"""Research data review and export window (7 tabs per TZ).

Каждая вкладка = одна таблица формата сдачи (submission_template).
Данные — из research.extract_publication (solar) или
research_rag.extract_publication_rag (RAG).
Экспорт — 7 CSV + JSON.
Двойной клик по строке — переход в PDF с подсветкой фрагмента и дубликатов.
"""
import csv
import json
import os

from PyQt5 import QtCore, QtWidgets

from . import theme
from .research import (
    SOLAR, RAG, extract_publication, validate, import_workspace,
)
from .research_rag import (
    extract_publication_rag, CSV_FIELDS_RAG,
)
from .export_rag import export_rag_submission

# Колонки вкладки «Результаты» в UI (в CSV — только машинные поля)
RESULT_UI_COLS = [
    "publication_id", "result_id", "device_id", "measurement_id",
    "material_id", "metric_name", "metric_value", "metric_unit",
    "aggregation", "spread_value", "n_devices", "time_point",
    "time_unit", "raw_value", "raw_unit", "normalized_value",
    "normalized_unit", "result_origin", "cited_publication_id",
    "duplicate_of", "source_page", "source_section",
    "source_table", "source_figure", "source_fragment",
    "extraction_status", "duplicate_info",
]

TABS = [
    ("Публикации", "publications", [
        "publication_id", "title", "year", "DOI", "authors",
        "in_scope", "exclusion_reason"]),
    ("Материалы", "materials", [
        "publication_id", "material_id", "material_name_raw",
        "formula_normalized", "material_class", "dimensionality",
        "additives", "bandgap_value", "bandgap_unit",
        "bandgap_method"]),
    ("Приборы", "devices", [
        "publication_id", "device_id", "absorber_material_id",
        "device_label", "device_role", "device_type", "architecture",
        "substrate_type", "active_area", "area_unit",
        "area_definition", "encapsulation", "note"]),
    ("Слои", "layers", [
        "publication_id", "layer_id", "device_id", "layer_order",
        "layer_function", "layer_material", "layer_thickness",
        "thickness_unit", "deposition_method", "annealing_temperature",
        "annealing_time", "atmosphere", "note"]),
    ("Измерения", "measurements", [
        "publication_id", "measurement_id", "device_id",
        "measurement_type", "spectrum", "light_intensity",
        "intensity_unit", "scan_direction", "scan_rate",
        "mask_used", "certified", "temperature",
        "stability_protocol", "stress_conditions", "note"]),
    ("Результаты", "results", RESULT_UI_COLS),
    ("Замечания", "issues", [
        "publication_id", "issue_id", "record_ids", "check_name",
        "description", "source_page", "source_fragment"]),
]

# UI-вкладки для RAG-домена (порядок и колонки — из schema.json).
RAG_TABS = [
    ("Публикации", "publications", CSV_FIELDS_RAG["publications"]),
    ("Конфигурации", "configurations", CSV_FIELDS_RAG["configurations"]),
    ("Наборы", "datasets", CSV_FIELDS_RAG["datasets"]),
    ("Задачи", "tasks", CSV_FIELDS_RAG["tasks"]),
    ("Эксперименты", "experiments", CSV_FIELDS_RAG["experiments"]),
    ("Результаты", "results", CSV_FIELDS_RAG["results"]),
    ("Замечания", "issues", CSV_FIELDS_RAG["issues"]),
]

CSV_NAMES = {
    "publications": "publications.csv",
    "materials": "materials.csv",
    "devices": "devices.csv",
    "layers": "layers.csv",
    "measurements": "measurements.csv",
    "results": "results.csv",
    "issues": "issues.csv",
}

# Поля, которые пишутся в CSV (машинный формат без UI-полей)
CSV_FIELDS = {
    "publications": [
        "publication_id", "title", "year", "DOI", "authors",
        "in_scope", "exclusion_reason"],
    "materials": [
        "publication_id", "material_id", "material_name_raw",
        "formula_normalized", "material_class", "dimensionality",
        "additives", "bandgap_value", "bandgap_unit", "bandgap_method"],
    "devices": [
        "publication_id", "device_id", "absorber_material_id",
        "device_label", "device_role", "device_type", "architecture",
        "substrate_type", "active_area", "area_unit",
        "area_definition", "encapsulation", "note"],
    "layers": [
        "publication_id", "layer_id", "device_id", "layer_order",
        "layer_function", "layer_material", "layer_thickness",
        "thickness_unit", "deposition_method", "annealing_temperature",
        "annealing_time", "atmosphere", "note"],
    "measurements": [
        "publication_id", "measurement_id", "device_id",
        "measurement_type", "spectrum", "light_intensity",
        "intensity_unit", "scan_direction", "scan_rate",
        "mask_used", "certified", "temperature",
        "stability_protocol", "stress_conditions", "note"],
    "results": [
        "publication_id", "result_id", "device_id", "measurement_id",
        "material_id", "metric_name", "metric_value", "metric_unit",
        "aggregation", "spread_value", "n_devices", "time_point",
        "time_unit", "raw_value", "raw_unit", "normalized_value",
        "normalized_unit", "result_origin", "cited_publication_id",
        "duplicate_of", "source_page", "source_section",
        "source_table", "source_figure", "source_fragment",
        "extraction_status"],
    "issues": [
        "publication_id", "issue_id", "record_ids", "check_name",
        "description", "source_page", "source_fragment"],
}

TABLE_QSS = """
QTableWidget {
    background-color: %(bg)s;
    alternate-background-color: %(alt)s;
    color: %(text)s;
    gridline-color: %(grid)s;
    border: 1px solid %(grid)s;
}
QHeaderView::section {
    background-color: %(head)s;
    color: %(text)s;
    border: 1px solid %(grid)s;
    padding: 4px;
}
QTableCornerButton::section {
    background-color: %(head)s;
    border: none;
}
"""


class ResearchDialog(QtWidgets.QDialog):
    jump = QtCore.pyqtSignal(str, int, str)  # path, page, fragment

    def __init__(self, docs, parent=None):
        super().__init__(parent)
        self.docs = docs
        self.data = {key: [] for _, key, _ in TABS}
        self.setWindowTitle("CyberDoc · Научные данные и проверка")
        self.resize(1300, 800)

        lay = QtWidgets.QVBoxLayout(self)
        title = QtWidgets.QLabel("Научные данные · извлечение и проверка")
        title.setStyleSheet("font-size:20px; font-weight:700;")
        lay.addWidget(title)

        hint = QtWidgets.QLabel(
            "Автоматически найденные значения — кандидаты. "
            "Проверьте каждое по исходной странице PDF. "
            "Двойной клик по строке — переход к месту в PDF; "
            "дубликаты подсвечиваются вместе, ←/→ в окне PDF переключают.")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        bar = QtWidgets.QHBoxLayout()
        lay.addLayout(bar)

        self.domain = QtWidgets.QComboBox()
        self.domain.addItem("Солнечные элементы", SOLAR)
        self.domain.addItem("RAG-системы", RAG)
        self.domain.currentIndexChanged.connect(self._on_domain_changed)
        bar.addWidget(self.domain)

        self.scan = QtWidgets.QPushButton("Извлечь из открытых PDF")
        self.scan.clicked.connect(self.run_scan)
        bar.addWidget(self.scan)

        self.btn_import = QtWidgets.QPushButton("Загрузить JSON…")
        self.btn_import.clicked.connect(self.import_json)
        bar.addWidget(self.btn_import)

        self.btn_export_csv = QtWidgets.QPushButton("Экспорт CSV (7 файлов)…")
        self.btn_export_csv.clicked.connect(self.export_csv)
        bar.addWidget(self.btn_export_csv)

        self.btn_export_json = QtWidgets.QPushButton("Экспорт JSON…")
        self.btn_export_json.clicked.connect(self.export_json)
        bar.addWidget(self.btn_export_json)

        bar.addStretch(1)

        self.status = QtWidgets.QLabel("")
        self.status.setStyleSheet(theme.HINT_QSS)
        lay.addWidget(self.status)

        self.tabs = QtWidgets.QTabWidget()
        lay.addWidget(self.tabs, 1)
        self.tables = {}

        self._build_tables(TABS)
        self.retheme()

    # ------------------------------------------------------------ UI
    def _build_tables(self, tabs):
        """Перестраивает вкладки под выбранный домен."""
        self.tabs.clear()
        self.tables = {}
        for title, key, cols in tabs:
            table = QtWidgets.QTableWidget(0, len(cols))
            table.setHorizontalHeaderLabels(cols)
            table.verticalHeader().setVisible(False)
            table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
            table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            table.setSortingEnabled(True)
            table.setAlternatingRowColors(True)
            table.horizontalHeader().setStretchLastSection(True)
            self.tabs.addTab(table, title)
            self.tables[key] = table
        self.retheme()

    def _on_domain_changed(self, _idx):
        """Смена домена: другие вкладки и другие ключи self.data."""
        if self.domain.currentData() == RAG:
            self._build_tables(RAG_TABS)
            self.data = {key: [] for _, key, _ in RAG_TABS}
        else:
            self._build_tables(TABS)
            self.data = {key: [] for _, key, _ in TABS}
        self.status.setText("")

    def retheme(self):
        colors = theme.html_colors()
        bg = colors.get("block") or "#1d2541"
        alt = colors.get("block_alt") or bg
        text = colors.get("text") or "#e8ecf7"
        grid = colors.get("border") or "#2c3557"
        head = colors.get("block") or "#252f50"
        table_qss = TABLE_QSS % {
            "bg": bg, "alt": alt, "text": text,
            "grid": grid, "head": head,
        }
        for w in self.findChildren(QtWidgets.QWidget):
            if isinstance(w, QtWidgets.QPushButton):
                w.setStyleSheet(theme.BUTTON_QSS)
            elif isinstance(w, QtWidgets.QComboBox):
                theme.style_combo(w)
            elif isinstance(w, QtWidgets.QTableWidget):
                w.setStyleSheet(theme.INPUT_QSS + table_qss)

    # ------------------------------------------------------------ scan
    def run_scan(self):
        domain = self.domain.currentData()
        if not self.docs:
            QtWidgets.QMessageBox.information(
                self, "Нет документов", "Сначала загрузите PDF.")
            return
        if domain == RAG:
            tabs = RAG_TABS
        else:
            tabs = TABS
        self.data = {key: [] for _, key, _ in tabs}
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            for doc in self.docs.values():
                if domain == RAG:
                    full = extract_publication_rag(doc)
                else:
                    full = extract_publication(doc)
                for key in self.data:
                    self.data[key].extend(full.get(key, []) or [])
            self._annotate_duplicates()
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
        self.fill_tables()
        self.status.setText("Записей: %d" % sum(len(v) for v in self.data.values()))

    def _annotate_duplicates(self):
        """Заполняет duplicate_info: 'оригинал', 'дубликат <id> (стр. N)'."""
        results = self.data.get("results", [])
        by_id = {r["result_id"]: r for r in results if r.get("result_id")}
        for r in results:
            dup = r.get("duplicate_of")
            if dup and dup in by_id:
                orig = by_id[dup]
                r["duplicate_info"] = "дубликат %s (стр. %s)" % (
                    orig.get("result_id", "")[:8],
                    orig.get("source_page") or "?")
            elif any(x.get("duplicate_of") == r.get("result_id")
                     for x in results):
                r["duplicate_info"] = "оригинал"
            else:
                r["duplicate_info"] = ""

    def fill_tables(self):
        tabs = RAG_TABS if self.domain.currentData() == RAG else TABS
        for title, key, cols in tabs:
            table = self.tables[key]
            rows = self.data.get(key, [])
            table.setSortingEnabled(False)
            table.setRowCount(len(rows))
            for i, row in enumerate(rows):
                for j, col in enumerate(cols):
                    val = row.get(col)
                    if isinstance(val, (list, tuple)):
                        val = ";".join(str(x) for x in val)
                    item = QtWidgets.QTableWidgetItem(
                        "" if val is None else str(val))
                    if j == 0:
                        item.setData(QtCore.Qt.UserRole, row)
                    table.setItem(i, j, item)
            table.setSortingEnabled(True)
            table.resizeColumnsToContents()
            try:
                table.cellDoubleClicked.disconnect(
                    self._on_cell_double_clicked)
            except TypeError:
                pass
            table.cellDoubleClicked.connect(self._on_cell_double_clicked)

    def _on_cell_double_clicked(self, row, col):
        table = self.sender()
        item = table.item(row, 0)
        if item is None:
            return
        rec = item.data(QtCore.Qt.UserRole)
        if not rec:
            return
        pub_id = rec.get("publication_id")
        page = rec.get("source_page")
        fragment = rec.get("source_fragment") or ""
        if not pub_id or page is None:
            return
        path = None
        for p, d in self.docs.items():
            if getattr(d, "name", "").rsplit(".", 1)[0] == pub_id:
                path = p
                break
        if path is None and self.docs:
            path = next(iter(self.docs.keys()))
        self._emit_jump(path or "", int(page), fragment, rec)

    def _emit_jump(self, path, page, fragment, rec):
        """Сохраняем rec на время перехода — main_window использует его."""
        self._last_jump_record = rec
        self.jump.emit(path, page, fragment)

    def last_jump_record(self):
        return getattr(self, "_last_jump_record", None)

    # ------------------------------------------------------------ import
    def import_json(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Загрузить JSON", "", "JSON (*.json)")
        if not path:
            return
        try:
            payload = import_workspace(path)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Импорт", str(e))
            return
        tabs = RAG_TABS if self.domain.currentData() == RAG else TABS
        self.data = {key: [] for _, key, _ in tabs}
        for _, key, _ in tabs:
            self.data[key] = payload.get(key, [])
        self._annotate_duplicates()
        self.fill_tables()
        self.status.setText("Импортировано из %s" % os.path.basename(path))

    # ------------------------------------------------------------ export CSV
    def export_csv(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Папка для CSV")
        if not folder:
            return
        if self.domain.currentData() == RAG:
            written = export_rag_submission(folder, self.data)
        else:
            written = []
            for _, key, _ in TABS:
                cols = CSV_FIELDS[key]
                path = os.path.join(folder, CSV_NAMES[key])
                with open(path, "w", encoding="utf-8-sig", newline="") as fh:
                    w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
                    w.writeheader()
                    for row in self.data.get(key, []):
                        w.writerow({c: ("" if row.get(c) is None else row.get(c))
                                    for c in cols})
                written.append(path)
        QtWidgets.QMessageBox.information(
            self, "Экспорт", "Записано %d файлов в:\n%s" % (len(written), folder))

    # ------------------------------------------------------------ export JSON
    def export_json(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Экспорт JSON", "cyberdoc_dataset.json", "JSON (*.json)")
        if not path:
            return
        payload = {
            "passport": {
                "name": "CyberDoc evidence dataset",
                "version": "0.7",
                "domain": self.domain.currentData(),
                "unknown_values": "null; never inferred",
                "status_values": ["candidate", "verified", "rejected",
                                  "present_not_extractable"],
            },
        }
        payload.update(self.data)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        self.status.setText("JSON: %s" % os.path.basename(path))
