"""Экспорт извлечённых записей в формат сдачи (7 CSV).

Колонки — строго как в submission_template. Значения, которых нет,
остаются пустыми (не додумываются). source_fragment — дословная
подстрока страницы PDF (это проверяет tools/check_submission.py).
"""
import csv
import os

# Порядок и состав колонок — из submission_template.
COLUMNS = {
    "publications.csv": [
        "publication_id", "title", "year", "DOI", "authors",
        "in_scope", "exclusion_reason",
    ],
    "materials.csv": [
        "publication_id", "material_id", "material_name_raw",
        "formula_normalized", "material_class", "dimensionality",
        "additives", "bandgap_value", "bandgap_unit", "bandgap_method",
        "note",
    ],
    "devices.csv": [
        "publication_id", "device_id", "absorber_material_id",
        "device_label", "device_role", "device_type", "architecture",
        "substrate_type", "active_area", "area_unit", "area_definition",
        "encapsulation", "note",
    ],
    "layers.csv": [
        "publication_id", "layer_id", "device_id", "layer_order",
        "layer_function", "layer_material", "layer_thickness",
        "thickness_unit", "deposition_method", "annealing_temperature",
        "annealing_time", "atmosphere", "note",
    ],
    "measurements.csv": [
        "publication_id", "measurement_id", "device_id",
        "measurement_type", "spectrum", "light_intensity",
        "intensity_unit", "scan_direction", "scan_rate", "mask_used",
        "certified", "certification_lab", "temperature",
        "stability_protocol", "stress_conditions", "note",
    ],
    "results.csv": [
        "publication_id", "result_id", "device_id", "measurement_id",
        "material_id", "metric_name", "metric_value", "metric_unit",
        "aggregation", "spread_value", "n_devices", "time_point",
        "time_unit", "raw_value", "raw_unit", "normalized_value",
        "normalized_unit", "result_origin", "cited_publication_id",
        "source_page", "source_section", "source_table", "source_figure",
        "source_fragment", "extraction_status", "duplicate_of", "note",
    ],
    "issues.csv": [
        "publication_id", "issue_id", "record_ids", "check_name",
        "description", "source_page", "source_fragment",
    ],
}


def _write_csv(path, rows, columns):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") if r.get(c) is not None else ""
                        for c in columns})


def export_submission(out_dir, publications, materials, devices,
                      layers, measurements, results, issues):
    """Раскладывает по 7 CSV в out_dir. Возвращает пути файлов."""
    os.makedirs(out_dir, exist_ok=True)
    payload = {
        "publications.csv": publications,
        "materials.csv": materials,
        "devices.csv": devices,
        "layers.csv": layers,
        "measurements.csv": measurements,
        "results.csv": results,
        "issues.csv": issues,
    }
    written = []
    for name, rows in payload.items():
        path = os.path.join(out_dir, name)
        _write_csv(path, rows, COLUMNS[name])
        written.append(path)
    return written
