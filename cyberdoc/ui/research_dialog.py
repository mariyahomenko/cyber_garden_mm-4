"""Research data review and export window."""
import json
from PyQt5 import QtCore, QtWidgets
from .. import theme
from ..research import SOLAR, RAG, extract_candidates, validate, export_dataset

class ResearchDialog(QtWidgets.QDialog):
    def __init__(self, docs, parent=None):
        super().__init__(parent)
        self.docs=docs;self.records=[]
        self.setWindowTitle("CyberDoc · Научные данные и проверка")
        self.resize(1100,700)
        
        lay=QtWidgets.QVBoxLayout(self)
        title=QtWidgets.QLabel("Научные данные · извлечение и проверка")
        title.setStyleSheet("font-size:20px; font-weight:700;")
        lay.addWidget(title)
        
        hint=QtWidgets.QLabel("Автоматически найденные значения — кандидаты. Проверьте каждое по исходной странице PDF.")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        
        bar=QtWidgets.QHBoxLayout()
        lay.addLayout(bar)
        
        self.domain=QtWidgets.QComboBox()
        self.domain.addItem("Солнечные элементы",SOLAR)
        self.domain.addItem("RAG-системы",RAG)
        bar.addWidget(self.domain)
        
        self.scan=QtWidgets.QPushButton("Извлечь из открытых PDF")
        self.scan.clicked.connect(self.extract)
        bar.addWidget(self.scan)
        
        self.verify=QtWidgets.QPushButton("Подтвердить запись")
        self.verify.clicked.connect(self.mark_verified)
        bar.addWidget(self.verify)
        
        self.import_btn=QtWidgets.QPushButton("Загрузить JSON")
        self.import_btn.clicked.connect(self.load_json)
        bar.addWidget(self.import_btn)
        
        self.export=QtWidgets.QPushButton("Экспорт JSON")
        self.export.clicked.connect(self.save)
        bar.addWidget(self.export)
        
        self.table=QtWidgets.QTableWidget(0,7)
        self.table.setHorizontalHeaderLabels(["Статус","Показатель","Значение","Ед.","Файл","Стр.","Замечания"])
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self.show_source)
        lay.addWidget(self.table,3)
        
        lay.addWidget(QtWidgets.QLabel("Исходный фрагмент и замечания"))
        self.source=QtWidgets.QTextBrowser()
        lay.addWidget(self.source,1)
        
        self.status=QtWidgets.QLabel("Откройте PDF, выберите предметную область и нажмите «Извлечь»")
        lay.addWidget(self.status)
        
        self.retheme()

    def retheme(self):
        self.setStyleSheet(theme.DIALOG_QSS)
        self.domain.setStyleSheet(theme.INPUT_QSS)
        self.scan.setStyleSheet(theme.BUTTON_QSS)
        self.verify.setStyleSheet(theme.BUTTON_QSS)
        self.import_btn.setStyleSheet(theme.BUTTON_QSS)
        self.export.setStyleSheet(theme.BUTTON_QSS)
        self.table.setStyleSheet(theme.TABLE_QSS)
        self.source.setStyleSheet(theme.INPUT_QSS)

    def extract(self):
        domain=self.domain.currentData()
        self.records=[]
        for doc in self.docs.values():self.records.extend(extract_candidates(doc,domain))
        self.refresh()

    def refresh(self):
        self.table.setRowCount(len(self.records))
        for i,r in enumerate(self.records):
            values=[r.get("extraction_status"),r.get("metric_name"),r.get("normalized_value"),
                    r.get("normalized_unit"),r.get("publication_id"),r.get("source_page"),len(validate(r))]
            for j,value in enumerate(values):
                item=QtWidgets.QTableWidgetItem(str(value if value is not None else "—"))
                item.setData(QtCore.Qt.UserRole,i)
                self.table.setItem(i,j,item)
        self.table.resizeColumnsToContents()
        self.status.setText("Найдено записей: %d · Требуют проверки: %d" %
            (len(self.records),sum(r["extraction_status"]=="candidate" for r in self.records)))

    def selected(self):
        row=self.table.currentRow()
        return self.records[row] if 0<=row<len(self.records) else None

    def show_source(self):
        r=self.selected()
        if not r:return
        findings=validate(r)
        self.source.setPlainText("Файл: %s\nСтраница PDF: %s\n\n%s\n\nЗамечания:\n%s" %
            (r["source_file"],r["source_page"],r["source_fragment"],
             "\n".join("• "+f["message"] for f in findings) or "Нет автоматических замечаний"))

    def mark_verified(self):
        r=self.selected()
        if not r:return
        confirm=QtWidgets.QMessageBox.question(self,"Проверка источника",
           "Вы вручную сверили значение, единицу и контекст с исходной страницей PDF?")
        if confirm==QtWidgets.QMessageBox.Yes:
            r["extraction_status"]="verified"
            self.refresh()

    def load_json(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Загрузить научные данные", "", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as handle:
                payload = json.load(handle)
            if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
                raise ValueError("Ожидается объект JSON с массивом records")
            domain = payload.get("passport", {}).get("domain")
            if domain not in (SOLAR, RAG):
                raise ValueError("Неизвестная предметная область в паспорте")
            for record in payload["records"]:
                if not isinstance(record, dict) or record.get("domain") != domain:
                    raise ValueError("Запись без корректного поля domain")
            self.domain.setCurrentIndex(0 if domain == SOLAR else 1)
            self.records = payload["records"]
            self.refresh()
            self.status.setText("Загружено записей: %d" % len(self.records))
        except (OSError, ValueError, TypeError, UnicodeError) as exc:
            QtWidgets.QMessageBox.warning(self, "Ошибка загрузки JSON", str(exc))

    def save(self):
        if not self.records:
            QtWidgets.QMessageBox.information(self,"Нет данных","Сначала выполните извлечение.")
            return
        path,_=QtWidgets.QFileDialog.getSaveFileName(self,"Экспорт набора данных","cyberdoc_dataset.json","JSON (*.json)")
        if path:
            count,issues=export_dataset(path,self.records,self.domain.currentData())
            self.status.setText("Экспортировано %d записей, %d замечаний"%(count,issues))
