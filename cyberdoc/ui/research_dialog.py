"""Research data review and export window (7 tabs per TZ)."""
import json
from PyQt5 import QtCore, QtWidgets
from .. import theme
from ..research import (SOLAR, RAG, extract_publication, validate,
                        export_workspace, import_workspace)


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
        "area_definition", "encapsulation"]),
    ("Слои", "layers", [
        "publication_id", "layer_id", "device_id", "layer_order",
        "layer_function", "layer_material", "layer_thickness",
        "thickness_unit", "deposition_method", "annealing_temperature",
        "annealing_time", "atmosphere"]),
    ("Измерения", "measurements", [
        "publication_id", "measurement_id", "device_id",
        "measurement_type", "spectrum", "light_intensity",
        "intensity_unit", "scan_direction", "scan_rate",
        "mask_used", "certified", "temperature",
        "stability_protocol"]),
    ("Результаты", "results", [
        "publication_id", "result_id", "device_id", "measurement_id",
        "material_id", "metric_name", "metric_value", "metric_unit",
        "aggregation", "raw_value", "raw_unit", "normalized_value",
        "normalized_unit", "result_origin", "source_page",
        "source_section", "source_table", "source_figure",
        "source_fragment", "extraction_status", "duplicate_of"]),
    ("Замечания", "issues", [
        "publication_id", "issue_id", "record_ids", "check_name",
        "description", "source_page", "source_fragment"]),
]


class ResearchDialog(QtWidgets.QDialog):
    def __init__(self, docs, parent=None):
        super().__init__(parent)
        self.docs = docs
        self.data = {key: [] for _, key, _ in TABS}
        self.setWindowTitle("CyberDoc · Научные данные и проверка")
        self.resize(1200, 750)

        lay = QtWidgets.QVBoxLayout(self)
        title = QtWidgets.QLabel("Научные данные · извлечение и проверка")
        title.setStyleSheet("font-size:20px; font-weight:700;")
        lay.addWidget(title)

        hint = QtWidgets.QLabel(
            "Автоматически найденные значения — кандидаты. "
            "Проверьте каждое по исходной странице PDF.")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        bar = QtWidgets.QHBoxLayout()
        lay.addLayout(bar)

        self.domain = QtWidgets.QComboBox()
        self.domain.addItem("Солнечные элементы", SOLAR)
        self.domain.addItem("RAG-системы", RAG)
        bar.addWidget(self.domain)

        self.scan = QtWidgets.QPushButton("Извлечь из открытых PDF")
        self.scan.clicked.connect(self.extract)
        bar.addWidget(self.scan)

        self.verify = QtWidgets.QPushButton("Подтвердить запись")
        self.verify.clicked.connect(self.mark_verified)
        bar.addWidget(self.verify)

        self.import_btn = QtWidgets.QPushButton("Загрузить JSON")
        self.import_btn.clicked.connect(self.load_json)
        bar.addWidget(self.import_btn)

        self.export = QtWidgets.QPushButton("Экспорт JSON")
        self.export.clicked.connect(self.save)
        bar.addWidget(self.export)

        self.tabs = QtWidgets.QTabWidget()
        lay.addWidget(self.tabs, 4)

        self.tables = {}
        self._build_tabs()

        lay.addWidget(QtWidgets.QLabel("Исходный фрагмент и замечания"))
        self.source = QtWidgets.QTextBrowser()
        self.source.setMinimumHeight(120)
        lay.addWidget(self.source, 1)

        self.status = QtWidgets.QLabel(
            "Откройте PDF, выберите предметную область и нажмите «Извлечь»")
        lay.addWidget(self.status)

        self.retheme()

    def _build_tabs(self):
        for title, key, cols in TABS:
            table = QtWidgets.QTableWidget(0, len(cols))
            table.setHorizontalHeaderLabels(cols)
            table.setSelectionBehavior(
                QtWidgets.QAbstractItemView.SelectRows)
            table.setEditTriggers(
                QtWidgets.QAbstractItemView.NoEditTriggers)
            table.verticalHeader().setVisible(False)
            table.setCornerButtonEnabled(False)
            header = table.horizontalHeader()
            header.setSectionResizeMode(QtWidgets.QHeaderView.Interactive)
            for i in range(len(cols) - 1):
                table.setColumnWidth(i, 110)
            header.setSectionResizeMode(
                len(cols) - 1, QtWidgets.QHeaderView.Stretch)
            table.itemSelectionChanged.connect(
                lambda t=table, k=key: self.show_source(t, k))
            self.tables[key] = table
            self.tabs.addTab(table, title)

    def retheme(self):
        self.setStyleSheet(theme.DIALOG_QSS)
        self.domain.setStyleSheet(theme.INPUT_QSS)
        for w in (self.scan, self.verify, self.import_btn, self.export):
            w.setStyleSheet(theme.BUTTON_QSS)
        self.source.setStyleSheet(theme.INPUT_QSS)
        table_qss = theme.TABLE_QSS + """
QHeaderView { background: #252f50; border: none; }
QHeaderView::section { background: #252f50; color: %s; border: none; }
QTableCornerButton::section { background: #252f50; border: none; }
QTableWidget { background: #202844; border: none; }
""" % theme.TEXT_COLOR
        for table in self.tables.values():
            table.setStyleSheet(table_qss)

    # ------------------------------------------------------------ extract
    def extract(self):
        self.data = {key: [] for _, key, _ in TABS}
        for doc in self.docs.values():
            full = extract_publication(doc)
            for key in self.data:
                if key in full:
                    self.data[key].extend(full[key])
        self.refresh()

    def refresh(self):
        for title, key, cols in TABS:
            table = self.tables[key]
            table.clearContents()
            table.setRowCount(0)
            rows = self.data.get(key, [])
            table.setRowCount(len(rows))
            for i, row in enumerate(rows):
                for j, col in enumerate(cols):
                    value = row.get(col)
                    item = QtWidgets.QTableWidgetItem(
                        "" if value is None else str(value))
                    item.setData(QtCore.Qt.UserRole, i)
                    table.setItem(i, j, item)
        self.status.setText(
            "Публикаций: %d · Материалов: %d · Приборов: %d · "
            "Слоёв: %d · Измерений: %d · Результатов: %d · "
            "Замечаний: %d" % tuple(
                len(self.data[k]) for k in (
                    "publications", "materials", "devices", "layers",
                    "measurements", "results", "issues")))

    # ------------------------------------------------------------ source
    def show_source(self, table, key):
        row = table.currentRow()
        rows = self.data.get(key, [])
        if not (0 <= row < len(rows)):
            return
        r = rows[row]
        parts = []
        for label, field in (
                ("Файл", "source_file"), ("Страница", "source_page"),
                ("Фрагмент", "source_fragment"),
                ("Раздел", "source_section"),
                ("Таблица", "source_table"),
                ("Рисунок", "source_figure")):
            if r.get(field):
                parts.append("%s: %s" % (label, r[field]))
        if key == "results":
            for f in validate(r):
                parts.append("• " + f["message"])
        if not parts:
            parts = ["Нет данных об источнике для этой записи."]
        self.source.setPlainText("\n".join(parts))

    # ------------------------------------------------------------ verify
    def mark_verified(self):
        idx = self.tabs.currentIndex()
        if idx < 0 or idx >= len(TABS):
            return
        key = TABS[idx][1]
        table = self.tables[key]
        row = table.currentRow()
        rows = self.data.get(key, [])
        if not (0 <= row < len(rows)):
            return
        confirm = QtWidgets.QMessageBox.question(
            self, "Проверка источника",
            "Вы вручную сверили запись с исходной страницей PDF?")
        if confirm == QtWidgets.QMessageBox.Yes:
            if "extraction_status" in rows[row]:
                rows[row]["extraction_status"] = "verified"
                self.refresh()

    # ------------------------------------------------------------ JSON
    def load_json(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Загрузить рабочий набор", "", "JSON (*.json)")
        if not path:
            return
        try:
            data = import_workspace(path)
            for key in self.data:
                self.data[key] = data.get(key, [])
            self.refresh()
            self.status.setText("Загружено: %d результатов, %d замечаний"
                                % (len(self.data["results"]),
                                   len(self.data["issues"])))
        except (OSError, ValueError, TypeError, UnicodeError) as exc:
            QtWidgets.QMessageBox.warning(
                self, "Ошибка загрузки JSON", str(exc))

    def save(self):
        if not self.docs:
            QtWidgets.QMessageBox.information(
                self, "Нет данных",
                "Сначала загрузите PDF в главное окно.")
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Экспорт рабочего набора",
            "cyberdoc_workspace.json", "JSON (*.json)")
        if not path:
            return
        try:
            total = export_workspace(path, self.docs)
            self.status.setText(
                "Экспортирован рабочий набор: %d записей" % total)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Экспорт", str(exc))
