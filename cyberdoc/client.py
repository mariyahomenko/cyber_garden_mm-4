import base64
import json
import math
import os
import re
import tempfile
import time
import uuid
from collections import Counter

import requests


class LLMError(RuntimeError):
    pass


def detect_language(text: str) -> str:
    """'ru', если в тексте много кириллицы, иначе 'en'."""
    text = text or ""
    cyr = sum(1 for ch in text if "\u0400" <= ch <= "\u04FF")
    lat = sum(1 for ch in text if ("a" <= ch.lower() <= "z"))
    return "ru" if cyr >= max(1, lat * 0.2) else "en"


class BaseClient:
    """Общий интерфейс провайдера LLM."""

    name = "base"
    key_env = ""
    key_title = "API ключ"
    default_model = ""

    def __init__(self):
        self.api_key = ""
        self.model = os.environ.get(self.key_env.replace("_API_KEY", "_MODEL"),
                                    self.default_model)
        self.retries = 3
        self.timeout = 300
        self.last_context_pages = []

    # ---------------- ключ ----------------
    def needs_key(self) -> bool:
        return not self.api_key

    def set_key(self, value: str):
        self.api_key = (value or "").strip()

    def credential_fields(self):
        return [("api_key", "Ключ %s:" % self.name, True)]

    def set_credentials(self, values: dict):
        self.set_key(values.get("api_key", ""))

    def ensure_key(self, parent=None, force=False) -> bool:
        if not force and not self.needs_key():
            return True
        return self.ask_credentials(parent)

    def ask_credentials(self, parent=None) -> bool:
        from PyQt5 import QtWidgets
        dlg = QtWidgets.QDialog(parent)
        dlg.setWindowTitle(self.key_title)
        dlg.setMinimumWidth(480)
        form = QtWidgets.QFormLayout(dlg)
        edits = {}
        for attr, label, secret in self.credential_fields():
            ed = QtWidgets.QLineEdit(dlg)
            ed.setText(getattr(self, attr, "") or "")
            if secret:
                ed.setEchoMode(QtWidgets.QLineEdit.Password)
            edits[attr] = ed
            form.addRow(label, ed)
        hint = QtWidgets.QLabel(
            "Данные не хранятся в коде и действуют до закрытия программы.")
        hint.setWordWrap(True)
        form.addRow(hint)
        box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        box.accepted.connect(dlg.accept)
        box.rejected.connect(dlg.reject)
        form.addRow(box)
        first = next(iter(edits.values()))
        first.setFocus()
        if dlg.exec_() != QtWidgets.QDialog.Accepted:
            return False
        self.set_credentials({k: e.text().strip() for k, e in edits.items()})
        return not self.needs_key()

    # ---------------- запрос ----------------
    def ask(self, prompt: str, temperature: float = 0.1,
            parent=None) -> str:
        if not self.ensure_key(parent):
            raise LLMError("API-ключ не введён — запрос отменён.")
        last_err = None
        for attempt in range(self.retries):
            try:
                return self._once(prompt, temperature)
            except LLMError as e:
                last_err = e
                if attempt < self.retries - 1:
                    time.sleep(2 ** attempt)
        raise last_err

    def _once(self, prompt, temperature) -> str:
        raise NotImplementedError

    # ---------------- ранкинг страниц ----------------
    def rank_pages(self, pages_text, question, top_n=12):
        """TF-IDF cosine-ранкинг страниц под вопрос (без внешних зависимостей).

        IDF считается по корпусу страниц документа, TF — с нормировкой
        на длину страницы. Возвращает отсортированный список индексов
        страниц (0-based), включая страницу 0.
        """

        def toks(s):
            return re.findall(r"[A-Za-zА-яЁё0-9]{3,}", (s or "").lower())

        q_toks = toks(question)
        if not q_toks:
            return list(range(min(top_n, len(pages_text))))

        page_toks = [toks(t) for t in pages_text]
        # IDF: log((N+1)/(df+1)) + 1
        df = {}
        for toks_list in page_toks:
            for w in set(toks_list):
                df[w] = df.get(w, 0) + 1
        n_docs = max(1, len(page_toks))

        def tfidf(tokens):
            tf = {}
            for w in tokens:
                tf[w] = tf.get(w, 0) + 1
            length = max(1, len(tokens))
            vec = {}
            for w, c in tf.items():
                idf = math.log((n_docs + 1) / (df.get(w, 0) + 1)) + 1.0
                vec[w] = (c / length) * idf
            return vec

        q_vec = tfidf(q_toks)
        q_norm = math.sqrt(sum(v * v for v in q_vec.values())) or 1.0

        scores = []
        for toks_list in page_toks:
            p_vec = tfidf(toks_list)
            p_norm = math.sqrt(sum(v * v for v in p_vec.values())) or 1.0
            dot = sum(q_vec[w] * p_vec.get(w, 0.0) for w in q_vec)
            scores.append(dot / (q_norm * p_norm))

        order = sorted(range(len(pages_text)), key=lambda i: -scores[i])
        picked = [i for i in order if scores[i] > 0][:top_n]
        if pages_text and 0 not in picked:
            picked.insert(0, 0)
        return sorted(set(picked))


class DeepSeekClient(BaseClient):
    name = "DeepSeek"
    key_env = "DEEPSEEK_API_KEY"
    key_title = "DeepSeek API"
    default_model = "deepseek-chat"

    def __init__(self):
        super().__init__()
        self.api_url = os.environ.get(
            "DEEPSEEK_API_URL", "https://api.deepseek.com/chat/completions")

    def _once(self, prompt, temperature) -> str:
        """Стриминговый запрос: чанки пишутся в файл, чтение из файла —
        обходит ограничение max_tokens и не теряет длинные ответы."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": "Bearer %s" % self.api_key,
        }
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "stream": True,
        }
        tmp_path = os.path.join(
            tempfile.gettempdir(), "cyberdoc_%s.md" % uuid.uuid4().hex)
        try:
            response = requests.post(
                self.api_url, headers=headers, json=payload,
                timeout=self.timeout, stream=True)
            if response.status_code != 200:
                raise LLMError(
                    "DeepSeek API %d: %s" % (response.status_code,
                                             response.text[:300]))
            with open(tmp_path, "w", encoding="utf-8") as f_out:
                for raw_line in response.iter_lines(decode_unicode=True):
                    if not raw_line:
                        continue
                    if raw_line.startswith("data: "):
                        data = raw_line[6:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            delta = chunk["choices"][0]["delta"].get(
                                "content", "") or ""
                        except (KeyError, IndexError, ValueError):
                            delta = ""
                        if delta:
                            f_out.write(delta)
                            f_out.flush()
            with open(tmp_path, "r", encoding="utf-8") as f_in:
                return f_in.read()
        except requests.RequestException as e:
            raise LLMError("Сетевая ошибка: %s" % e) from e
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass


class GigaChatClient(BaseClient):
    """GigaChat: авторизация OAuth (ID клиента + ключ → access_token)."""

    name = "GigaChat"
    key_env = "GIGACHAT_API_KEY"
    key_title = "GigaChat API"
    default_model = "GigaChat"

    def __init__(self):
        super().__init__()
        # Мы запрашиваем credentials только для текущего сеанса и не загружаем
        # секреты из окружения.
        self.client_id = ""
        self.api_url = os.environ.get(
            "GIGACHAT_API_URL",
            "https://gigachat.devices.sberbank.ru/api/v1/chat/completions")
        self.oauth_url = os.environ.get(
            "GIGACHAT_OAUTH_URL",
            "https://ngw.devices.sberbank.ru:9443/api/v2/oauth")
        self.scope = os.environ.get("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
        self.verify_ssl = os.environ.get("GIGACHAT_VERIFY_SSL", "0") == "1"
        self._token = None
        self._token_exp_ms = 0

    # ---------------- учётные данные ----------------
    def needs_key(self) -> bool:
        # Для GigaChat нужны И client_id, И ключ.
        return not self.api_key or not self.client_id

    def credential_fields(self):
        return [
            ("client_id", "ID клиента (Client ID):", False),
            ("api_key", "Ключ (Client Secret / Authorization key):", True),
        ]

    def set_credentials(self, values: dict):
        self.client_id = (values.get("client_id") or "").strip()
        self.set_key(values.get("api_key", ""))
        self._token = None
        self._token_exp_ms = 0

    # ---------------- токен доступа ----------------
    def _basic_value(self) -> str:
        key = (self.api_key or "").strip()
        # Личный кабинет может вернуть уже закодированный Base64 ключ.
        # Мы не кодируем такой ключ повторно.
        try:
            decoded = base64.b64decode(key, validate=True).decode("utf-8")
            if ":" in decoded:
                return key
        except Exception:
            pass
        if self.client_id:
            raw = ("%s:%s" % (self.client_id, key)).encode("utf-8")
            return base64.b64encode(raw).decode("ascii")
        return key

    def _get_token(self) -> str:
        now_ms = time.time() * 1000
        if self._token and now_ms < self._token_exp_ms - 60000:
            return self._token
        headers = {
            "Authorization": "Basic %s" % self._basic_value(),
            "RqUID": str(uuid.uuid4()),
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }
        try:
            r = requests.post(self.oauth_url, headers=headers,
                              data={"scope": self.scope}, timeout=30,
                              verify=self.verify_ssl)
        except requests.RequestException as e:
            raise LLMError("Сетевая ошибка авторизации GigaChat: %s" % e) from e
        if r.status_code != 200:
            raise LLMError("GigaChat: ошибка авторизации %d: %s. Проверьте "
                           "ID клиента и ключ." % (r.status_code, r.text[:300]))
        try:
            data = r.json()
            self._token = data["access_token"]
            expires = data.get("expires_at")
            # Мы поддерживаем миллисекунды Unix и ISO-время истечения токена.
            if isinstance(expires, str):
                try:
                    expires = float(expires)
                except ValueError:
                    try:
                        from datetime import datetime
                        expires = datetime.fromisoformat(
                            expires.replace("Z", "+00:00")).timestamp() * 1000
                    except ValueError:
                        expires = None
            if isinstance(expires, (int, float)) and expires < 1e12:
                expires *= 1000
            self._token_exp_ms = float(expires or (now_ms + 29 * 60 * 1000))
        except (KeyError, ValueError, TypeError) as e:
            raise LLMError("Неожиданный ответ авторизации GigaChat: %s"
                           % r.text[:300]) from e
        return self._token

    # ---------------- запрос ----------------
    def _once(self, prompt, temperature) -> str:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": "Bearer %s" % self._get_token(),
        }
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
        }
        try:
            response = requests.post(
                self.api_url, headers=headers, json=payload,
                timeout=self.timeout, verify=self.verify_ssl)
        except requests.RequestException as e:
            raise LLMError("Сетевая ошибка: %s" % e) from e
        if response.status_code == 401:
            self._token = None          # токен устарел — получим заново
        if response.status_code != 200:
            raise LLMError("GigaChat API %d: %s" % (
                response.status_code, response.text[:300]))
        try:
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as e:
            raise LLMError("Неожиданный ответ GigaChat: %s"
                           % response.text[:300]) from e


PROVIDERS = {
    "deepseek": DeepSeekClient,
    "gigachat": GigaChatClient,
}


def make_client(provider: str) -> BaseClient:
    return PROVIDERS.get((provider or "deepseek").lower(),
                         DeepSeekClient)()


SYSTEM_PROMPT = (
    "Ты — научный ассистент по физике и математике. "
    "Отвечай, используя ТОЛЬКО предоставленный текст статьи.\n"
    "\n"
    "=== ЯЗЫК ===\n"
    "Отвечай СТРОГО на том языке, на котором задан вопрос пользователя. "
    "Если статья на английском, а вопрос на русском — отвечай по-русски. "
    "Если вопрос на английском — отвечай по-английски. "
    "Названия, термины и цитаты из статьи можно давать в оригинале "
    "с переводом в скобках.\n"
    "\n"
    "=== НУМЕРАЦИЯ СТРАНИЦ ===\n"
    "Маркеры [Страница N] используют сквозную нумерацию фрагментов "
    "с 1 до конца, НЕЗАВИСИМО от печатной нумерации, напечатанной на "
    "самих страницах (она может начинаться с 1000 или быть иной). "
    "Когда пользователь называет страницу, ориентируйся на смысл: "
    "'третья страница' — это фрагмент [Страница 3]. Если пользователь "
    "называет число с арифметикой ('2+1', '5-2') — вычисли результат. "
    "Печатный номер страницы и номер фрагмента могут не совпадать — "
    "это нормально, не сообщай, что страницы 'нет'.\n"
    "\n"
    "=== ОСОБЕННОСТИ ТЕКСТА ===\n"
    "Текст статей свёрстан, как правило, В ДВЕ КОЛОНКИ: извлечённый "
    "текст читается колонка за колонкой, строки разных колонок могут "
    "перемежаться. Не считай, что текст 'обрывается' — он продолжается "
    "в следующей колонке или на следующей странице. Сноски и список "
    "литературы в конце страницы НЕ относятся к основному тексту — "
    "не принимай их за продолжение абзаца и не считай, что основной "
    "текст закончился. НИКОГДА не пиши, что текст обрывается или что "
    "загружена только одна страница, если фрагментов несколько.\n"
    "\n"
    "=== ПРАВИЛА ФОРМАТА ===\n"
    "1. Структурируй ответ: короткие заголовки (##), списки, абзацы.\n"
    "2. После каждого факта — источник [стр. N], N — номер фрагмента "
    "из маркера [Страница N]. Для разных фактов — разные N.\n"
    "3. КАЖДАЯ формула — ОТДЕЛЬНОЙ строкой, строго в виде:\n"
    " [[FORMULA p.<N>: <latex>]]\n"
    " где N — номер фрагмента, где формула встречается.\n"
    " В обычном тексте вместо формулы — только пояснение словами. "
    "Никаких $...$, \\(...\\), \\[...\\], \\begin{...} в тексте.\n"
    "4. После каждой формулы ОБЯЗАТЕЛЬНО дай короткую якорную цитату:\n"
    ' [[REF p.N: "3-8 слов, которые в тексте PDF стоят ВПЛОТНУЮ к этой'
    ' формуле — на той же строке или строкой выше/ниже. Внутри цитаты'
    ' должна быть ХОТЯ БЫ ОДНА латинская буква из самой формулы'
    ' (например, H, J, E, V, diag, m)."]],\n'
    " чтобы при поиске в PDF попасть в саму формулу, а не в текст"
    " абзаца над ней.\n"
    " Приводи цитату дословно, как в тексте, с той же пунктуацией.\n"
    "\n"
    "=== ПРАВИЛА LaTeX ВНУТРИ [[FORMULA ...]] ===\n"
    "- Дроби — \\frac{a}{b}, индексы — _{...}, степени — ^{...}.\n"
    "- Греки — \\alpha, \\beta, \\gamma, \\sigma, \\mu (латиницей).\n"
    "- НЕ пиши кириллицу внутри LaTeX, не используй \\text{} с кириллицей.\n"
    "- Одна формула — один маркер.\n"
    "- Многострочные системы пиши через \\begin{cases}...\\end{cases} "
    "или через несколько [[FORMULA]] подряд.\n"
    "\n"
    "=== ОСТАЛЬНОЕ ===\n"
    "5. Если ответа нет в тексте — напиши: "
    "В данной статье эта информация не найдена.\n"
    "6. Не выдумывай факты и формулы.\n"
    "7. НЕ добавляй служебные строки [[START_PAGE: ...]] или "
    "[[PAGES: ...]].\n"
)


def build_prompt(pages_text, context_pages, question, doc_name=None):
    lang = detect_language(question)
    lang_rule = ("Ответ давай на русском языке."
                 if lang == "ru" else
                 "Give your answer in English.")
    chunks = []
    for pno in context_pages:
        chunks.append("[Страница %d]\n%s" % (pno + 1, pages_text[pno]))
    full_text = "\n".join(chunks)
    src = ("\nИсточник — файл: %s. В начале ответа укажи имя файла."
           % doc_name if doc_name else "")
    return ("%s\n\n%s%s\n\n=== ТЕКСТ СТАТЬИ ===\n%s\n\n=== ВОПРОС ===\n%s"
            % (SYSTEM_PROMPT, lang_rule, src, full_text, question))