import re

FORMULA_RE = re.compile(
    r"\[\[\s*FORMULA\s+p\.?\s*(\d+)\s*:\s*(.*?)\s*\]\]", re.S | re.I)
REF_RE = re.compile(
    r'\[\[\s*REF\s+p\.?\s*(\d+)\s*:\s*"(.*?)"\s*\]\]', re.S | re.I)
PAGES_RE = re.compile(
    r"\[\[\s*PAGES\s*:?\s*start=(\d+)\s*,\s*end=(\d+)\s*,\s*total=(\d+)\s*\]\]",
    re.S | re.I)
START_PAGE_RE = re.compile(
    r"\[\[\s*START_PAGE\s*:?\s*(\d+)\s*\]\]", re.S | re.I)
PLACEHOLDER_RE = re.compile(r"\x00FORMULAIDX(\d+)\x00")
PAGE_CITE_RE = re.compile(r"\[стр\.\s*(\d+)\]")


def parse_answer(raw: str) -> dict:
    """Возвращает dict: text, formulas, anchors, pages."""
    pages = None
    m = PAGES_RE.search(raw)
    if m:
        pages = {"start": int(m.group(1)), "end": int(m.group(2)),
                 "total": int(m.group(3))}
        raw = PAGES_RE.sub("", raw)
    raw = START_PAGE_RE.sub("", raw)

    anchors = []

    def _repl_ref(m):
        anchors.append({"page": int(m.group(1)),
                        "quote": m.group(2).strip()})
        return ""

    raw = REF_RE.sub(_repl_ref, raw)

    formulas = []

    def _append(latex, page=None) -> str:
        latex = (latex or "").strip()
        if not latex:
            return ""
        idx = len(formulas)
        formulas.append({"page": page, "latex": latex})
        return "\x00FORMULAIDX%d\x00" % idx

    def _repl_formula(m):
        return _append(m.group(2), int(m.group(1)))

    raw = FORMULA_RE.sub(_repl_formula, raw)
    raw = re.sub(r"\$\$(.+?)\$\$",
                 lambda m: _append(m.group(1)), raw, flags=re.S)
    raw = re.sub(r"\$(.+?)\$",
                 lambda m: _append(m.group(1)), raw, flags=re.S)
    raw = re.sub(r"\\\[(.+?)\\\]",
                 lambda m: _append(m.group(1)), raw, flags=re.S)
    raw = re.sub(r"\\\((.+?)\\\)",
                 lambda m: _append(m.group(1)), raw, flags=re.S)
    raw = re.sub(r"\\begin\{([^{}]+)\}.*?\\end\{\1\}",
                 lambda m: _append(m.group(0)), raw, flags=re.S)

    return {"text": raw.strip(), "formulas": formulas,
            "anchors": anchors, "pages": pages}
