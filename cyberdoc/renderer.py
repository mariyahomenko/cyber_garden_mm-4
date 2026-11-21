import base64
import html
import io
import re

from .parser import PLACEHOLDER_RE, PAGE_CITE_RE
from . import theme

try:
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    HAS_MPL = True
except Exception:
    HAS_MPL = False

GREEK = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ",
    "epsilon": "ε", "zeta": "ζ", "eta": "η", "theta": "θ",
    "iota": "ι", "kappa": "κ", "lambda": "λ", "mu": "μ",
    "nu": "ν", "xi": "ξ", "pi": "π", "rho": "ρ", "sigma": "σ",
    "tau": "τ", "phi": "φ", "chi": "χ", "psi": "ψ", "omega": "ω",
    "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ",
    "Xi": "Ξ", "Pi": "Π", "Sigma": "Σ", "Phi": "Φ", "Psi": "Ψ",
    "Omega": "Ω",
}

SIMPLE_OPS = {
    "cdot": "·", "times": "×", "div": "÷", "pm": "±", "mp": "∓",
    "leq": "≤", "le": "≤", "geq": "≥", "ge": "≥",
    "neq": "≠", "approx": "≈", "equiv": "≡",
    "infty": "∞", "to": "→", "rightarrow": "→", "leftarrow": "←",
    "sum": "∑", "prod": "∏", "int": "∫",
    "partial": "∂", "nabla": "∇", "in": "∈",
    "ldots": "...", "cdots": "·", "sqrt": "√",
}


def latex_to_unicode(s: str) -> str:
    if not s:
        return s
    out = s
    for _ in range(4):
        new = re.sub(
            r"\\[dt]?frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}",
            lambda m: "(%s)/(%s)" % (m.group(1).strip(),
                                     m.group(2).strip()),
            out)
        if new == out:
            break
        out = new
    out = re.sub(r"\\sqrt\s*\{([^{}]*)\}", r"√(\1)", out)
    out = re.sub(r"\\sqrt\s*\[([^\]]*)\]\s*\{([^{}]*)\}",
                 r"(\2)^(1/\1)", out)
    out = re.sub(r"\\left\s*([\\{\|])", r"\1", out)
    out = re.sub(r"\\right\s*([\\{\|])", r"\1", out)
    out = re.sub(
        r"\\(?:text|mathrm|mathbf|mathit|mathbb|mathcal|operatorname)"
        r"\s*\{([^{}]*)\}", r"\1", out)
    for name, sym in GREEK.items():
        out = re.sub(r"\\" + name + r"\b", sym, out)
    for name, sym in SIMPLE_OPS.items():
        out = re.sub(r"\\" + name + r"\b", sym, out)
    out = re.sub(r"\\[a-zA-Z]+", "", out)
    out = out.replace("{", "").replace("}", "").replace("$", "")
    return out.strip()


class LatexRenderer:
    _cache = {}
    MAX_WIDTH_PX = 620
    BASE_DPI = 200
    BASE_FONTSIZE = 16

    # Конструкции, которые matplotlib mathtext НЕ поддерживает.
    # Их вырезаем и рисуем упрощённый вариант. Полноценно — только
    # настоящий LaTeX (texlive) или MathJax в браузере, но у нас QLabel.
    _UNSUPPORTED = [
        (r"\\begin\{[^{}]+\}", ""),
        (r"\\end\{[^{}]+\}", ""),
        (r"\\text\s*\{([^{}]*)\}", r"\1"),
        (r"\\operatorname\s*\{([^{}]*)\}", r"\1"),
        (r"\\mathbb\s*\{([^{}]*)\}", r"\1"),
        (r"\\mathcal\s*\{([^{}]*)\}", r"\1"),
        (r"\\mathrm\s*\{([^{}]*)\}", r"\1"),
        (r"\\left\s*", ""),
        (r"\\right\s*", ""),
        (r"\\,", " "),
        (r"\\;", " "),
        (r"\\!", ""),
        (r"\\quad", " \u2003 "),
        (r"\\qquad", " \u2003\u2003 "),
    ]

    @classmethod
    def _sanitize_for_mpl(cls, latex: str) -> str:
        s = latex
        for pat, rep in cls._UNSUPPORTED:
            s = re.sub(pat, rep, s)
        # mpl не любит пустые {} в индексах
        s = re.sub(r"\^\s*\{\s*\}", "", s)
        s = re.sub(r"_\s*\{\s*\}", "", s)
        # немного сжать длинные пробелы
        s = re.sub(r"\s{2,}", " ", s).strip()
        return s

    @classmethod
    def _render_png(cls, latex: str, color: str, fontsize: int):
        if not HAS_MPL:
            return None
        try:
            fig = Figure(figsize=(0.01, 0.01), dpi=cls.BASE_DPI)
            FigureCanvasAgg(fig)
            fig.patch.set_alpha(0.0)
            fig.text(0, 0, "$%s$" % latex,
                     fontsize=fontsize, color=color)
            fig.canvas.draw()
            buf = io.BytesIO()
            fig.savefig(buf, format="png", transparent=True,
                        bbox_inches="tight", pad_inches=0.05)
            return buf.getvalue()
        except Exception:
            return None

    @classmethod
    def render_to_html(cls, latex: str, color: str = None,
                       fontsize: int = None) -> str:
        if color is None:
            color = theme.html_colors()["formula"]
        latex = (latex or "").strip()
        if not latex:
            return ""
        fontsize = fontsize or cls.BASE_FONTSIZE
        key = (latex, color, fontsize)
        if key in cls._cache:
            return cls._cache[key]

        img_html = None
        if HAS_MPL:
            # Сначала пробуем как есть (простые формулы рендерятся идеально)
            png = cls._render_png(latex, color, fontsize)
            if png is None:
                # Чистим конструкции, ломающие mathtext
                cleaned = cls._sanitize_for_mpl(latex)
                if cleaned and cleaned != latex:
                    png = cls._render_png(cleaned, color, fontsize)
            if png is not None:
                w_px = None
                try:
                    from PIL import Image
                    with Image.open(io.BytesIO(png)) as im:
                        w_px = im.size[0]
                except Exception:
                    pass
                b64 = base64.b64encode(png).decode("ascii")
                style = ("vertical-align:middle; display:inline-block;"
                         "max-width:100%; height:auto;")
                if w_px:
                    style += "width:%dpx;" % min(w_px, cls.MAX_WIDTH_PX)
                img_html = (
                    '<img src="data:image/png;base64,%s" '
                    'style="%s margin:2px 0;" />' % (b64, style))

        if img_html is None:
            # Совсем не отрендерилось — выводим «красивый юникод»
            pretty = html.escape(latex_to_unicode(latex))
            img_html = (
                '<span style="color:%s; font-family:\'Cambria Math\', '
                '\'STIXGeneral\', \'DejaVu Serif\', serif; '
                'font-size:%dpx;">%s</span>'
                % (color, fontsize, pretty))
        cls._cache[key] = img_html
        return img_html


def render_answer_html(text: str, formulas, anchors,
                       doc_name: str = None) -> str:
    formulas = formulas or []
    anchors = anchors or []
    colors = theme.html_colors()
    t = html.escape(text)

    placeholder_map = {}
    counter = [0]

    def _formula_placeholder(m):
        idx = int(m.group(1))
        if idx >= len(formulas):
            return ""
        ph = "\x01F%d\x01" % counter[0]
        counter[0] += 1
        placeholder_map[ph] = idx
        return ph

    t = PLACEHOLDER_RE.sub(_formula_placeholder, t)

    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<!\*)\*(?!\*)([^*\n]+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", t)
    t = re.sub(r"^#{1,3}\s*(.*)$", r"<h3>\1</h3>", t, flags=re.M)

    link_style = ('style="color:%s; text-decoration:none;"'
                  % colors["link"])
    anchor_ptr = [0]

    def _cite(m):
        n = int(m.group(1))
        ai = None
        j = anchor_ptr[0]
        while j < len(anchors):
            if anchors[j]["page"] == n:
                ai = j
                break
            j += 1
        if ai is not None:
            anchor_ptr[0] = ai + 1
            return ('<a href="anchor:%d" %s>[стр. %d]</a>'
                    % (ai, link_style, n))
        return ('<a href="page:%d" %s>[стр. %d]</a>'
                % (n, link_style, n))

    t = PAGE_CITE_RE.sub(_cite, t)

    def _formula_block(idx):
        if idx >= len(formulas):
            return ""
        f = formulas[idx]
        img = LatexRenderer.render_to_html(f["latex"])
        page = f.get("page")
        s = ('<div style="background-color:%s; padding:6px 10px; '
             'margin:6px 0; border-radius:8px; max-width:100%%; '
             'white-space:normal; word-wrap:break-word; overflow:hidden;">'
             % colors["block"])
        s += img + " "
        if page is not None:
            s += ('<a href="formula:%d" style="color:%s; '
                  'text-decoration:none; font-size:12px;">[стр. %d]</a>'
                  % (idx, colors["link"], page))
        return s + "</div>"

    result_lines = []
    buf = []

    def flush():
        if buf:
            result_lines.append("".join(buf))
            buf.clear()

    for ln in t.split("\n"):
        phs = re.findall(r"\x01F(\d+)\x01", ln)
        if not phs:
            buf.append(ln + "\n")
            continue
        rest = ln
        for ph in phs:
            idx = placeholder_map.get("\x01F%s\x01" % ph)
            if idx is None:
                continue
            before, rest = rest.split("\x01F%s\x01" % ph, 1)
            if before.strip():
                buf.append(before)
            flush()
            result_lines.append(_formula_block(idx))
            buf.append(rest)
        buf.append("\n")
    flush()

    t = "\n".join(result_lines) if result_lines else ""

    header = ""
    if doc_name:
        header = (
            '<div style="background-color:%s; padding:4px 10px; '
            'margin-bottom:8px; border-radius:8px; font-size:12px; '
            'color:%s;"><b>Файл:</b> %s</div>'
            % (colors["block"], colors["hint"], html.escape(str(doc_name))))

    return ('<div style="color:%s; font-size:14px; line-height:1.5; '
            'white-space:normal; word-wrap:break-word;">%s%s</div>'
            % (colors["text"], header, t))
