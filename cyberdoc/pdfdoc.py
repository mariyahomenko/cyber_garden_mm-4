import re
import unicodedata
from pathlib import Path
import fitz

try:
    import pytesseract
    from PIL import Image
    HAS_OCR = True
except Exception:
    HAS_OCR = False

MODE_PHRASE = "phrase"          # точная фраза целиком
MODE_WORDS = "words"            # каждое слово запроса (целые слова)
MODE_SUBSTRING = "substring"    # вхождение внутри слов
MODE_REGEX = "regex"            # регулярное выражение

SEARCH_MODES = [
    (MODE_PHRASE, "Точная фраза"),
    (MODE_WORDS, "Слова запроса"),
    (MODE_SUBSTRING, "Вхождение в словах"),
    (MODE_REGEX, "Регулярное выражение"),
]


def _normalize(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    s = s.replace("\u00ad", "")
    s = s.replace("\u2011", "-").replace("\u2010", "-")
    s = s.replace("\u2013", "-").replace("\u2014", "-")
    s = s.replace("«", "").replace("»", "")
    s = s.replace("\u201c", "").replace("\u201d", "")
    s = re.sub(r"\s+", " ", s)
    return s.strip().lower()


class PDFDocument:
    def __init__(self, path: str):
        self.path = path
        self.name = Path(path).name
        self.doc = fitz.open(path)
        self.pages_text = [p.get_text("text") for p in self.doc]
        self.first_page_number = self._detect_first_page_number()
        self.highlights = {}          # {(pno, rect_tuple): color} — маркеры
        self.search_highlights = {}   # {(pno, rect_tuple): True}
        self.bookmarks = []
        self.thumbs = {}
        self._ai_highlights = []      # [(pno, fitz.Rect)] — подсветки из ответа
        # Колонко-ориентированный текст (для промпта и ранкинга)
        self.pages_text = [self._extract_page_text(p) for p in self.doc]
        # После сортировки блоков снова подставляем OCR для пустых страниц.
        for i, text in enumerate(self.pages_text):
            if len(text.strip()) < 20:
                words = self._ocr_page_words(i)
                if words:
                    self.pages_text[i] = " ".join(
                        word for *_box, word in words)
        self._norm_pages = [_normalize(t) for t in self.pages_text]
        self._layout_cache = {}

    # ==================== OCR СКАНОВ ====================
    def _ocr_replace_empty_pages(self):
        """Мы добавляем распознанный текст в индекс, сохраняя исходный скан."""
        empty = {i for i, t in enumerate(self.pages_text)
                 if len(t.strip()) < 20}
        if not empty:
            return
        for i in sorted(empty):
            words = self._ocr_page_words(i)
            if words:
                self.pages_text[i] = " ".join(word for *_box, word in words)

    def _ocr_page_words(self, pno):
        """Слова страницы через Tesseract: [(x0,y0,x1,y1,word)]."""
        page = self.doc[pno]
        # Мы используем встроенный OCR-мост PyMuPDF без PyTesseract.
        if not HAS_OCR:
            try:
                try:
                    tp = page.get_textpage_ocr(language="rus+eng", dpi=200, full=True)
                except Exception:
                    tp = page.get_textpage_ocr(language="eng", dpi=200, full=True)
                words = []
                for x0, y0, x1, y1, word, *_ in tp.extractWORDS():
                    word = (word or "").strip()
                    if word:
                        words.append((x0, y0, x1, y1, word))
                return words
            except Exception:
                return []
        pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        try:
            try:
                data = pytesseract.image_to_data(
                    img, output_type=pytesseract.Output.DICT,
                    lang="rus+eng", config="--psm 6")
            except Exception:
                data = pytesseract.image_to_data(
                    img, output_type=pytesseract.Output.DICT,
                    lang="eng", config="--psm 6")
        except Exception:
            return []
        words = []
        n = len(data.get("text", []))
        for i in range(n):
            w = (data["text"][i] or "").strip()
            if not w:
                continue
            try:
                conf = float(data["conf"][i])
            except (ValueError, TypeError):
                conf = -1
            if conf < 20:
                continue
            x0 = data["left"][i] / 2.0
            y0 = data["top"][i] / 2.0
            x1 = (data["left"][i] + data["width"][i]) / 2.0
            y1 = (data["top"][i] + data["height"][i]) / 2.0
            words.append((x0, y0, x1, y1, w))
        return words

    # ==================== КОЛОНКИ ====================
    def _extract_page_text(self, page) -> str:
        """Текст страницы в порядке чтения: для двухколоночной вёрстки
        сначала левая колонка, затем правая."""
        try:
            blocks = page.get_text("blocks")
        except Exception:
            return page.get_text("text")
        if not blocks:
            return ""
        w = page.rect.width
        left, right, other = [], [], []
        total_chars = 0
        for b in blocks:
            x0, y0, x1, y1, text = b[0], b[1], b[2], b[3], (b[4] or "")
            total_chars += len(text.strip())
            cx = (x0 + x1) / 2.0
            if cx < w * 0.48:
                left.append(b)
            elif cx > w * 0.52:
                right.append(b)
            else:
                other.append(b)
        # две колонки: обе стороны содержат заметную часть текста
        l_chars = sum(len((b[4] or "").strip()) for b in left)
        r_chars = sum(len((b[4] or "").strip()) for b in right)
        two_col = (total_chars > 0 and l_chars > total_chars * 0.15
                   and r_chars > total_chars * 0.15)
        if not two_col:
            ordered = sorted(blocks, key=lambda b: (b[1], b[0]))
            return "\n".join((b[4] or "").strip() for b in ordered
                             if (b[4] or "").strip())
        left_sorted = sorted(left, key=lambda b: (b[1], b[0]))
        right_sorted = sorted(right, key=lambda b: (b[1], b[0]))
        parts = [(b[4] or "").strip() for b in left_sorted
                 if (b[4] or "").strip()]
        parts += [(b[4] or "").strip() for b in other
                  if (b[4] or "").strip()]
        parts += [(b[4] or "").strip() for b in right_sorted
                  if (b[4] or "").strip()]
        return "\n".join(parts)

    # ==================== НУМЕРАЦИЯ СТРАНИЦ ====================
    def _detect_first_page_number(self) -> int:
        """Печатный номер первой страницы (метки PDF или колонтитул)."""
        try:
            lbl = self.doc[0].get_label()
            if lbl and str(lbl).strip().isdigit():
                return int(str(lbl).strip())
        except Exception:
            pass
        text = self.pages_text[0] if self.pages_text else ""
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        for l in lines[:3] + lines[-3:]:
            if re.fullmatch(r"\d{1,5}", l):
                return int(l)
        return 1

    def to_pdf_index(self, article_page):
        """Номер страницы → индекс в PDF.

        Сначала трактуем число как печатный номер (first_page_number...),
        если оно вне диапазона печатной нумерации — как порядковый
        номер страницы с начала документа (даже если печатная нумерация
        начинается с тысячной)."""
        if article_page is None:
            return None
        try:
            n = int(str(article_page).strip())
        except (TypeError, ValueError):
            return None
        idx = n - int(self.first_page_number)
        if 0 <= idx < len(self.doc):
            return idx
        if 1 <= n <= len(self.doc):
            return n - 1
        return None

    def to_article_page(self, pdf_index: int):
        """Индекс в PDF → порядковый номер фрагмента (1..N)."""
        if 0 <= pdf_index < len(self.doc):
            return pdf_index + 1
        return None

    def printable_page(self, pdf_index: int):
        """Индекс в PDF → печатный номер страницы."""
        if 0 <= pdf_index < len(self.doc):
            return pdf_index + int(self.first_page_number)
        return None

    # ==================== ПОИСК ====================
    def search(self, query: str, mode: str = MODE_PHRASE,
               case_sensitive: bool = False):
        """Поиск по всем страницам с настройками.

        mode: phrase | words | substring | regex.
        Возвращает список {'page', 'rect', 'text'}."""
        results = []
        if not query or not query.strip():
            return results
        q = query.strip()
        rx = None
        if mode == MODE_REGEX:
            try:
                rx = re.compile(q, 0 if case_sensitive else re.IGNORECASE)
            except re.error:
                return []
        for pno, page in enumerate(self.doc):
            if mode == MODE_REGEX:
                for r in self._regex_on_page(page, pno, rx):
                    results.append(r)
            elif mode == MODE_SUBSTRING:
                qq = q if case_sensitive else q.lower()
                for w in self._page_words(page):
                    ww = w[4] if case_sensitive else w[4].lower()
                    if qq in ww:
                        results.append({"page": pno,
                                        "rect": fitz.Rect(w[:4]),
                                        "text": w[4]})
            elif mode == MODE_WORDS:
                qset = q.split()
                if not case_sensitive:
                    qset = [x.lower() for x in qset]
                qset = set(qset)
                for w in self._page_words(page):
                    ww = w[4] if case_sensitive else w[4].lower()
                    if ww in qset:
                        results.append({"page": pno,
                                        "rect": fitz.Rect(w[:4]),
                                        "text": w[4]})
            else:  # MODE_PHRASE
                if case_sensitive:
                    results.extend(self._phrase_case_sensitive(page, pno, q))
                else:
                    try:
                        for r in page.search_for(q):
                            results.append({"page": pno, "rect": r, "text": q})
                    except Exception:
                        pass
        if mode == MODE_PHRASE and not results:
            # фолбэк: переносы/дефисы/лигатуры ломают точный поиск —
            # ищем отдельные значимые слова запроса
            significant = [w for w in re.findall(r"[\w\-]{3,}", q)
                           if not w.isdigit()]
            if significant:
                results = self.search(" ".join(significant), MODE_WORDS,
                                      case_sensitive)
        return results

    @staticmethod
    def _page_words(page):
        try:
            return page.get_text("words")
        except Exception:
            return []

    @staticmethod
    def _regex_on_page(page, pno, rx):
        """Регулярка по строкам страницы: диапазон совпадения
        превращаем в объединение rect-ов входящих в него слов."""
        results = []
        lines = {}
        for w in PDFDocument._page_words(page):
            lines.setdefault((w[5], w[6]), []).append(w)
        for key in lines:
            ws = sorted(lines[key], key=lambda w: w[0])
            text = " ".join(w[4] for w in ws)
            spans, pos = [], 0
            for w in ws:
                spans.append((pos, pos + len(w[4])))
                pos += len(w[4]) + 1
            for m in rx.finditer(text):
                rect = None
                for w, (s, e) in zip(ws, spans):
                    if s < m.end() and e > m.start():
                        r = fitz.Rect(w[:4])
                        rect = r if rect is None else rect | r
                if rect is not None:
                    results.append({"page": pno, "rect": rect,
                                    "text": m.group(0)})
        return results

    def _phrase_case_sensitive(self, page, pno, q):
        """Поиск фразы с учётом регистра: построчно по словам."""
        results = []
        lines = {}
        for w in self._page_words(page):
            lines.setdefault((w[5], w[6]), []).append(w)
        for key in lines:
            ws = sorted(lines[key], key=lambda w: w[0])
            text = " ".join(w[4] for w in ws)
            spans, pos = [], 0
            for w in ws:
                spans.append((pos, pos + len(w[4])))
                pos += len(w[4]) + 1
            for m in re.finditer(re.escape(q), text):
                rect = None
                for w, (s, e) in zip(ws, spans):
                    if s < m.end() and e > m.start():
                        r = fitz.Rect(w[:4])
                        rect = r if rect is None else rect | r
                if rect is not None:
                    results.append({"page": pno, "rect": rect, "text": q})
        return results

    def search_exact_ci(self, query: str):
        """Обратная совместимость: регистронезависимый поиск фразы."""
        return self.search(query, MODE_PHRASE, False)

    def find_all_on_page(self, pno, query, mode=MODE_PHRASE,
                         case_sensitive=False):
        """Все вхождения запроса на одной странице (для подсветки по ссылке)."""
        if not (0 <= pno < len(self.doc)):
            return []
        saved = []
        page = self.doc[pno]
        if mode == MODE_REGEX:
            try:
                rx = re.compile(query, 0 if case_sensitive else re.IGNORECASE)
            except re.error:
                return []
            for r in self._regex_on_page(page, pno, rx):
                saved.append(r["rect"])
        elif mode == MODE_SUBSTRING:
            qq = query if case_sensitive else query.lower()
            for w in self._page_words(page):
                ww = w[4] if case_sensitive else w[4].lower()
                if qq in ww:
                    saved.append(fitz.Rect(w[:4]))
        elif mode == MODE_WORDS:
            qset = set(query.split())
            if not case_sensitive:
                qset = {x.lower() for x in qset}
            for w in self._page_words(page):
                ww = w[4] if case_sensitive else w[4].lower()
                if ww in qset:
                    saved.append(fitz.Rect(w[:4]))
        else:
            if case_sensitive:
                for r in self._phrase_case_sensitive(page, pno, query):
                    saved.append(r["rect"])
            else:
                try:
                    saved = list(page.search_for(query))
                except Exception:
                    saved = []
        return [r for r in saved if r is not None]

    # ==================== ПОДСВЕТКИ ====================
    @staticmethod
    def _rect_key(rect):
        return (float(rect.x0), float(rect.y0),
                float(rect.x1), float(rect.y1))

    def toggle_highlight(self, pno, rect, color=(255, 170, 0, 130)):
        """Поставить/снять маркер (по совпадению области)."""
        key = (pno, self._rect_key(rect))
        if key in self.highlights:
            self.highlights.pop(key, None)
        else:
            self.highlights[key] = color

    def add_search_highlight(self, pno, rect):
        key = (pno, self._rect_key(rect))
        self.search_highlights[key] = True

    def clear_search_highlights(self):
        self.search_highlights.clear()

    # ==================== AI-ПОДСВЕТКИ ====================
    def set_ai_highlights(self, items):
        """items: список (pno, rect). Подсвечиваются ВСЕ найденные места."""
        out = []
        for pno, rect in items:
            if rect is None:
                continue
            try:
                out.append((int(pno), fitz.Rect(rect)))
            except Exception:
                continue
        self._ai_highlights = out

    def set_ai_highlight(self, pno, rect):
        if rect is None:
            self._ai_highlights = []
        else:
            self.set_ai_highlights([(pno, rect)])

    def get_ai_highlights(self):
        return list(self._ai_highlights)

    def get_ai_highlight(self):
        return self._ai_highlights[0] if self._ai_highlights else None

    def clear_ai_highlight(self):
        self._ai_highlights = []

    # ==================== ЛЕЙАУТ СТРАНИЦЫ ====================
    def _page_layout(self, pno):
        if pno in self._layout_cache:
            return self._layout_cache[pno]
        page = self.doc[pno]
        data = page.get_text("dict")
        lines = []
        for b in data.get("blocks", []):
            if b.get("type") != 0:
                continue
            bx0, by0, bx1, by1 = b["bbox"]
            for ln in b.get("lines", []):
                lx0, ly0, lx1, ly1 = ln["bbox"]
                spans = []
                for sp in ln.get("spans", []):
                    spans.append({
                        "bbox": tuple(sp["bbox"]),
                        "font": sp.get("font", ""),
                        "size": sp.get("size", 0.0),
                        "text": sp.get("text", ""),
                        "flags": sp.get("flags", 0),
                    })
                math_hint = False
                for sp in spans:
                    fn = (sp["font"] or "").lower()
                    if any(k in fn for k in
                           ("math", "symbol", "italic", "cmr", "cmmi",
                            "cmex", "cmsy", "stix", "mt extra")):
                        math_hint = True
                        break
                    if sp["flags"] & 0b10:
                        math_hint = True
                        break
                lines.append({
                    "bbox": (lx0, ly0, lx1, ly1),
                    "block_bbox": (bx0, by0, bx1, by1),
                    "spans": spans,
                    "math_hint": math_hint,
                })
        heights = sorted(
            (l["bbox"][3] - l["bbox"][1])
            for l in lines if l["bbox"][3] > l["bbox"][1])
        med_h = heights[len(heights) // 2] if heights else 12.0
        self._layout_cache[pno] = {"lines": lines, "med_h": med_h}
        return self._layout_cache[pno]

    # ==================== РАСШИРЕНИЕ ЯКОРЯ ДО ФОРМУЛЫ ====================
    def find_formula_rect(self, pdf_index, anchor_rect=None):
        if not (0 <= pdf_index < len(self.doc)):
            return None
        page = self.doc[pdf_index]
        layout = self._page_layout(pdf_index)
        lines = layout["lines"]
        med_h = layout["med_h"]

        anchor_line_idx = None
        if anchor_rect is not None:
            ar = fitz.Rect(anchor_rect)
            best_i, best_d = None, None
            for i, ln in enumerate(lines):
                lr = fitz.Rect(ln["bbox"])
                if ar.intersects(lr):
                    d = abs((lr.y0 + lr.y1) / 2.0 -
                            (ar.y0 + ar.y1) / 2.0)
                    if best_d is None or d < best_d:
                        best_d = d
                        best_i = i
            if best_i is not None:
                anchor_line_idx = best_i

        if anchor_line_idx is not None:
            line = lines[anchor_line_idx]
            x0, y0, x1, y1 = line["bbox"]
            for sp in line["spans"]:
                sx0, sy0, sx1, sy1 = sp["bbox"]
                if sy1 > y0 - med_h and sy0 < y1 + med_h:
                    x0 = min(x0, sx0)
                    x1 = max(x1, sx1)
                    y0 = min(y0, sy0)
                    y1 = max(y1, sy1)

            block_bbox = line["block_bbox"]
            bx0, by0, bx1, by1 = block_bbox
            gap_limit = med_h * 1.6

            def neighbour_ok(ln):
                lr = fitz.Rect(ln["bbox"])
                if not (lr.y1 >= by0 - 1 and lr.y0 <= by1 + 1):
                    return False
                if ln["math_hint"]:
                    return True
                txt = "".join(sp["text"] for sp in ln["spans"]).strip()
                return len(txt) <= 12

            for _ in range(30):
                ok_up = (anchor_line_idx > 0 and
                         neighbour_ok(lines[anchor_line_idx - 1]) and
                         (y0 - lines[anchor_line_idx - 1]["bbox"][3])
                         <= gap_limit)
                ok_dn = (anchor_line_idx < len(lines) - 1 and
                         neighbour_ok(lines[anchor_line_idx + 1]) and
                         (lines[anchor_line_idx + 1]["bbox"][1] - y1)
                         <= gap_limit)
                moved = False
                if ok_up:
                    lr = lines[anchor_line_idx - 1]["bbox"]
                    x0 = min(x0, lr[0]); y0 = min(y0, lr[1])
                    x1 = max(x1, lr[2]); y1 = max(y1, lr[3])
                    anchor_line_idx -= 1
                    moved = True
                if ok_dn:
                    lr = lines[anchor_line_idx + 1]["bbox"]
                    x0 = min(x0, lr[0]); y0 = min(y0, lr[1])
                    x1 = max(x1, lr[2]); y1 = max(y1, lr[3])
                    anchor_line_idx += 1
                    moved = True
                if not moved:
                    break
            result = fitz.Rect(x0, y0, x1, y1)
        else:
            math_lines = [ln for ln in lines if ln["math_hint"]]
            if math_lines:
                bbs = [fitz.Rect(ln["bbox"]) for ln in math_lines]
                result = bbs[0]
                for r in bbs[1:]:
                    result |= r
            else:
                result = None

        if result is not None:
            pad_y = med_h * 2.5
            region = fitz.Rect(
                result.x0 - 10, result.y0 - pad_y,
                result.x1 + 10, result.y1 + pad_y)
            # объединяем ВСЕ строки формул в районе якоря —
            # чтобы выделялась формула целиком, а не кусок
            for ln in lines:
                if not ln["math_hint"]:
                    continue
                lr = fitz.Rect(ln["bbox"])
                if lr.intersects(region):
                    result |= lr
            try:
                for d in page.get_drawings():
                    r = fitz.Rect(d["rect"])
                    if r.width < 6 or r.height < 6:
                        continue
                    if r.intersects(region):
                        result |= r
            except Exception:
                pass
            try:
                for img in page.get_images(full=True):
                    for r in page.get_image_rects(img[0]):
                        r = fitz.Rect(r)
                        if r.width < 10 or r.height < 10:
                            continue
                        if r.intersects(region):
                            result |= r
            except Exception:
                pass
            result = fitz.Rect(
                result.x0 - 2, result.y0 - 2,
                result.x1 + 2, result.y1 + 2)

        if result is None and not self.pages_text[pdf_index].strip() \
                and anchor_rect is not None:
            r = self._resolve_anchor_ocr(pdf_index, "")
            if r is not None:
                result = r
        return result

    # ==================== RESOLVE ANCHOR ====================
    def resolve_anchor(self, article_page: int, quote: str):
        pno = self.to_pdf_index(article_page)
        if pno is None:
            return None
        page = self.doc[pno]
        text = self.pages_text[pno]
        q = " ".join((quote or "").split())
        if not q:
            return None
        try:
            rects = page.search_for(q)
        except Exception:
            rects = []
        if rects:
            return rects[0]
        norm_q = _normalize(q)
        if norm_q:
            words = norm_q.split()
            for n in (12, 10, 8, 6, 5, 4, 3, 2):
                if len(words) < n:
                    continue
                for start in (0, len(words) - n):
                    cand_words = words[start:start + n]
                    cand = " ".join(cand_words)
                    try:
                        rects = page.search_for(cand)
                    except Exception:
                        rects = []
                    if rects:
                        return rects[0]
            for w in words:
                if len(w) < 4:
                    continue
                try:
                    rects = page.search_for(w)
                except Exception:
                    rects = []
                if rects:
                    return rects[0]
        if not text.strip():
            r = self._resolve_anchor_ocr(pno, quote)
            if r is not None:
                return r
        return None

    def _resolve_anchor_ocr(self, pno, quote):
        words = [{"text": _normalize(w[4]), "rect": fitz.Rect(w[:4])}
                 for w in self._page_words(self.doc[pno])]
        if not words:
            return None
        q_words = _normalize(quote).split() if quote else []
        if not q_words:
            r = fitz.Rect(words[0]["rect"])
            for w in words[1:]:
                r |= w["rect"]
            return r
        for i in range(len(words) - len(q_words) + 1):
            ok = True
            for j, qw in enumerate(q_words):
                if words[i + j]["text"] != qw:
                    ok = False
                    break
            if ok:
                r = fitz.Rect(words[i]["rect"])
                for j in range(1, len(q_words)):
                    r |= words[i + j]["rect"]
                return r
        return None

    # ==================== TOC / len ====================
    def get_toc(self):
        try:
            return self.doc.get_toc()
        except Exception:
            return []

    def __len__(self):
        return len(self.doc)
