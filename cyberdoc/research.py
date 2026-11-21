"""Evidence-first structured extraction for the VINITI/YuFU specification.

Этап 2: парсер структуры темы 1.

* publications: title / year / DOI / authors (мягкие эвристики);
* materials: формула, класс, размерность, добавки, Eg;
* devices: архитектура, подложка, площадь, инкапсуляция, роль;
* layers: порядок, функция, материал, толщина, метод осаждения,
  отжиг, атмосфера;
* measurements: тип, спектр, интенсивность, scan direction/rate,
  маска, сертификация, температура, протокол старения;
* results связываются с device_id / measurement_id / material_id,
  если те определены рядом (иначе — None, без догадок).

Неизвестное остаётся пустым. source_fragment — дословная подстрока
страницы (требование tools/check_submission.py).
"""
import json
import re
import uuid
from pathlib import Path

SOLAR = "solar"
RAG = "rag"

FIELDS = {
    SOLAR: [
        "publication_id", "title", "year", "doi", "authors",
        "material_id", "material_name_raw", "formula_normalized",
        "material_class", "dimensionality", "additives",
        "bandgap_value", "bandgap_unit", "bandgap_method",
        "device_id", "device_label", "device_role", "device_type",
        "architecture", "substrate_type", "active_area", "area_unit",
        "area_definition", "encapsulation",
        "layer_id", "layer_order", "layer_function", "layer_material",
        "layer_thickness", "thickness_unit", "deposition_method",
        "annealing_temperature", "annealing_time", "atmosphere",
        "measurement_id", "measurement_type", "spectrum", "light_intensity",
        "scan_direction", "scan_rate", "mask_used", "certified",
        "temperature", "stability_protocol", "stress_conditions",
        "metric_name", "metric_value", "metric_unit", "aggregation",
        "spread_value", "n_devices", "time_point", "time_unit",
        "raw_value", "raw_unit", "normalized_value", "normalized_unit",
        "result_origin", "cited_publication_id",
        "source_page", "source_section", "source_table", "source_figure",
        "source_fragment", "extraction_status",
    ],
    RAG: [
        "publication_id", "title", "year", "doi", "authors",
        "config_id", "rag_variant", "retrieval_method",
        "embedding_model", "embedding_version",
        "chunking_method", "chunk_size", "chunk_overlap", "chunk_unit",
        "index_type", "vector_store", "top_k",
        "reranker_model",
        "generator_model", "generator_version",
        "dataset_id", "dataset_name", "dataset_version",
        "task_id", "task_type", "language", "scientific_domain",
        "experiment_id", "evaluation_protocol", "baseline_name",
        "metric_name", "metric_variant", "metric_direction",
        "metric_k", "metric_value", "metric_unit", "baseline_value",
        "raw_value", "raw_unit", "normalized_value", "normalized_unit",
        "result_origin", "cited_publication_id",
        "source_page", "source_section", "source_table", "source_figure",
        "source_fragment", "extraction_status",
    ],
}

PATTERNS = {
    SOLAR: [
        ("PCE", r"\b(?:PCE|power conversion efficiency)\s*(?:=|:|of|was)?\s*(\d+(?:[.,]\d+)?)\s*(%)", "%"),
        ("Voc", r"\b(?:V[_ ]?oc|open.circuit voltage)\s*(?:=|:|of|was)?\s*(\d+(?:[.,]\d+)?)\s*(mV|V)\b", "V"),
        ("Jsc", r"\b(?:J[_ ]?sc|short.circuit current density)\s*(?:=|:|of|was)?\s*(\d+(?:[.,]\d+)?)\s*(mA/cm2|mA/cm²|A/m2|A/m²)", "mA/cm²"),
        ("FF", r"\b(?:FF|fill factor)\s*(?:=|:|of|was)?\s*(\d+(?:[.,]\d+)?)\s*(%)", "%"),
        ("Rs", r"\bR[_ ]?s\s*(?:=|:)\s*(\d+(?:[.,]\d+)?)\s*(m?\s*ohm|Ω|ohm)", "ohm"),
        ("Rsh", r"\bR[_ ]?sh\s*(?:=|:)\s*(\d+(?:[.,]\d+)?)\s*(k?\s*ohm|Ω|ohm)", "ohm"),
        ("T80", r"\bT80\s*(?:=|:)\s*(\d+(?:[.,]\d+)?)\s*(h|hours?)", "h"),
        ("Eg", r"\b(?:E[_ ]?g|band.?gap)\s*(?:=|:|of|was|~|≈)?\s*(\d+(?:[.,]\d+)?)\s*(eV|эВ)\b", "eV"),
        ("Jsc_EQE", r"\bJ[_ ]?sc[,\s]*(?:from\s+)?EQE\s*(?:=|:|of|was)?\s*(\d+(?:[.,]\d+)?)\s*(mA/cm2|mA/cm²)", "mA/cm²"),
        ("Area", r"\b(?:active\s+area|area)\s*(?:=|:|of|was)?\s*(\d+(?:[.,]\d+)?)\s*(cm2|cm²|mm2|mm²|m2|m²)", "cm²"),
        ("LightIntensity", r"\b(?:AM\s*1\.?5G[,\s]*)?(\d+(?:[.,]\d+)?)\s*(mW/cm2|mW/cm²|W/m2|W/m²)\b", "mW/cm²"),
        ("Thickness", r"(\d+(?:[.,]\d+)?)\s*(nm|нм)\b", "nm"),
        ("ScanDirection", r"\b(?:scan(?:ned)?\s+(?:from|at)|sweep(?:ed)?\s+from)\s+(forward|reverse)\b", None),
        ("ScanRate", r"\bscan\s+rate\s*(?:of)?\s*(\d+(?:[.,]\d+)?)\s*(V\s*s[-−]?1|V/s|mV/s)", "V/s"),
        ("Architecture", r"\b(n-i-p|p-i-n|nip|pin|substrate|superstrate)\b", None),
        ("Substrate", r"\b(glass|ITO|FTO|flexible|PET|metal)\s+(?:substrate|glass)?\b", None),
        ("MaterialClass", r"\b(perovskite|CIGS|CdTe|kesterite|Sb2Se3|CZTS|thin.?film\s+Si)\b", None),
        ("Dimensionality", r"\b(2D|3D)\s+(?:perovskite|layer)\b", None),
        ("Certified", r"\b(certified|certification|сертифиц\w*)\b", None),
    ],
    RAG: [
        ("Recall@k", r"\bRecall\s*@\s*(\d+)\s*(?:=|:)\s*(\d+(?:[.,]\d+)?)\s*(%)?", None),
        ("Precision@k", r"\bPrecision\s*@\s*(\d+)\s*(?:=|:)\s*(\d+(?:[.,]\d+)?)\s*(%)?", None),
        ("MRR", r"\bMRR\s*(?:=|:)\s*(\d+(?:[.,]\d+)?)\s*(%)?", None),
        ("NDCG", r"\bNDCG\s*(?:@\s*(\d+))?\s*(?:=|:)\s*(\d+(?:[.,]\d+)?)\s*(%)?", None),
    ],
}

NORMALIZATION_RULES = {
    "SOLAR": {
        "PCE": {"unit": "%", "note": "0..100"},
        "FF": {"unit": "%", "note": "0..100"},
        "Voc": {"unit": "V", "note": "mV / 1000"},
        "Jsc": {"unit": "mA/cm²", "note": "A/m² / 10"},
        "Jsc_EQE": {"unit": "mA/cm²", "note": "A/m² / 10"},
        "Eg": {"unit": "eV", "note": "как есть"},
        "Area": {"unit": "cm²", "note": "mm² / 100, m² × 10000"},
        "LightIntensity": {"unit": "mW/cm²", "note": "W/m² / 10"},
        "Thickness": {"unit": "nm", "note": "как есть"},
        "T80": {"unit": "h", "note": "как есть"},
    },
    "RAG": {
        "Recall": {"unit": "fraction", "note": "% / 100"},
        "Precision": {"unit": "fraction", "note": "% / 100"},
        "MRR": {"unit": "fraction", "note": "% / 100"},
        "NDCG": {"unit": "fraction", "note": "% / 100"},
    },
}

COMPARISON_RULES = {
    "SOLAR": (
        "Сравниваются результаты при совпадении: класс материала, тип "
        "прибора, условия AM1.5G 100 мВт/см², сопоставимая площадь "
        "(±10 %), агрегация и направление развёртки. Сертифицированные "
        "значения и стабильность сравниваются отдельно."
    ),
    "RAG": (
        "Сравнение с baseline допускается только при совпадении "
        "dataset_id, task_id и evaluation_protocol."
    ),
}

RE_TABLE = re.compile(r"\b(?:Table|Таблица)\s*([0-9]+[A-Za-z]?)", re.I)
RE_FIG = re.compile(r"\b(?:Fig(?:ure)?\.?|Рис(?:унок)?\.?)\s*([0-9]+[A-Za-z]?)", re.I)
RE_SECTION = re.compile(r"\b(?:Section|Раздел)\s*([0-9]+(?:\.[0-9]+)*)", re.I)

# --- эвристики для структуры ---
RE_FORMULA = re.compile(
    r"\b((?:FA|MA|Cs|Rb|K|Pb|Sn|Bi|Sb|Ag|Cu|Zn|Cd|In|Ga|Se|S|I|Br|Cl)"
    r"(?:[A-Z][a-z]?\d*){1,10})\b")
RE_DEVICE_LABEL = re.compile(
    r"\b(champion|best|control|reference|pristine|target|record|device)\b",
    re.I)
RE_LAYER_ROW = re.compile(
    r"(?P<mat>[A-Z][A-Za-z0-9().\-/]{1,30})\s*[,\-—]?\s*"
    r"(?P<th>\d+(?:[.,]\d+)?)\s*(?P<unit>nm|нм)\b")
RE_DEPOSITION = re.compile(
    r"\b(spin[- ]?coated|spin[- ]?coating|evaporated|sputtered|"
    r"ALD|CVD|PVD|drop[- ]?cast|doctor[- ]?blade|slot[- ]?die)\b", re.I)
RE_ANNEAL = re.compile(
    r"\b(?:annealed|annealing)\s*(?:at)?\s*(\d{2,4})\s*°?\s*C"
    r"(?:\s*for\s*(\d+(?:[.,]\d+)?)\s*(min|minutes|h|hours))?", re.I)
RE_MASK = re.compile(r"\b(?:mask|aperture|shadow\s+mask)\b", re.I)
RE_CERT = re.compile(r"\b(certified|certification|сертифиц\w*)\b", re.I)
RE_TEMP = re.compile(r"\b(?:at|temperature\s+of)\s*(\d{2,3})\s*(?:K|°C)\b", re.I)
RE_STAB = re.compile(r"\b(T80|MPP|maximum\s+power\s+point|damp[- ]heat|"
                     r"thermal\s+stress|light\s+soaking)\b", re.I)


def _number(value):
    try:
        return float(str(value).replace(",", "."))
    except (ValueError, TypeError):
        return None


def _normalize_unit(value, unit, metric):
    if value is None:
        return None, unit
    u = (unit or "").strip().lower()
    if metric in ("PCE", "FF"):
        return value, "%"
    if metric == "Voc":
        return (value / 1000.0, "V") if u == "mv" else (value, "V")
    if metric in ("Jsc", "Jsc_EQE"):
        if u in ("a/m2", "a/m²"):
            return value / 10.0, "mA/cm²"
        return value, "mA/cm²"
    if metric == "Eg":
        return value, "eV"
    if metric == "Area":
        if u in ("mm2", "mm²"):
            return value / 100.0, "cm²"
        if u in ("m2", "m²"):
            return value * 10000.0, "cm²"
        return value, "cm²"
    if metric == "LightIntensity":
        if u in ("w/m2", "w/m²"):
            return value / 10.0, "mW/cm²"
        return value, "mW/cm²"
    if metric == "Thickness":
        return value, "nm"
    if metric == "ScanRate":
        if u == "mv/s":
            return value / 1000.0, "V/s"
        return value, "V/s"
    return value, unit


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


# ======================================================================
# publications
# ======================================================================
def parse_publication(doc):
    """Мягкие эвристики для title / year / DOI / authors.

    Неизвестное — None. Не выдумываем.
    """
    pub_id = Path(doc.path).stem
    text0 = (doc.pages_text[0] if doc.pages_text else "")
    first = [l.strip() for l in text0.splitlines() if l.strip()]

    title = None
    for line in first[:15]:
        low = line.lower()
        if (len(line) > 20 and "http" not in low
                and not line.startswith("=")
                and not re.match(r"^[A-Z][a-z]+ \d+", line)
                and "journal" not in low
                and "volume" not in low):
            title = line
            break

    year = None
    m = re.search(r"\b(19|20)\d{2}\b", text0)
    if m:
        year = int(m.group(0))

    doi = None
    m = re.search(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\b", text0)
    if m:
        doi = m.group(0).rstrip(".,;)")

    authors = None
    for line in first[:20]:
        if "," in line and re.search(r"[A-Z][a-z]+ [A-Z]", line) \
                and "university" not in line.lower() \
                and "institute" not in line.lower() \
                and "china" not in line.lower() \
                and "journal" not in line.lower():
            candidates = [a.strip() for a in line.split(",") if a.strip()]
            names = [a for a in candidates if re.match(r"^[A-Z][\w.\-]+\s+[A-Z]", a)]
            if len(names) >= 2:
                authors = "; ".join(candidates)
                break

    in_scope = "true"
    exclusion_reason = ""
    low_all = "\n".join(doc.pages_text).lower()
    if "tandem" in low_all:
        in_scope = "false"
        exclusion_reason = "tandem devices are out of scope"

    return {
        "publication_id": pub_id,
        "title": title,
        "year": year,
        "DOI": doi,
        "authors": authors,
        "in_scope": in_scope,
        "exclusion_reason": exclusion_reason,
    }


# ======================================================================
# materials
# ======================================================================
def parse_materials(doc, pub_id):
    """Формула, класс, размерность, добавки, Eg. Без догадок."""
    text = "\n".join(doc.pages_text)
    out = []
    seen = set()

    # Каждая формула — отдельный материал-кандидат.
    for m in RE_FORMULA.finditer(text):
        formula = m.group(1)
        if formula.lower() in seen:
            continue
        # отбрасываем очевидно нехимические строки
        if not re.search(r"[A-Z][a-z]?", formula) or len(formula) < 3:
            continue
        seen.add(formula.lower())
        cls = None
        low = text.lower()
        if "perovskite" in low:
            cls = "perovskite"
        elif "cigs" in low:
            cls = "CIGS"
        elif "cdte" in low:
            cls = "CdTe"
        elif "kesterite" in low or "czts" in low:
            cls = "kesterite"
        elif "sb2se3" in low:
            cls = "Sb2Se3"
        dim = None
        mdim = re.search(r"\b(2D|3D)\s+(?:perovskite|layer)", text, re.I)
        if mdim:
            dim = mdim.group(1).upper()

        eg = None
        eg_unit = None
        meg = re.search(
            r"\b(?:E[_ ]?g|band.?gap)\s*(?:=|:|of|was|~|≈)?\s*(\d+(?:[.,]\d+)?)\s*(eV|эВ)\b",
            text, re.I)
        if meg:
            eg = _number(meg.group(1))
            eg_unit = "eV"

        additives = None
        madd = re.search(r"\b(?:doped|doping|additive|additives)\s+with\s+([A-Za-z0-9₂₃₄\- ]{2,40})", text, re.I)
        if madd:
            additives = madd.group(1).strip()

        out.append({
            "publication_id": pub_id,
            "material_id": "M-%d" % (len(out) + 1),
            "material_name_raw": m.group(0),
            "formula_normalized": formula,
            "material_class": cls,
            "dimensionality": dim,
            "additives": additives,
            "bandgap_value": eg,
            "bandgap_unit": eg_unit,
            "bandgap_method": None,
            "note": "",
        })
    return out


# ======================================================================
# devices
# ======================================================================
def parse_devices(doc, pub_id, materials):
    """Архитектура, подложка, площадь, роль, инкапсуляция."""
    text = "\n".join(doc.pages_text)
    out = []
    seen = set()

    arch = None
    m = re.search(r"\b(n-i-p|p-i-n|nip|pin|substrate|superstrate)\b", text, re.I)
    if m:
        arch = m.group(1).lower()

    substrate = None
    m = re.search(r"\b(glass|ITO|FTO|flexible|PET|metal)\s+(?:substrate|glass)?\b", text, re.I)
    if m:
        substrate = m.group(1)

    area = None
    area_unit = None
    m = re.search(r"\b(?:active\s+area|area)\s*(?:=|:|of|was)?\s*(\d+(?:[.,]\d+)?)\s*(cm2|cm²|mm2|mm²|m2|m²)", text, re.I)
    if m:
        area, area_unit = _normalize_unit(
            _number(m.group(1)), m.group(2), "Area")

    area_def = None
    if re.search(r"\b(?:aperture|shadow\s+mask|mask)\b", text, re.I):
        area_def = "masked"

    encaps = None
    if re.search(r"\bencapsulat", text, re.I):
        encaps = "encapsulated"

    # Один общий прибор, если явно не сказано иное.
    if arch or substrate or area or "device" in text.lower():
        mat_id = materials[0]["material_id"] if materials else None
        out.append({
            "publication_id": pub_id,
            "device_id": "DEV-1",
            "absorber_material_id": mat_id,
            "device_label": "device",
            "device_role": "target",
            "device_type": "single-junction",
            "architecture": arch,
            "substrate_type": substrate,
            "active_area": area,
            "area_unit": area_unit,
            "area_definition": area_def,
            "encapsulation": encaps,
            "note": "",
        })
    return out


# ======================================================================
# layers
# ======================================================================
def parse_layers(doc, pub_id, devices):
    """Слои: порядок, функция, материал, толщина, метод, отжиг, атмосфера.

    Консервативно: только строки «material thickness nm» и явные роли.
    """
    text = "\n".join(doc.pages_text)
    out = []
    seen = set()
    device_id = devices[0]["device_id"] if devices else None

    role_hints = {
        "compact tio2": "ETL", "c-tio2": "ETL", "tio2": "ETL",
        "sno2": "ETL", "zno": "ETL",
        "perovskite": "absorber", "cspb": "absorber", "mapb": "absorber",
        "fapb": "absorber",
        "spiro": "HTL", "p3ht": "HTL", "pedot": "HTL", "nio": "HTL",
        "ag": "contact", "au": "contact", "gold": "contact", "silver": "contact",
        "ito": "contact", "fto": "contact",
    }

    # Явные пары «материал + толщина».
    for m in RE_LAYER_ROW.finditer(text):
        mat = m.group("mat").strip()
        th = _number(m.group("th"))
        unit = "nm"
        key = (mat.lower(), th)
        if key in seen:
            continue
        seen.add(key)
        func = None
        for hint, role in role_hints.items():
            if hint in mat.lower():
                func = role
                break
        dep = None
        mdep = RE_DEPOSITION.search(text)
        if mdep:
            dep = mdep.group(1).lower()
        an_temp = None
        an_time = None
        an_unit = None
        man = RE_ANNEAL.search(text)
        if man:
            an_temp = int(man.group(1))
            if man.group(2):
                an_time = _number(man.group(2))
                an_unit = man.group(3)
        atm = None
        if re.search(r"\bglove\s*box|nitrogen|n2\b", text, re.I):
            atm = "N2"
        out.append({
            "publication_id": pub_id,
            "layer_id": "L-%d" % (len(out) + 1),
            "device_id": device_id,
            "layer_order": len(out) + 1,
            "layer_function": func,
            "layer_material": mat,
            "layer_thickness": th,
            "thickness_unit": unit,
            "deposition_method": dep,
            "annealing_temperature": an_temp,
            "annealing_time": an_time,
            "atmosphere": atm,
            "note": ("annealing_time_unit=" + str(an_unit)) if an_unit else "",
        })
    return out


# ======================================================================
# measurements
# ======================================================================
def parse_measurements(doc, pub_id, devices):
    """Условия измерения: тип, спектр, интенсивность, scan, маска, серт."""
    text = "\n".join(doc.pages_text)
    device_id = devices[0]["device_id"] if devices else None
    out = []
    seen = set()

    m_type = None
    if re.search(r"\bJ-?V\b", text):
        m_type = "J-V"
    elif re.search(r"\bEQE\b", text):
        m_type = "EQE"

    spectrum = "AM1.5G" if re.search(r"AM\s*1\.?5G", text, re.I) else None

    intensity = None
    intensity_unit = None
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(mW/cm2|mW/cm²|W/m2|W/m²)", text, re.I)
    if m:
        intensity, intensity_unit = _normalize_unit(
            _number(m.group(1)), m.group(2), "LightIntensity")

    scan_dir = None
    m = re.search(r"\b(forward|reverse)\s+scan\b", text, re.I)
    if m:
        scan_dir = m.group(1).lower()

    scan_rate = None
    m = re.search(r"scan\s+rate\s*(?:of)?\s*(\d+(?:[.,]\d+)?)\s*(V\s*s[-−]?1|V/s|mV/s)", text, re.I)
    if m:
        scan_rate, _u = _normalize_unit(_number(m.group(1)), m.group(2), "ScanRate")

    mask = bool(RE_MASK.search(text))
    cert = bool(RE_CERT.search(text))

    temp = None
    m = RE_TEMP.search(text)
    if m:
        temp = int(m.group(1))

    stab = None
    m = RE_STAB.search(text)
    if m:
        stab = m.group(1)

    if not any([m_type, spectrum, intensity, scan_dir, mask, cert, temp, stab]):
        return out

    key = (m_type, spectrum, intensity, scan_dir, scan_rate, mask, cert, temp, stab)
    if key in seen:
        return out
    seen.add(key)

    out.append({
        "publication_id": pub_id,
        "measurement_id": "MEAS-1",
        "device_id": device_id,
        "measurement_type": m_type,
        "spectrum": spectrum,
        "light_intensity": intensity,
        "intensity_unit": intensity_unit,
        "scan_direction": scan_dir,
        "scan_rate": scan_rate,
        "mask_used": mask,
        "certified": cert,
        "certification_lab": None,
        "temperature": temp,
        "stability_protocol": stab,
        "stress_conditions": None,
        "note": "",
    })
    return out


# ======================================================================
# results (как в Этапе 1 + привязка к device_id / measurement_id)
# ======================================================================
def extract_candidates(doc, domain, devices=None, measurements=None,
                       materials=None):
    """Regex-извлечение. source_fragment — дословная подстрока страницы."""
    if domain not in FIELDS:
        raise ValueError("Unknown domain")

    records = []
    pub_id = Path(doc.path).stem
    device_id = devices[0]["device_id"] if devices else None
    measurement_id = measurements[0]["measurement_id"] if measurements else None
    material_id = materials[0]["material_id"] if materials else None

    for page_index, text in enumerate(doc.pages_text):
        for name, pattern, target_unit in PATTERNS[domain]:
            for match in re.finditer(pattern, text, re.I):
                groups = match.groups()
                if domain == RAG and name in ("Recall@k", "Precision@k", "NDCG"):
                    k = groups[0] if len(groups) >= 2 else None
                    raw = groups[1] if len(groups) >= 2 else groups[0]
                    raw_unit = groups[2] if len(groups) >= 3 else None
                else:
                    k = None
                    raw = groups[0]
                    raw_unit = groups[1] if len(groups) >= 2 else None

                raw_unit = raw_unit or ("fraction" if domain == RAG else None)
                value = _number(raw)
                normalized, normalized_unit = _normalize_unit(value, raw_unit, name)

                fragment = _line_fragment(text, match)
                section, table, figure = _context_source(text, match)

                record = {key: None for key in FIELDS[domain]}
                record.update({
                    "result_id": str(uuid.uuid4()),
                    "domain": domain,
                    "publication_id": pub_id,
                    "source_file": doc.path,
                    "source_page": page_index + 1,
                    "source_section": section,
                    "source_table": table,
                    "source_figure": figure,
                    "source_fragment": fragment,
                    "result_origin": "primary",
                    "cited_publication_id": None,
                    "metric_name": name,
                    "metric_k": int(k) if k else None,
                    "metric_value": normalized,
                    "metric_unit": normalized_unit,
                    "raw_value": raw,
                    "raw_unit": raw_unit,
                    "normalized_value": normalized,
                    "normalized_unit": normalized_unit,
                    "extraction_status": "candidate",
                    "device_id": device_id,
                    "measurement_id": measurement_id,
                    "material_id": material_id,
                })
                records.append(record)

    return records


def field_coverage(records, domain):
    fields = FIELDS.get(domain, [])
    total = len(records)
    cov = {}
    for f in fields:
        filled = sum(1 for r in records if r.get(f) is not None)
        cov[f] = {"filled": filled, "null": total - filled,
                  "ratio": (filled / total) if total else 0.0}
    return cov


def validate(record):
    findings = []

    def flag(rule, message):
        findings.append({
            "rule": rule,
            "message": message,
            "record_id": record.get("result_id"),
            "publication_id": record.get("publication_id"),
            "source_page": record.get("source_page"),
            "source_fragment": record.get("source_fragment"),
        })

    if not record.get("source_fragment") or not record.get("source_page"):
        flag("SOURCE_REQUIRED", "Не указаны фрагмент источника или страница")

    val_raw = record.get("raw_value")
    if val_raw is None or str(val_raw).strip() in ("", "n/a", "N/A"):
        flag("NO_INFERENCE", "Значение отсутствует — не восстанавливается по догадке")

    val = _number(record.get("normalized_value"))
    metric = str(record.get("metric_name") or "")
    unit = record.get("normalized_unit")

    if val is not None:
        if record.get("domain") == SOLAR:
            if metric in ("PCE", "FF") and unit == "%" and not 0 <= val <= 100:
                flag("PERCENT_RANGE", "Процент вне диапазона 0–100")
            if metric == "Voc" and val < 0:
                flag("VOC_RANGE", "Отрицательное напряжение Voc")
            if metric == "Jsc" and val < 0:
                flag("JSC_RANGE", "Отрицательная плотность тока")
            if metric in ("Voc", "Jsc", "FF", "PCE") and record.get("measurement_type") is None:
                flag("CONTEXT_REQUIRED", "Для фотоэлектрического результата не указан режим измерения")
            if metric == "PCE" and unit == "%":
                pin = _number(record.get("light_intensity"))
                if pin is not None and pin <= 0:
                    flag("PIN_RANGE", "Мощность освещения должна быть положительной")
        elif record.get("domain") == RAG:
            if metric.lower().startswith(("recall", "precision", "mrr", "ndcg")):
                limit = 100 if unit == "%" else 1 if unit in ("fraction", "доля") else None
                if limit is None:
                    flag("UNKNOWN_SCALE", "Шкала метрики не установлена")
                elif not 0 <= val <= limit:
                    flag("METRIC_RANGE", "Метрика вне допустимой шкалы")

    if record.get("extraction_status") == "candidate":
        flag("REVIEW_REQUIRED", "Автоматически найденное значение требует проверки")

    return findings


# ======================================================================
# сборка и экспорт
# ======================================================================
def extract_publication(doc):
    """Полный проход по одной статье: pub / materials / devices /
    layers / measurements / results."""
    pub = parse_publication(doc)
    materials = parse_materials(doc, pub["publication_id"])
    devices = parse_devices(doc, pub["publication_id"], materials)
    layers = parse_layers(doc, pub["publication_id"], devices)
    measurements = parse_measurements(doc, pub["publication_id"], devices)
    results = extract_candidates(
        doc, SOLAR, devices=devices, measurements=measurements,
        materials=materials)
    issues = []
    for r in results:
        issues.extend(validate(r))
    return {
        "publication": pub,
        "materials": materials,
        "devices": devices,
        "layers": layers,
        "measurements": measurements,
        "results": results,
        "issues": issues,
    }


def export_dataset(path, records, domain):
    selected = [r for r in records if r.get("domain") == domain]
    findings = [f for r in selected for f in validate(r)]
    payload = {
        "passport": {
            "name": "CyberDoc evidence dataset",
            "version": "0.5",
            "domain": domain,
            "fields": FIELDS[domain],
            "unknown_values": "null; never inferred",
            "status_values": ["candidate", "verified", "rejected"],
            "normalization_rules": NORMALIZATION_RULES.get(domain.upper(), {}),
            "comparison_rules": COMPARISON_RULES.get(domain.upper(), ""),
            "coverage": field_coverage(selected, domain),
        },
        "records": selected,
        "validation_findings": findings,
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    return len(selected), len(findings)


def export_submission_csv(out_dir, doc, records=None, domain=SOLAR,
                          publication_meta=None):
    """Заполняет 7 CSV формата сдачи по одной статье.

    Если records не переданы — делает полный проход `extract_publication`.
    """
    from . import submission_export

    full = extract_publication(doc)
    if records is not None:
        full["results"] = records
    pub_id = full["publication"]["publication_id"]

    publications = [{
        "publication_id": pub_id,
        "title": full["publication"].get("title"),
        "year": full["publication"].get("year"),
        "DOI": full["publication"].get("DOI"),
        "authors": full["publication"].get("authors"),
        "in_scope": full["publication"].get("in_scope", "true"),
        "exclusion_reason": full["publication"].get("exclusion_reason", ""),
    }]

    materials = full["materials"]
    devices = full["devices"]
    layers = full["layers"]
    measurements = full["measurements"]

    results = []
    issues = []
    for r in full["results"]:
        if r.get("domain") != domain:
            continue
        results.append({
            "publication_id": r.get("publication_id"),
            "result_id": r.get("result_id"),
            "device_id": r.get("device_id"),
            "measurement_id": r.get("measurement_id"),
            "material_id": r.get("material_id"),
            "metric_name": r.get("metric_name"),
            "metric_value": r.get("metric_value"),
            "metric_unit": r.get("metric_unit"),
            "aggregation": r.get("aggregation"),
            "spread_value": r.get("spread_value"),
            "n_devices": r.get("n_devices"),
            "time_point": r.get("time_point"),
            "time_unit": r.get("time_unit"),
            "raw_value": r.get("raw_value"),
            "raw_unit": r.get("raw_unit"),
            "normalized_value": r.get("normalized_value"),
            "normalized_unit": r.get("normalized_unit"),
            "result_origin": r.get("result_origin") or "primary",
            "cited_publication_id": r.get("cited_publication_id"),
            "source_page": r.get("source_page"),
            "source_section": r.get("source_section"),
            "source_table": r.get("source_table"),
            "source_figure": r.get("source_figure"),
            "source_fragment": r.get("source_fragment"),
            "extraction_status": r.get("extraction_status") or "candidate",
            "duplicate_of": r.get("duplicate_of"),
            "note": "",
        })

    for f in full["issues"]:
        issues.append({
            "publication_id": f.get("publication_id"),
            "issue_id": str(uuid.uuid4()),
            "record_ids": f.get("record_id"),
            "check_name": f.get("rule"),
            "description": f.get("message"),
            "source_page": f.get("source_page"),
            "source_fragment": f.get("source_fragment"),
        })

    return submission_export.export_submission(
        out_dir,
        publications=publications,
        materials=materials,
        devices=devices,
        layers=layers,
        measurements=measurements,
        results=results,
        issues=issues,
    )
