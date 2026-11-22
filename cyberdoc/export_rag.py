"""Экспорт RAG-домена в формат сдачи: 7 CSV по submission_template/schema.json."""
import csv
import os

from .research_rag import CSV_FIELDS_RAG


def _write_csv(path, rows, columns):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: ("" if r.get(c) is None else r.get(c))
                        for c in columns})


def export_rag_submission(out_dir, workspace):
    """Раскладывает по 7 CSV в out_dir. workspace — dict с ключами
    publications/configurations/datasets/tasks/experiments/results/issues.
    Возвращает список путей."""
    os.makedirs(out_dir, exist_ok=True)
    written = []
    for table, columns in CSV_FIELDS_RAG.items():
        rows = workspace.get(table, []) or []
        path = os.path.join(out_dir, table + ".csv")
        _write_csv(path, rows, columns)
        written.append(path)
    return written


def build_rag_workspace(docs):
    """Собирает workspace по всем открытым документам."""
    from .research_rag import extract_publication_rag
    data = {k: [] for k in CSV_FIELDS_RAG}
    for doc in docs.values():
        full = extract_publication_rag(doc)
        for key in data:
            data[key].extend(full.get(key, []) or [])
    return data
