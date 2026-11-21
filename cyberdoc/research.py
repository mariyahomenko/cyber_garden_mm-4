"""Evidence-first structured extraction for the VINITI/YuFU specification.
No missing values are inferred. Candidate records must be reviewed by a human.
"""
import csv
import json
import re
import uuid
from pathlib import Path

SOLAR = "solar"
RAG = "rag"
FIELDS = {
    SOLAR: ["publication_id", "title", "year", "doi", "authors", "material_id",
            "material_name_raw", "formula_normalized", "material_class", "dimensionality",
            "additives", "bandgap_value", "bandgap_unit", "bandgap_method", "device_id",
            "device_label", "device_role", "device_type", "architecture", "substrate_type",
            "active_area", "area_unit", "area_definition", "encapsulation", "layer_id",
            "layer_order", "layer_function", "layer_material", "layer_thickness",
            "thickness_unit", "deposition_method", "annealing_temperature", "annealing_time",
            "atmosphere", "measurement_id", "measurement_type", "spectrum", "light_intensity",
            "scan_direction", "scan_rate", "mask_used", "certified", "temperature",
            "stability_protocol", "stress_conditions", "metric_name", "metric_value",
            "metric_unit", "aggregation", "spread_value", "n_devices", "time_point",
            "time_unit", "raw_value", "raw_unit", "normalized_value", "normalized_unit"],
    RAG: ["publication_id", "config_id", "rag_variant", "retrieval_method", "embedding_model",
          "chunking_method", "chunk_size", "chunk_overlap", "index_type", "vector_store",
          "top_k", "reranker_model", "generator_model", "dataset_id", "task_id",
          "experiment_id", "evaluation_protocol", "metric_name", "metric_variant",
          "metric_direction", "metric_k", "metric_value", "metric_unit", "baseline_value",
          "raw_value", "raw_unit", "normalized_value", "normalized_unit"],
}
# Explicit patterns only; a matching number is a candidate, not a verified fact.
PATTERNS = {
 SOLAR: [
  ("PCE", r"\b(?:PCE|power conversion efficiency)\s*(?:=|:|of|was)?\s*(\d+(?:[.,]\d+)?)\s*(%)", "%"),
  ("Voc", r"\b(?:V[_ ]?oc|open.circuit voltage)\s*(?:=|:|of|was)?\s*(\d+(?:[.,]\d+)?)\s*(mV|V)\b", "V"),
  ("Jsc", r"\b(?:J[_ ]?sc|short.circuit current density)\s*(?:=|:|of|was)?\s*(\d+(?:[.,]\d+)?)\s*(mA/cm2|mA/cm²|A/m2|A/m²)", "mA/cm²"),
  ("FF", r"\b(?:FF|fill factor)\s*(?:=|:|of|was)?\s*(\d+(?:[.,]\d+)?)\s*(%)", "%"),
  ("Rs", r"\bR[_ ]?s\s*(?:=|:)\s*(\d+(?:[.,]\d+)?)\s*(m?\s*ohm|Ω|ohm)", "ohm"),
  ("Rsh", r"\bR[_ ]?sh\s*(?:=|:)\s*(\d+(?:[.,]\d+)?)\s*(k?\s*ohm|Ω|ohm)", "ohm"),
  ("T80", r"\bT80\s*(?:=|:)\s*(\d+(?:[.,]\d+)?)\s*(h|hours?)", "h"),
 ],
 RAG: [
  ("Recall@k", r"\bRecall\s*@\s*(\d+)\s*(?:=|:)\s*(\d+(?:[.,]\d+)?)\s*(%)?", None),
  ("Precision@k", r"\bPrecision\s*@\s*(\d+)\s*(?:=|:)\s*(\d+(?:[.,]\d+)?)\s*(%)?", None),
  ("MRR", r"\bMRR\s*(?:=|:)\s*(\d+(?:[.,]\d+)?)\s*(%)?", None),
  ("NDCG", r"\bNDCG\s*(?:@\s*(\d+))?\s*(?:=|:)\s*(\d+(?:[.,]\d+)?)\s*(%)?", None),
 ]
}

def _number(value):
    try: return float(str(value).replace(",", "."))
    except (ValueError, TypeError): return None

def validate(record):
    """Return non-destructive, source-linked findings."""
    findings=[]
    def flag(rule, message):
        findings.append({"rule":rule,"message":message,"record_id":record.get("result_id"),
                         "publication_id":record.get("publication_id"),"source_page":record.get("source_page"),
                         "source_fragment":record.get("source_fragment")})
    if not record.get("source_fragment") or not record.get("source_page"):
        flag("SOURCE_REQUIRED", "Не указаны фрагмент источника или страница")
    val=_number(record.get("normalized_value"))
    metric=str(record.get("metric_name") or "")
    unit=record.get("normalized_unit")
    if val is not None:
        if record.get("domain")==SOLAR:
            if metric in ("PCE","FF") and unit=="%" and not 0<=val<=100:
                flag("PERCENT_RANGE", "Процент вне диапазона 0–100")
            if metric=="Voc" and val<0:flag("VOC_RANGE", "Отрицательное напряжение Voc")
            if metric=="Jsc" and val<0:flag("JSC_RANGE", "Отрицательная плотность тока")
            if metric in ("Voc", "Jsc", "FF", "PCE") and record.get("measurement_type") is None:
                flag("CONTEXT_REQUIRED", "Для фотоэлектрического результата не указан режим измерения")
            if metric == "PCE" and unit == "%":
                pin = _number(record.get("light_intensity"))
                if pin is not None and pin <= 0:
                    flag("PIN_RANGE", "Мощность освещения должна быть положительной")
        elif record.get("domain")==RAG:
            if metric.lower().startswith(("recall", "precision", "mrr", "ndcg")):
                limit=100 if unit=="%" else 1 if unit in ("fraction", "доля") else None
                if limit is None:flag("UNKNOWN_SCALE", "Шкала метрики не установлена")
                elif not 0<=val<=limit:flag("METRIC_RANGE", "Метрика вне допустимой шкалы")
    if record.get("extraction_status")=="candidate":
        flag("REVIEW_REQUIRED", "Автоматически найденное значение требует проверки")
    return findings

def extract_candidates(doc, domain):
    """Conservative regex extraction from original PDF text; no LLM assumptions."""
    if domain not in FIELDS:raise ValueError("Unknown domain")
    records=[]
    pub_id=Path(doc.path).stem
    for page_index,text in enumerate(doc.pages_text):
        for name,pattern,target_unit in PATTERNS[domain]:
            for match in re.finditer(pattern,text,re.I):
                groups=match.groups()
                if domain==RAG and name in ("Recall@k","Precision@k"):
                    k,raw,raw_unit=groups
                elif domain==RAG and name=="NDCG":
                    k,raw,raw_unit=groups
                else:
                    k=None;raw,raw_unit=groups
                raw_unit=raw_unit or ("fraction" if domain==RAG else None)
                value=_number(raw)
                normalized=value; normalized_unit=raw_unit
                if domain==SOLAR and name=="Voc" and raw_unit=="mV":
                    normalized=value/1000;normalized_unit="V"
                elif domain==SOLAR and name=="Jsc" and raw_unit in ("A/m2","A/m²"):
                    normalized=value/10;normalized_unit="mA/cm²"
                elif domain==RAG and raw_unit=="%":
                    normalized=value/100;normalized_unit="fraction"
                start=max(0,match.start()-90);end=min(len(text),match.end()+90)
                record={key:None for key in FIELDS[domain]}
                record.update({"result_id":str(uuid.uuid4()),"domain":domain,"publication_id":pub_id,
                  "source_file":doc.path,"source_page":page_index+1,"source_section":None,
                  "source_table":None,"source_figure":None,"source_fragment":text[start:end].strip(),
                  "result_origin":"unknown", "cited_publication_id":None,
                  "metric_name":name,"metric_k":int(k) if k else None,"metric_value":normalized,
                  "metric_unit":normalized_unit,"raw_value":raw,"raw_unit":raw_unit,
                  "normalized_value":normalized,"normalized_unit":normalized_unit,
                  "extraction_status":"candidate"})
                records.append(record)
    return records

def export_dataset(path, records, domain):
    selected=[r for r in records if r.get("domain")==domain]
    findings=[f for r in selected for f in validate(r)]
    payload={"passport":{"name":"CyberDoc evidence dataset", "version":"0.2",
      "domain":domain,"fields":FIELDS[domain],
      "source_page":"1-based physical PDF page", "unknown_values":"null; never inferred",
      "status_values":["candidate","verified","rejected"],
      "note":"Candidates require manual verification; not an evaluated gold dataset"},
      "records":selected,"validation_findings":findings}
    with open(path,"w",encoding="utf-8") as fh:json.dump(payload,fh,ensure_ascii=False,indent=2)
    return len(selected),len(findings)
