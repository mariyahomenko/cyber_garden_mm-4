import csv
import json
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
    fields = ["type", "param", "value", "unit", "page", "doc"]
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


# =====================================================================
# Структура данных по ТЗ (общая задача и структура данных):
# публикация / набор и задача / конфигурация RAG / эксперимент /
# результат метрики / статус записи. Фиксируются только параметры,
# реально используемые системой; неизвестные значения не выдумываются.
# =====================================================================

def build_tz_dataset(app_name, version, client, provider, docs, history):
    """Формирует машиночитаемый набор данных по структуре ТЗ.

    docs: {path: PDFDocument}; history: список ответов (entry)."""
    publication = {
        "publication_id": "P-%s" % app_name.upper(),
        "title": "%s — AI-ассистент по научным статьям" % app_name,
        "year": time.localtime().tm_year,
        "DOI": None,
        "authors": [],
    }
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
    datasets = []
    experiments = []
    results = []
    eid = 0
    for path, d in docs.items():
        dataset = {
            "dataset_id": "D-%d" % (len(datasets) + 1),
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
            experiments.append({
                "experiment_id": "E-%d" % eid,
                "evaluation_protocol": "extraction of factual answers "
                                       "with page citations",
                "baseline_name": None,
                "hardware": None,
                "latency_ms": None,
                "tokens_per_query": None,
                "sample_size": 1,
                "publication_id": publication["publication_id"],
                "config_id": config["config_id"],
                "dataset_id": dataset["dataset_id"],
                **generation,
            })
            results.append({
                "result_id": "R-%d" % eid,
                "experiment_id": "E-%d" % eid,
                "config_id": config["config_id"],
                "dataset_id": dataset["dataset_id"],
                "task_id": "T-qa",
                "metric_group": "extraction",
                "metric_name": "answers_collected",
                "metric_variant": None,
                "metric_direction": "n/a",
                "metric_k": None,
                "metric_value": 1,
                "metric_unit": "answer",
                "baseline_value": None,
                "aggregation": "count",
                "sample_size": 1,
                "publication_id": publication["publication_id"],
                "result_origin": "primary",
                "cited_publication_id": None,
                "source_page": None,
                "source_section": None,
                "source_table": None,
                "source_figure": None,
                "source_fragment": (e.get("question") or "")[:200],
                "raw_value": 1, "raw_unit": "answer",
                "normalized_value": 1, "normalized_unit": "answer",
                "extraction_status": "auto",
            })
    return {
        "passport": {
            "name": "%s dataset" % app_name,
            "version": version,
            "subject_area": "RAG configurations and evaluation results",
            "description": "Machine-readable records of the RAG system "
                           "configuration and answer-extraction results; "
                           "unknown fields are null and are not guessed.",
        },
        "publication": publication,
        "configurations": [config],
        "datasets": datasets,
        "experiments": experiments,
        "results": results,
    }


def export_tz_json(path, *args, **kwargs):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(build_tz_dataset(*args, **kwargs), f,
                  ensure_ascii=False, indent=2)
