"""Evidence-first structured extraction для RAG-домена (ВИНИТИ/ЮФУ, тема 2).

Поля и колонки — ровно по submission_template/schema.json.
source_fragment — дословная подстрока страницы PDF.
Неизвестное остаётся None, не выдумывается.

Таблицы и рисунки с метриками, которые строковый парсер не извлёк,
попадают в issues.csv как present_not_extractable (не в results.csv).
"""
import re
import uuid
from pathlib import Path

RAG = "rag"

# ---------------------------------------------------------------- FIELDS
CSV_FIELDS_RAG = {
    "publications": [
        "publication_id", "title", "year", "DOI", "authors",
        "in_scope", "exclusion_reason",
    ],
    "configurations": [
        "publication_id", "config_id", "rag_variant", "retrieval_method",
        "retriever_model", "embedding_model", "embedding_version",
        "chunking_method", "chunk_size", "chunk_overlap", "chunk_unit",
        "index_type", "vector_store", "top_k", "reranker_model",
        "generator_model", "generator_version", "prompt_strategy",
        "context_strategy", "note",
    ],
    "datasets": [
        "publication_id", "dataset_id", "dataset_name", "dataset_version",
        "language", "data_split", "scientific_domain", "note",
    ],
    "tasks": [
        "publication_id", "task_id", "task_type", "note",
    ],
    "experiments": [
        "publication_id", "experiment_id", "evaluation_protocol",
        "baseline_name", "hardware", "latency_ms", "tokens_per_query",
        "sample_size", "note",
    ],
    "results": [
        "publication_id", "result_id", "experiment_id", "config_id",
        "dataset_id", "task_id", "metric_group", "metric_name",
        "metric_variant", "metric_direction", "metric_k", "metric_value",
        "metric_unit", "baseline_value", "aggregation", "sample_size",
        "raw_value", "raw_unit", "normalized_value", "normalized_unit",
        "result_origin", "cited_publication_id", "source_page",
        "source_section", "source_table", "source_figure",
        "source_fragment", "extraction_status", "duplicate_of", "note",
    ],
    "issues": [
        "publication_id", "issue_id", "record_ids", "check_name",
        "description", "source_page", "source_fragment",
    ],
}

FIELDS_RAG = {k: list(v) for k, v in CSV_FIELDS_RAG.items()}

# ---------------------------------------------------------------- PATTERNS
PATTERNS_RAG = [
    ("Recall@k",
     r"\bRecall\s*@\s*(\d+)\s*(?:=|:)\s*(\d+(?:[.,]\d+)?)\s*(%)?",
     "retrieval", "fraction", "higher_is_better"),
    ("Precision@k",
     r"\bPrecision\s*@\s*(\d+)\s*(?:=|:)\s*(\d+(?:[.,]\d+)?)\s*(%)?",
     "retrieval", "fraction", "higher_is_better"),
    ("MRR",
     r"\bMRR\s*(?:=|:)\s*(\d+(?:[.,]\d+)?)\s*(%)?",
     "retrieval", "fraction", "higher_is_better"),
    ("NDCG@k",
     r"\bNDCG\s*@\s*(\d+)\s*(?:=|:)\s*(\d+(?:[.,]\d+)?)\s*(%)?",
     "retrieval", "fraction", "higher_is_better"),
    ("NDCG",
     r"\bNDCG\s*(?:=|:)\s*(\d+(?:[.,]\d+)?)\s*(%)?",
     "retrieval", "fraction", "higher_is_better"),
    ("EM",
     r"\b(?:Exact\s*Match|EM)\s*(?:=|:)\s*(\d+(?:[.,]\d+)?)\s*(%)?",
     "qa", "fraction", "higher_is_better"),
    ("F1",
     r"\bF1\s*(?:=|:)\s*(\d+(?:[.,]\d+)?)\s*(%)?",
     "qa", "fraction", "higher_is_better"),
    ("BLEU",
     r"\bBLEU(?:-?\d+)?\s*(?:=|:)\s*(\d+(?:[.,]\d+)?)\s*(%)?",
     "generation", "fraction", "higher_is_better"),
    ("ROUGE-L",
     r"\bROUGE(?:-L)?\s*(?:=|:)\s*(\d+(?:[.,]\d+)?)\s*(%)?",
     "generation", "fraction", "higher_is_better"),
    ("UniEval",
     r"\b(?:UniEval|factual\s+consistency)\s*(?:=|:|score)?\s*"
     r"(\d+(?:[.,]\d+)?)\s*(%)?",
     "generation", "fraction", "higher_is_better"),
    ("tokens_per_query",
     r"\b(\d+(?:[.,]\d+)?)\s*(k|K|M)?\s*tokens?\s*(?:per|/)\s*query",
     "cost", "tokens", "lower_is_better"),
    ("latency",
     r"\b(?:latency|inference\s+time)\s*(?:=|:)?\s*"
     r"(\d+(?:[.,]\d+)?)\s*(ms|s|sec|seconds?)\b",
     "cost", "ms", "lower_is_better"),
]

# ---------------------------------------------------------------- REGEX
RE_TABLE = re.compile(r"\b(?:Table|Таблица)\s*([0-9]+[A-Za-z]?)", re.I)
RE_FIG = re.compile(r"\b(?:Fig(?:ure)?\.?|Рис(?:унок)?\.?)\s*([0-9]+[A-Za-z]?)", re.I)
RE_SECTION = re.compile(r"\b(?:Section|Раздел)\s*([0-9]+(?:\.[0-9]+)*)", re.I)

# Конфигурации: только конкретные имена систем, без общего «RAG».
RE_RAG_VARIANT = re.compile(
    r"\b(RAG-EDA|ThreadRAG|MoRSE|GraphRAG|LightRAG|HippoRAG|"
    r"Self-RAG|CRAG|RAGAS|Naive\s*RAG|Vanilla\s*RAG)\b", re.I)
RE_RETRIEVAL = re.compile(
    r"\b(BM25|TF-?IDF|dense|sparse|semantic|lexical|hybrid|"
    r"hybrid\s+(?:BM25\s+and\s+dense|semantic\s+and\s+lexical))\b", re.I)
# embedding: только эмбеддеры, без reranker-ов.
RE_EMBEDDING = re.compile(
    r"\b(BAAI/bge-(?:large|base|small)(?:-en)?(?:-v1\.5)?|"
    r"bge-(?:large|base|small)(?:-en)?(?:-v1\.5)?|"
    r"Qwen3-Embedding[-\w.]*|nomic-embed-text|"
    r"text-embedding-(?:ada|3)[-\w.]*|Sentence-?BERT[-\w.]*|"
    r"E5[-\w.]*)\b", re.I)
RE_RERANKER = re.compile(
    r"\b(bge-reranker[-\w.]*|Qwen3-Reranker[-\w.]*|"
    r"cross-?encoder[-\w.]*|Cohere\s+Rerank[-\w.]*|"
    r"monoT5[-\w.]*)\b", re.I)
RE_GENERATOR = re.compile(
    r"\b(GPT-?4(?:o(?:-mini)?)?|GPT-?3\.5[-\w.]*|Llama[-\s]?\d[-\w.]*|"
    r"Qwen[-\s]?\d[-\w.]*|Mistral[-\w.]*|Mixtral[-\w.]*|Gemini[-\w.]*|"
    r"DeepSeek[-\w.]*|GigaChat[-\w.]*|Claude[-\w.]*)\b", re.I)
RE_CHUNK = re.compile(
    r"\bchunk(?:s|ing)?\s*(?:size|length)\s*(?:=|:|of)?\s*"
    r"(\d+)\s*(tokens?|characters?|words?)\b", re.I)
RE_CHUNK_OVERLAP = re.compile(
    r"\boverlap\s*(?:=|:|of)?\s*(\d+)\s*(tokens?|characters?|words?)\b",
    re.I)
RE_TOPK = re.compile(r"\btop[- ]?k\s*(?:=|:|of)?\s*(\d+)\b", re.I)
RE_INDEX = re.compile(
    r"\b(FAISS|Elasticsearch|Pinecone|Chroma|Qdrant|Milvus|Weaviate|"
    r"Annoy|ScaNN|HNSW|IVF)\b", re.I)

# Датасеты: инструменты (OpenROAD) и общие слова (quality) не датасеты.
RE_DATASET = re.compile(
    r"\b(HotpotQA|2WikiMultiHopQA|2WikiMultihopQA|2WikiMultihop|MuSiQue|"
    r"NaturalQuestions|TriviaQA|WebQuestions|ORD-QA|FinanceBench|"
    r"LongHealth|QuALITY|BEIR|MTEB)\b", re.I)

# Нормализация имён датасетов (алиасы -> каноническое имя).
DATASET_CANON = {
    "2wikimultihop": "2WikiMultiHopQA",
    "2wikimultihopqa": "2WikiMultiHopQA",
    "naturalquestions": "NaturalQuestions",
    "ord-qa": "ORD-QA",
    "financebench": "FinanceBench",
    "longhealth": "LongHealth",
    "hotpotqa": "HotpotQA",
    "musique": "MuSiQue",
    "triviaqa": "TriviaQA",
    "webquestions": "WebQuestions",
    "quality": "QuALITY",
    "beir": "BEIR",
    "mteb": "MTEB",
}

RE_SPLIT = re.compile(
    r"\b(train(?:ing)?|dev(?:elopment)?|validation|test(?:ing)?)\s+split\b",
    re.I)
RE_LANGUAGE = re.compile(r"\b(English|Russian|Chinese|multilingual)\b", re.I)

# Задачи: только «question answering»-формулировки, без retrieval/generation.
RE_TASK = re.compile(
    r"\b(multi-?hop\s+(?:question\s+answering|QA)|"
    r"document[- ]grounded\s+(?:question\s+answering|QA)|"
    r"open[- ]domain\s+(?:question\s+answering|QA)|"
    r"question\s+answering|QA)\b", re.I)

# Эксперименты: известные baseline-системы, без «baselines»/«compared with».
RE_BASELINE_NAMES = re.compile(
    r"\b(GraphRAG|LightRAG|HippoRAG|IRCoT|Self-Ask|ReAct|ToG|PoG|"
    r"KnowTrace|RA-CoT|Iter-RetGen|CoTKR|EFSUM|ERA-CoT|"
    r"Naive\s*RAG|Vanilla\s*RAG)\b", re.I)

RE_HARDWARE = re.compile(
    r"\b(\d+\s*[x×]\s*(?:NVIDIA\s+)?(?:A100|H100|V100|A6000|RTX\s*\d+|"
    r"TPU|GPU|CPU)s?)\b", re.I)
RE_SAMPLE = re.compile(
    r"\b(\d+)\s*(?:test|dev|evaluation|queries|questions|examples|"
    r"samples|QA\s+pairs)\b", re.I)

RE_CITED = re.compile(
    r"(\[\s*\d+\s*\]|\bfrom\s+ref\.?\s*\[?\d+|"
    r"\bas\s+reported\s+in\b|\btaken\s+from\b|\bref\.?\s*\[?\d+\s*\]?)",
    re.I)
RE_SUPPLEMENTARY = re.compile(
    r"\b(supplementary|supporting\s+information|supplementary\s+"
    r"information|suppl\.\s*mater|esi)\b", re.I)

# Индикаторы, что в статье есть таблица/график с результатами.
RE_HAS_TABLE = re.compile(
    r"\b(?:Table|Таблица)\s*([0-9]+[A-Za-z]?)", re.I)
RE_HAS_FIG = re.compile(
    r"\b(?:Fig(?:ure)?\.?|Рис(?:унок)?\.?)\s*([0-9]+[A-Za-z]?)", re.I)
RE_RESULT_WORDS = re.compile(
    r"\b(?:EM|F1|BLEU|ROUGE|NDCG|MRR|Recall|Precision|UniEval|"
    r"Exact\s*Match|hit\s*rate|accuracy)\b", re.I)
RE_RESULT_TABLE_CAPTION = re.compile(
    r"\b(?:result|results|performance|evaluation|ablation|score|scores|"
    r"benchmark)\b", re.I)

# ---------------------------------------------------------------- helpers
def _number(value):
    s = str(value).strip().replace(" ", "")
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+", s):
        s = s.replace(",", "")
    else:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _normalize_metric(value, raw_unit, metric):
    if value is None:
        return None, None
    u = (raw_unit or "").strip().lower()
    if u == "%":
        return value / 100.0, "fraction"
    return value, "fraction"


def _normalize_latency(value, raw_unit):
    if value is None:
        return None, None
    u = (raw_unit or "").strip().lower()
    if u in ("s", "sec", "seconds", "second"):
        return value * 1000.0, "ms"
    return value, "ms"


def _context_source(text, match):
    start = max(0, match.start() - 400)
    end = min(len(text), match.end() + 400)
    window = text[start:end]
    m_t = RE_TABLE.search(window)
    m_f = RE_FIG.search(window)
    m_s = RE_SECTION.search(window)
    return (m_s.group(1) if m_s else None,
            m_t.group(1) if m_t else None,
            m_f.group(1) if m_f else None)


def _line_fragment(text, match):
    start = text.rfind("\n", 0, match.start()) + 1
    end = text.find("\n", match.end())
    if end == -1:
        end = len(text)
    frag = text[start:end].strip()
    return frag or match.group(0)


def _window_around(text, match_or_pos, radius=400):
    if hasattr(match_or_pos, "start"):
        s, e = match_or_pos.start(), match_or_pos.end()
    else:
        s = e = int(match_or_pos)
    return text[max(0, s - radius): min(len(text), e + radius)]


def _resolve_origin(text, match):
    win = _window_around(text, match, 250)
    m = RE_CITED.search(win)
    if not m:
        return "primary", None
    cited = re.search(r"\d+", m.group(0))
    return "cited", (cited.group(0) if cited else None)


def _resolve_status(text, match):
    win = _window_around(text, match, 300)
    if RE_SUPPLEMENTARY.search(win) and not re.search(r"\d", match.group(0)):
        return "present_not_extractable"
    return "extracted"


# ---------------------------------------------------------------- publication
RE_AUTHOR = re.compile(
    r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}(?:\s+[A-Z][a-z]+)?\b")
RE_AFFIL = re.compile(
    r"\b(universit|institut|college|school|academy|laborator|department|"
    r"key\s+lab|center\s+for|china|russia|usa|japan|korea|germany)\b", re.I)
RE_JOURNAL_NOISE = re.compile(
    r"(https?://|doi\b|journal\b|volume\b|received\b|accepted\b|"
    r"published\b|frontiers\b|copyright\b|issn\b|elsevier\b|"
    r"springer\b|wiley\b|rsc\b|adv\.\b|^\d+\s*$|"
    r"edited\s+by|reviewed\s+by|correspondence|"
    r"citation\s*:|specialty\s+section|approved\s+by|"
    r"^abstract\b)", re.I)


def _looks_like_title(line):
    s = (line or "").strip()
    if len(s) < 15 or len(s) > 300:
        return False
    if s.endswith("-"):
        return False
    if RE_JOURNAL_NOISE.search(s):
        return False
    if RE_AFFIL.search(s):
        return False
    words = s.split()
    caps = sum(1 for w in words if w[:1].isupper())
    return caps >= 2


def _extract_title(doc, lines):
    md_title = ((doc.doc.metadata or {}).get("title") or "").strip()
    if _looks_like_title(md_title) and not re.search(r"\d+\.\.\d+", md_title):
        return md_title
    for i in range(min(20, len(lines))):
        buf = lines[i]
        for j in range(i + 1, min(i + 4, len(lines))):
            cand = buf + " " + lines[j]
            if _looks_like_title(cand) and len(cand) >= 30:
                return cand
            buf = cand
        if _looks_like_title(buf):
            return buf
    return None


RE_ORG_WORDS = re.compile(
    r"\b(technology|business|science|engineering|academy|"
    r"laboratory|department|school|college|institute|university|"
    r"center|centre|key\s+lab|group|faculty)\b", re.I)
RE_INITIAL = re.compile(r"\b[A-Z]\.\s*[A-Z]?\.?")


def _extract_authors(lines):
    for line in lines[:30]:
        if not re.search(r"[A-Z][a-z]+", line):
            continue
        if RE_AFFIL.search(line) and line.count(",") < 2:
            continue
        if RE_ORG_WORDS.search(line):
            continue
        if not re.search(r",|\band\b", line):
            continue
        names = RE_AUTHOR.findall(line)
        names = [n for n in names if not RE_AFFIL.search(n)
                 and not RE_ORG_WORDS.search(n) and len(n) > 3]
        if len(names) >= 2 and (
                RE_INITIAL.search(line)
                or any(len(n.split()) >= 2 for n in names)):
            return "; ".join(names)
    return None


def parse_publication_rag(doc):
    pub_id = Path(doc.path).stem
    text0 = doc.pages_text[0] if doc.pages_text else ""
    lines = [l.strip() for l in text0.splitlines() if l.strip()]

    title = _extract_title(doc, lines)
    year = None
    m = re.search(r"\b(19|20)\d{2}\b", text0)
    if m:
        year = int(m.group(0))
    doi = None
    m = re.search(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\b", text0)
    if m:
        doi = m.group(0).rstrip(".,;)")
    authors = _extract_authors(lines)

    head = (text0[:4000] or "").lower()
    title_low = (title or "").lower()
    in_scope, reason = "true", ""
    if re.search(r"\b(survey|review|overview)\b", title_low) and not \
            re.search(r"\b(experiment|evaluation|results|benchmark)\b", head):
        in_scope, reason = "false", "survey without configuration and evaluation results"
    elif "rag" not in head and "retrieval augmented" not in head \
            and "retrieval-augmented" not in head:
        in_scope, reason = "false", "no RAG configuration or evaluation found"
    return {
        "publication_id": pub_id, "title": title, "year": year,
        "DOI": doi, "authors": authors, "in_scope": in_scope,
        "exclusion_reason": reason,
    }


# ---------------------------------------------------------------- configurations
def parse_configurations(doc, pub_id):
    text = "\n".join(doc.pages_text)
    out, seen = [], set()

    for m in RE_RAG_VARIANT.finditer(text):
        variant = m.group(0).strip()
        key = variant.lower()
        if key in seen:
            continue
        seen.add(key)

        window = _window_around(text, m, 800)

        embedding = None
        me = RE_EMBEDDING.search(window)
        if me:
            embedding = me.group(0)

        reranker = None
        mr = RE_RERANKER.search(window)
        if mr:
            reranker = mr.group(0)

        generator = None
        mg = RE_GENERATOR.search(window)
        if mg:
            generator = mg.group(0)

        retrieval = None
        mret = RE_RETRIEVAL.search(window)
        if mret:
            retrieval = mret.group(0)

        chunk_size, chunk_unit = None, None
        mc = RE_CHUNK.search(window)
        if mc:
            chunk_size = int(mc.group(1))
            chunk_unit = mc.group(2).lower()
            chunk_unit = {"characters": "characters",
                          "character": "characters",
                          "tokens": "tokens",
                          "token": "tokens",
                          "words": "words"}.get(chunk_unit, chunk_unit)

        chunk_overlap = None
        mo = RE_CHUNK_OVERLAP.search(window)
        if mo:
            chunk_overlap = int(mo.group(1))

        top_k = None
        mk = RE_TOPK.search(window)
        if mk:
            top_k = int(mk.group(1))

        index_type = None
        mi = RE_INDEX.search(window)
        if mi:
            index_type = mi.group(0)

        out.append({
            "publication_id": pub_id,
            "config_id": "C-%02d" % (len(out) + 1),
            "rag_variant": variant,
            "retrieval_method": retrieval,
            "retriever_model": None,
            "embedding_model": embedding,
            "embedding_version": None,
            "chunking_method": None,
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
            "chunk_unit": chunk_unit,
            "index_type": index_type,
            "vector_store": None,
            "top_k": top_k,
            "reranker_model": reranker,
            "generator_model": generator,
            "generator_version": None,
            "prompt_strategy": None,
            "context_strategy": None,
            "note": "auto-extracted; verify chunking and generator version on page",
        })
    return out


# ---------------------------------------------------------------- datasets
def parse_datasets(doc, pub_id):
    text = "\n".join(doc.pages_text)
    out, seen = [], set()
    for m in RE_DATASET.finditer(text):
        raw = m.group(0).strip()
        # Не считать обычное слово «quality» в нижнем регистре датасетом.
        if raw.lower() == "quality" and raw != "QuALITY":
            continue
        canon = DATASET_CANON.get(raw.lower(), raw)
        key = canon.lower()
        if key in seen:
            continue
        seen.add(key)
        win = _window_around(text, m, 200)
        split = None
        ms = RE_SPLIT.search(win)
        if ms:
            split = ms.group(1).lower()
        lang = None
        ml = RE_LANGUAGE.search(win)
        if ml:
            lang = ml.group(1).lower()
        out.append({
            "publication_id": pub_id,
            "dataset_id": "D-%02d" % (len(out) + 1),
            "dataset_name": canon,
            "dataset_version": None,
            "language": lang,
            "data_split": split,
            "scientific_domain": "RAG",
            "note": "",
        })
    return out


# ---------------------------------------------------------------- tasks
def parse_tasks(doc, pub_id):
    text = "\n".join(doc.pages_text)
    out, seen = [], set()
    # Приоритет: document-grounded и open-domain — это уточнение,
    # а не отдельная задача. Схлопываем к каноническим типам.
    canon_map = {
        "qa": "question answering",
        "question answering": "question answering",
        "multi-hop qa": "multi-hop question answering",
        "multi-hop question answering": "multi-hop question answering",
        "document-grounded qa": "document-grounded question answering",
        "document-grounded question answering":
            "document-grounded question answering",
        "open-domain qa": "open-domain question answering",
        "open-domain question answering":
            "open-domain question answering",
    }
    for m in RE_TASK.finditer(text):
        typ = re.sub(r"\s+", " ", m.group(0)).strip().lower()
        canon = canon_map.get(typ, typ)
        if canon in seen:
            continue
        seen.add(canon)
        out.append({
            "publication_id": pub_id,
            "task_id": "T-%02d" % (len(out) + 1),
            "task_type": canon,
            "note": "",
        })
    return out


# ---------------------------------------------------------------- experiments
def parse_experiments(doc, pub_id, configurations):
    text = "\n".join(doc.pages_text)
    hardware = None
    m = RE_HARDWARE.search(text)
    if m:
        hardware = m.group(1).strip()
    sample = None
    m = RE_SAMPLE.search(text)
    if m:
        sample = int(m.group(1))
    baseline = None
    m = RE_BASELINE_NAMES.search(text)
    if m:
        baseline = m.group(0)
    if not any([hardware, sample, baseline]):
        return []
    return [{
        "publication_id": pub_id,
        "experiment_id": "E-01",
        "evaluation_protocol": None,
        "baseline_name": baseline,
        "hardware": hardware,
        "latency_ms": None,
        "tokens_per_query": None,
        "sample_size": sample,
        "note": "auto-extracted; verify evaluation protocol and sample size",
    }]


# ---------------------------------------------------------------- results
def _pick_config_id(text, match, configurations):
    if not configurations:
        return None
    win = _window_around(text, match, 400).lower()
    for cfg in configurations:
        variant = (cfg.get("rag_variant") or "").lower()
        if variant and variant in win:
            return cfg.get("config_id")
    return configurations[0].get("config_id")


def _pick_dataset_id(text, match, datasets):
    if not datasets:
        return None
    win = _window_around(text, match, 400).lower()
    for ds in datasets:
        name = (ds.get("dataset_name") or "").lower()
        if name and name in win:
            return ds.get("dataset_id")
    return datasets[0].get("dataset_id")


def _pick_task_id(text, match, tasks):
    if not tasks:
        return None
    return tasks[0].get("task_id")


def _table_or_figure_issue(doc, pub_id, results_on_page, page_index, text):
    """Возвращает issue-dict для таблицы/рисунка с метриками, если
    на странице есть Table N / Figure N и слова метрик, но PATTERNS_RAG
    ничего не извлёк. Иначе None.

    Важно: результаты на странице не передаются, нужен факт,
    что их нет. results_on_page — bool.
    """
    if results_on_page:
        return None
    has_table = RE_HAS_TABLE.search(text)
    has_fig = RE_HAS_FIG.search(text)
    if not (has_table or has_fig):
        return None
    if not RE_RESULT_WORDS.search(text):
        return None
    ref = has_table or has_fig
    is_table = bool(has_table)
    caption_window = _window_around(text, ref, 400)
    if not RE_RESULT_TABLE_CAPTION.search(caption_window):
        return None
    kind = "table" if is_table else "figure"
    ref_id = ref.group(1) if ref.groups() else "?"
    fragment = _line_fragment(text, ref)
    return {
        "publication_id": pub_id,
        "issue_id": None,       # проставит вызывающий
        "record_ids": "",       # нет result_id — это не results
        "check_name": "present_not_extractable",
        "description": ("%s %s содержит метрики, но строковый парсер их "
                        "не извлёк; проверьте изображение страницы."
                        % (kind, ref_id)),
        "source_page": page_index + 1,
        "source_fragment": fragment,
    }


def extract_results_rag(doc, pub_id, configurations=None,
                        datasets=None, tasks=None, experiments=None,
                        issues_sink=None):
    """Только реально извлечённые метрики — в results. Таблицы/рисунки
    без извлечённых значений — в issues_sink (список), не в results."""
    configurations = configurations or []
    datasets = datasets or []
    tasks = tasks or []
    experiments = experiments or []
    experiment_id = experiments[0]["experiment_id"] if experiments else None

    records = []
    for page_index, text in enumerate(doc.pages_text):
        page_had_results = False
        for name, pattern, group, unit, direction in PATTERNS_RAG:
            for match in re.finditer(pattern, text, re.I):
                page_had_results = True
                groups = match.groups()
                if len(groups) >= 3 and name.endswith("@k"):
                    k = groups[0]
                    raw = groups[1]
                    raw_unit = groups[2]
                elif len(groups) >= 2 and name in ("MRR", "EM", "F1",
                                                   "BLEU", "ROUGE-L",
                                                   "UniEval"):
                    k = None
                    raw = groups[0]
                    raw_unit = groups[1] if len(groups) > 1 else None
                elif len(groups) >= 3 and name == "tokens_per_query":
                    raw = groups[0]
                    suffix = groups[1]
                    raw_unit = None
                    if suffix and suffix.lower() == "k":
                        raw = str(float(str(raw).replace(",", ".")) * 1000)
                    elif suffix and suffix.lower() == "m":
                        raw = str(float(str(raw).replace(",", ".")) * 1_000_000)
                    k = None
                elif len(groups) >= 2 and name == "latency":
                    raw = groups[0]
                    raw_unit = groups[1]
                    k = None
                else:
                    k = None
                    raw = groups[0]
                    raw_unit = groups[1] if len(groups) > 1 else None

                value = _number(raw)
                if name == "latency":
                    norm, norm_unit = _normalize_latency(value, raw_unit)
                elif name == "tokens_per_query":
                    norm, norm_unit = value, "tokens"
                else:
                    norm, norm_unit = _normalize_metric(value, raw_unit, name)

                section, table, figure = _context_source(text, match)
                origin, cited_id = _resolve_origin(text, match)
                status = _resolve_status(text, match)

                rec = {key: None for key in FIELDS_RAG["results"]}
                rec.update({
                    "publication_id": pub_id,
                    "result_id": str(uuid.uuid4())[:8],
                    "experiment_id": experiment_id,
                    "config_id": _pick_config_id(text, match, configurations),
                    "dataset_id": _pick_dataset_id(text, match, datasets),
                    "task_id": _pick_task_id(text, match, tasks),
                    "metric_group": group,
                    "metric_name": name,
                    "metric_variant": None,
                    "metric_direction": direction,
                    "metric_k": int(k) if k else None,
                    "metric_value": norm,
                    "metric_unit": norm_unit,
                    "baseline_value": None,
                    "aggregation": None,
                    "sample_size": None,
                    "raw_value": raw,
                    "raw_unit": raw_unit,
                    "normalized_value": norm,
                    "normalized_unit": norm_unit,
                    "result_origin": origin,
                    "cited_publication_id": cited_id,
                    "source_page": page_index + 1,
                    "source_section": section,
                    "source_table": table,
                    "source_figure": figure,
                    "source_fragment": _line_fragment(text, match),
                    "extraction_status": status,
                    "duplicate_of": None,
                    "note": "",
                })
                records.append(rec)

        if not page_had_results and issues_sink is not None:
            issue = _table_or_figure_issue(
                doc, pub_id, page_had_results, page_index, text)
            if issue is not None:
                issues_sink.append(issue)

    # duplicate_of — одинаковые (metric_name, metric_k, value, unit) в одной публикации
    buckets = {}
    for r in records:
        if not r.get("metric_name"):
            continue
        key = (r.get("metric_name"), r.get("metric_k"),
               r.get("normalized_value"), r.get("normalized_unit"))
        buckets.setdefault(key, []).append(r)
    for key, group in buckets.items():
        if len(group) < 2:
            continue
        first = group[0]
        for other in group[1:]:
            other["duplicate_of"] = first["result_id"]

    return records


# ---------------------------------------------------------------- validate
def validate_rag(record, results=None):
    findings = []
    pub = record.get("publication_id")
    rid = record.get("result_id")

    def flag(check_name, description, record_ids=None):
        findings.append({
            "publication_id": pub,
            "issue_id": None,
            "record_ids": record_ids or rid or "",
            "check_name": check_name,
            "description": description,
            "source_page": record.get("source_page"),
            "source_fragment": record.get("source_fragment"),
        })

    if not record.get("source_fragment") or not record.get("source_page"):
        flag("source_required", "Не указаны фрагмент источника или страница")

    val = _number(record.get("normalized_value"))
    metric = str(record.get("metric_name") or "")
    unit = record.get("normalized_unit")

    if val is not None and unit == "fraction" and not 0 <= val <= 1:
        flag("metric_scale",
             "%s = %.4f вне шкалы [0, 1] для доли" % (metric, val))
    if val is not None and metric in ("Recall@k", "Precision@k", "NDCG@k") \
            and record.get("metric_k") is None:
        flag("metric_k", "Метрика @k без указания k")

    if record.get("extraction_status") == "extracted":
        for field in ("experiment_id", "config_id", "dataset_id", "task_id"):
            if not record.get(field):
                flag("protocol_mismatch",
                     "Нет связи %s — результат нельзя сопоставить" % field)

    return findings


# ---------------------------------------------------------------- pipeline
def extract_publication_rag(doc):
    """Полный проход по одной статье: publications / configurations /
    datasets / tasks / experiments / results / issues."""
    pub_id = Path(doc.path).stem
    pub = parse_publication_rag(doc)
    configurations = parse_configurations(doc, pub_id)
    datasets = parse_datasets(doc, pub_id)
    tasks = parse_tasks(doc, pub_id)
    experiments = parse_experiments(doc, pub_id, configurations)

    issues = []
    results = extract_results_rag(
        doc, pub_id, configurations, datasets, tasks, experiments,
        issues_sink=issues)

    for r in results:
        issues.extend(validate_rag(r, results=results))

    # проставить issue_id
    for i, it in enumerate(issues, 1):
        it["issue_id"] = "I%d" % i

    return {
        "publications": [pub],
        "configurations": configurations,
        "datasets": datasets,
        "tasks": tasks,
        "experiments": experiments,
        "results": results,
        "issues": issues,
    }
