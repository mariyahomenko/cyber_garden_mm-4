"""Экспорт: ответы (JSON), сущности (CSV), набор по ТЗ (JSON + CSV×7)."""
import csv
import json
import os
import time

from .client import PROVIDERS


def export_json(path, doc_path, history, bookmarks):
    data = {
        "document": doc_path,
        "answers": history,
        "bookmarks": bookmarks,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def export_csv(path, rows):
    """Старый плоский экспорт сущностей из EntityPanel (не формат ТЗ)."""
    fields = ["type", "param", "value", "unit", "page", "doc"]
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


# =====================================================================
# Экспорт набора по ТЗ: 7 CSV в формате submission_template +
# машиночитаемый JSON с паспортом.
# =====================================================================

CSV_FIELDS = {
    "publications": ["publication_id", "title", "year", "DOI", "authors",
                     "in_scope", "exclusion_reason"],
    "materials": ["publication_id", "material_id", "material_name_raw",
                  "formula_normalized", "material_class", "dimensionality",
                  "additives", "bandgap_value", "bandgap_unit",
                  "bandgap_method"],
    "devices": ["publication_id", "device_id", "absorber_material_id",
                "device_label", "device_role", "device_type", "architecture",
                "substrate_type", "active_area", "area_unit",
                "area_definition", "encapsulation", "note"],
    "layers": ["publication_id", "layer_id", "device_id", "layer_order",
               "layer_function", "layer_material", "layer_thickness",
               "thickness_unit", "deposition_method", "annealing_temperature",
               "annealing_time", "atmosphere", "note"],
    "measurements": ["publication_id", "measurement_id", "device_id",
                     "measurement_type", "spectrum", "light_intensity",
                     "intensity_unit", "scan_direction", "scan_rate",
                     "mask_used", "certified", "temperature",
                     "stability_protocol", "stress_conditions", "note"],
    "results": ["publication_id", "result_id", "device_id", "measurement_id",
                "material_id", "metric_name", "metric_value", "metric_unit",
                "aggregation", "spread_value", "n_devices", "time_point",
                "time_unit", "raw_value", "raw_unit", "normalized_value",
                "normalized_unit", "result_origin", "cited_publication_id",
                "duplicate_of", "source_page", "source_section",
                "source_table", "source_figure", "source_fragment",
                "extraction_status"],
    "issues": ["publication_id", "issue_id", "record_ids", "check_name",
               "description", "source_page", "source_fragment"],
}


def export_submission_csv(folder, workspace):
    """Пишет 7 CSV формата сдачи в папку folder.

    workspace — dict с ключами publications/materials/devices/layers/
    measurements/results/issues (например, из research.export_workspace
    или ResearchDialog.data). Возвращает список записанных файлов.
    """
    os.makedirs(folder, exist_ok=True)
    written = []
    for key, cols in CSV_FIELDS.items():
        path = os.path.join(folder, "%s.csv" % key)
        rows = workspace.get(key, []) or []
        with open(path, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            for row in rows:
                clean = {}
                for c in cols:
                    v = row.get(c)
                    if isinstance(v, (list, tuple)):
                        v = ";".join(str(x) for x in v)
                    clean[c] = "" if v is None else v
                w.writerow(clean)
        written.append("%s.csv" % key)
    return written


def build_tz_dataset(app_name, version, client, provider, docs, history):
    """JSON-представление набора по ТЗ (RAG-домен).

    publication_id — имя файла без расширения (правило ТЗ).
    Неизвестные поля — null, не догадки.
    """
    from pathlib import Path

    config = {
        "config_id": "C-1",
        "rag_variant": "lexical-ranking-v1",
        "retrieval_method": "tf-idf cosine ranking over page chunks",
        "retriever_model": None,
        "embedding_model": None,
        "embedding_version": None,
        "chunking_method": "by page",
        "chunk_size": None,
        "chunk_overlap": None,
        "chunk_unit": "page",
        "index_type": "none (in-memory token counters)",
        "vector_store": None,
        "top_k": 12,
        "reranker_model": None,
    }
    generation = {
        "generator_model": getattr(client, "model", None),
        "generator_version": provider,
        "prompt_strategy": "system-prompt with page markers and formula anchors",
        "context_strategy": "top-ranked pages, sequential numbering",
    }

    publications, datasets, experiments, results = [], [], [], []
    eid = 0
    for path, d in docs.items():
        pub_id = Path(path).stem  # правило ТЗ: имя файла без расширения
        publications.append({
            "publication_id": pub_id,
            "title": getattr(d, "name", None),
            "year": None, "DOI": None, "authors": [],
            "in_scope": "true", "exclusion_reason": "",
        })
        dataset = {
            "dataset_id": "D-%s" % pub_id,
            "dataset_name": d.name,
            "dataset_version": None,
            "task_id": "T-qa",
            "task_type": "question answering over document",
            "language": None,
            "data_split": None,
            "scientific_domain": None,
        }
        datasets.append(dataset)
        for e in history:
            if e.get("path") != path:
                continue
            eid += 1
            exp_id = "E-%d" % eid
            experiments.append({
                "experiment_id": exp_id,
                "evaluation_protocol": "extraction of factual answers "
                                       "with page citations",
                "baseline_name": None,
                "hardware": None,
                "latency_ms": None,
                "tokens_per_query": None,
                "sample_size": 1,
                "publication_id": pub_id,
                "config_id": config["config_id"],
                "dataset_id": dataset["dataset_id"],
                **generation,
            })
            results.append({
                "result_id": "R-%d" % eid,
                "experiment_id": exp_id,
                "config_id": config["config_id"],
                "dataset_id": dataset["dataset_id"],
                "task_id": "T-qa",
                "metric_group": "extraction",
                "metric_name": None,      # не выдумываем метрику
                "metric_variant": None,
                "metric_direction": None,
                "metric_k": None,
                "metric_value": None,
                "metric_unit": None,
                "baseline_value": None,
                "aggregation": None,
                "sample_size": 1,
                "publication_id": pub_id,
                "result_origin": "primary",
                "cited_publication_id": None,
                "source_page": None,
                "source_section": None,
                "source_table": None,
                "source_figure": None,
                "source_fragment": (e.get("question") or "")[:200],
                "raw_value": None, "raw_unit": None,
                "normalized_value": None, "normalized_unit": None,
                "extraction_status": "candidate",
            })

    return {
        "passport": {
            "name": "%s dataset" % app_name,
            "version": version,
            "subject_area": "RAG configurations and evaluation results",
            "description": "Machine-readable records of the RAG system "
                           "configuration; unknown fields are null and "
                           "are not guessed.",
        },
        "publications": publications,
        "configurations": [config],
        "datasets": datasets,
        "experiments": experiments,
        "results": results,
    }


def export_tz_json(path, *args, **kwargs):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(build_tz_dataset(*args, **kwargs), f,
                  ensure_ascii=False, indent=2)
