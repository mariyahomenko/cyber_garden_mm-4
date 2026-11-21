"""Правая панель: извлечённые сущности, сводка, проверки, поиск по документу.

Реализует кейс: извлечение данных из PDF, привязка к странице,
нормализация, проверка согласованности, поиск дубликатов и RAG-поиск."""

import re

from PyQt5 import QtWidgets, QtCore

from .. import theme

NUM_UNIT_RE = re.compile(
    r"([A-Za-zА-Яа-яёЁ][\w\-/αωΑ-Ω]{1,40})\s*(?:=|≈|:|)\s*"
    r"(-?\d+(?:[.,]\d+)?(?:\s?[x×]\s?10\^?-?\d+)?)\s*"
    r"(мВт/см²|Вт/м²|Вт/см²|мВт|кВт|Вт|нА|мкА|мА|А|мВ|кВ|В|"
    r"кОм|МОм|Ом|нм|мкм|мм|см²|см|м²|эВ|кДж|Дж|К|°С|%)",
    re.UNICODE)


def _to_float(value):
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _near(a, b):
    """Близость чисел: 2 % отн. или 0.1 абс. — как в сопоставлении ТЗ."""
    fa, fb = _to_float(a), _to_float(b)
    if fa is None or fb is None:
        return False
    if fa == 0 and fb == 0:
        return True
    denom = max(abs(fa), abs(fb)) or 1.0
    return abs(fa - fb) / denom <= 0.02 or abs(fa - fb) <= 0.1


class EntityPanel(QtWidgets.QWidget):
    jump = QtCore.pyqtSignal(dict)        # row -> переход в PDF

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []
        self._source_text = ""

        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)

        lbl = QtWidgets.QLabel("Данные статьи")
        lbl.setStyleSheet(theme.LABEL_QSS)
        v.addWidget(lbl)

        self.tabs = QtWidgets.QTabWidget()
        v.addWidget(self.tabs, 1)

        # ---------- вкладка: сущности ----------
        ent = QtWidgets.QWidget()
        ev = QtWidgets.QVBoxLayout(ent)
        ev.setContentsMargins(4, 4, 4, 4)
        ev.setSpacing(6)

        flt = QtWidgets.QHBoxLayout()
        ev.addLayout(flt)
        self.type_box = QtWidgets.QComboBox()
        self.type_box.setStyleSheet(theme.INPUT_QSS)
        self.type_box.addItems(["все", "числа", "формулы", "дубликаты"])
        self.type_box.currentIndexChanged.connect(self._apply_filters)
        flt.addWidget(self.type_box)

        self.text_filter = QtWidgets.QLineEdit()
        self.text_filter.setStyleSheet(theme.INPUT_QSS)
        self.text_filter.setPlaceholderText("фильтр...")
        self.text_filter.textChanged.connect(self._apply_filters)
        flt.addWidget(self.text_filter, 1)

        rng = QtWidgets.QHBoxLayout()
        ev.addLayout(rng)
        rl = QtWidgets.QLabel("Стр.:")
        rl.setStyleSheet(theme.LABEL_QSS)
        rng.addWidget(rl)
        self.page_from = QtWidgets.QSpinBox()
        self.page_from.setStyleSheet(theme.INPUT_QSS)
        self.page_from.setRange(0, 99999)
        self.page_from.valueChanged.connect(self._apply_filters)
        rng.addWidget(self.page_from)
        rl2 = QtWidgets.QLabel("—")
        rl2.setStyleSheet(theme.LABEL_QSS)
        rng.addWidget(rl2)
        self.page_to = QtWidgets.QSpinBox()
        self.page_to.setStyleSheet(theme.INPUT_QSS)
        self.page_to.setRange(0, 99999)
        self.page_to.setValue(99999)
        self.page_to.valueChanged.connect(self._apply_filters)
        rng.addWidget(self.page_to)

        self.table = QtWidgets.QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["Тип", "Параметр", "Значение", "Ед.", "Стр.", "Дубликат", "Где"])
        self.table.setColumnWidth(0, 60)
        self.table.setColumnWidth(1, 100)
        self.table.setColumnWidth(3, 45)
        self.table.setColumnWidth(4, 45)
        self.table.setColumnWidth(5, 70)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.doubleClicked.connect(self._on_jump)
        ev.addWidget(self.table, 1)

        hint = QtWidgets.QLabel(
            "Двойной клик — открыть место в PDF. «Дубликат» — совпадает "
            "с другой записью (та же статья или другая).")
        hint.setWordWrap(True)
        hint.setStyleSheet(theme.HINT_QSS)
        ev.addWidget(hint)

        self.tabs.addTab(ent, "Сущности")

        self.summary_view = QtWidgets.QTextBrowser()
        self.summary_view.setStyleSheet(theme.INPUT_QSS)
        self.summary_view.setOpenExternalLinks(False)
        self.tabs.addTab(self.summary_view, "Сводка")

        self.checks_view = QtWidgets.QTextBrowser()
        self.checks_view.setStyleSheet(theme.INPUT_QSS)
        self.checks_view.setOpenExternalLinks(False)
        self.tabs.addTab(self.checks_view, "Проверки")

        rag = QtWidgets.QWidget()
        rv = QtWidgets.QVBoxLayout(rag)
        rv.setContentsMargins(4, 4, 4, 4)
        rv.setSpacing(6)
        self.rag_input = QtWidgets.QLineEdit()
        self.rag_input.setStyleSheet(theme.INPUT_QSS)
        self.rag_input.setPlaceholderText("Найти факты/страницы по вопросу...")
        rv.addWidget(self.rag_input)
        self.rag_btn = QtWidgets.QPushButton("Искать фрагменты")
        self.rag_btn.setStyleSheet(theme.BUTTON_QSS)
        rv.addWidget(self.rag_btn)
        self.rag_view = QtWidgets.QListWidget()
        self.rag_view.setStyleSheet(theme.INPUT_QSS)
        self.rag_view.itemDoubleClicked.connect(self._rag_jump)
        rv.addWidget(self.rag_view, 1)
        self.tabs.addTab(rag, "Поиск по документу")

    # ============================ данные ============================
    def set_page_range(self, n_pages, first_number):
        self.page_from.setRange(first_number, first_number + n_pages)
        self.page_from.setValue(first_number)
        self.page_to.setRange(first_number, first_number + n_pages)
        self.page_to.setValue(first_number + n_pages - 1)

    def fill(self, entries):
        """entries: список dict с ключами text/formulas/anchors/doc (и path)."""
        self.rows = []
        self._source_text = ""
        for e in entries:
            doc = e.get("doc", "")
            path = e.get("path") or e.get("doc") or ""
            self._source_text += "\n" + (e.get("text") or "")
            for chunk in re.split(r"\[(?:стр\.|page)\s*", e.get("text", "")):
                m = re.match(r"(\d+)\]", chunk)
                cur_page = int(m.group(1)) if m else None
                for nm in NUM_UNIT_RE.finditer(chunk):
                    self.rows.append({
                        "type": "число",
                        "param": nm.group(1).strip(" ;,-—(«")[:48],
                        "value": nm.group(2).replace(",", ".").strip(),
                        "unit": nm.group(3),
                        "page": cur_page,
                        "doc": doc,
                        "path": path,
                        "duplicate_of": None,
                    })
            for f in e.get("formulas", []):
                self.rows.append({
                    "type": "формула",
                    "param": "формула",
                    "value": f.get("latex", "")[:64],
                    "unit": "—",
                    "page": f.get("page"),
                    "doc": doc,
                    "path": path,
                    "duplicate_of": None,
                })
        self._mark_duplicates()
        self._apply_filters()
        self._rebuild_summary()
        self._rebuild_checks()

    # ============================ дубликаты ============================
    def _mark_duplicates(self):
        """Помечает записи, совпадающие по параметру и близкому значению.

        Работает и внутри одной статьи, и между разными файлами —
        именно этого требует ТЗ (сопоставление результатов).
        """
        for i, r in enumerate(self.rows):
            r["duplicate_of"] = None
        for i in range(len(self.rows)):
            for j in range(i + 1, len(self.rows)):
                a, b = self.rows[i], self.rows[j]
                if a["type"] != b["type"]:
                    continue
                if a["param"].lower() != b["param"].lower():
                    continue
                if a["type"] == "число":
                    if not _near(a["value"], b["value"]):
                        continue
                else:
                    # формулы: сравниваем нормализованный текст
                    na = re.sub(r"\s+", "", a["value"]).lower()
                    nb = re.sub(r"\s+", "", b["value"]).lower()
                    if na != nb:
                        continue
                if b["duplicate_of"] is None:
                    b["duplicate_of"] = i  # индекс оригинала в self.rows

    # ============================ фильтры ============================
    def _apply_filters(self, *_args):
        type_sel = self.type_box.currentText()
        text = self.text_filter.text().strip().lower()
        p_from = self.page_from.value()
        p_to = self.page_to.value()
        shown = []
        for idx, r in enumerate(self.rows):
            r["_idx"] = idx
            if type_sel == "числа" and r["type"] != "число":
                continue
            if type_sel == "формулы" and r["type"] != "формула":
                continue
            if type_sel == "дубликаты" and r["duplicate_of"] is None:
                continue
            if text and text not in (r["param"] + " " + r["value"]).lower():
                continue
            if r["page"] is not None and not (p_from <= r["page"] <= p_to):
                continue
            shown.append(r)
        self.table.setRowCount(len(shown))
        for i, r in enumerate(shown):
            dup_text = ""
            where_text = ""
            if r["duplicate_of"] is not None:
                orig = self.rows[r["duplicate_of"]]
                dup_text = "строка %d" % (r["duplicate_of"] + 1)
                where_text = "%s:стр. %s" % (
                    orig.get("doc") or "?", orig.get("page") or "?")
            values = [r["type"], r["param"], r["value"], r["unit"],
                      r["page"], dup_text, where_text]
            for j, val in enumerate(values):
                item = QtWidgets.QTableWidgetItem("" if val is None else str(val))
                item.setData(QtCore.Qt.UserRole, r)
                if j == 5 and dup_text:
                    item.setForeground(QtCore.Qt.gray)
                self.table.setItem(i, j, item)
        self.table.resizeColumnsToContents()

    def _on_jump(self, index):
        row = self.table.item(index.row(), 0).data(QtCore.Qt.UserRole)
        if not row:
            return
        # Двойной клик по дубликату — открываем оригинал
        if row.get("duplicate_of") is not None:
            orig = self.rows[row["duplicate_of"]]
            self.jump.emit({
                "page": orig.get("page"),
                "value": orig.get("value", ""),
                "type": orig.get("type"),
                "path": orig.get("path"),
                "doc": orig.get("doc"),
            })
            return
        self.jump.emit({
            "page": row.get("page"),
            "value": row.get("value", ""),
            "type": row.get("type"),
            "path": row.get("path"),
            "doc": row.get("doc"),
        })

    # ============================ сводка ============================
    def _rebuild_summary(self):
        nums = [r for r in self.rows if r["type"] == "число"]
        forms = [r for r in self.rows if r["type"] == "формула"]
        dups = [r for r in self.rows if r["duplicate_of"] is not None]
        units = {}
        params = {}
        for r in nums:
            units[r["unit"]] = units.get(r["unit"], 0) + 1
            params[r["param"]] = params.get(r["param"], 0) + 1
        top_params = sorted(params.items(), key=lambda kv: -kv[1])[:10]
        lines = ["<h3>Сводка по извлечённым данным</h3>",
                 "<p>Чисел: <b>%d</b> &nbsp; Формул: <b>%d</b> &nbsp; "
                 "Дубликатов: <b>%d</b></p>"
                 % (len(nums), len(forms), len(dups)),
                 "<h4>Единицы измерения</h4><ul>"]
        for u, c in sorted(units.items(), key=lambda kv: -kv[1]):
            lines.append("<li>%s — %d</li>" % (u, c))
        lines.append("</ul><h4>Частые параметры</h4><ul>")
        for p, c in top_params:
            lines.append("<li>%s — %d</li>" % (p, c))
        lines.append("</ul>")
        self.summary_view.setHtml("".join(lines))

    # ============================ проверки ============================
    def _rebuild_checks(self):
        nums = [r for r in self.rows if r["type"] == "число"]
        dups = [(i, r) for i, r in enumerate(self.rows)
                if r["duplicate_of"] is not None]
        no_page = [r for r in nums if r["page"] is None]
        negatives = [r for r in nums if str(r["value"]).startswith("-")]
        lines = ["<h3>Проверка согласованности</h3>",
                 "<p>Всего чисел: %d</p>" % len(nums),
                 "<h4>Дубликаты: %d</h4>" % len(dups)]
        for i, r in dups:
            orig = self.rows[r["duplicate_of"]]
            lines.append(
                "<p>• %s = %s %s — <b>дубликат</b> строки %d "
                "(%s:стр. %s) → здесь: %s:стр. %s</p>" % (
                    r["param"], r["value"], r["unit"],
                    r["duplicate_of"] + 1,
                    orig.get("doc") or "?", orig.get("page") or "?",
                    r.get("doc") or "?", r.get("page") or "?"))
        lines.append("<h4>Числа без указания страницы: %d</h4>" % len(no_page))
        lines.append("<h4>Числа с отрицательным знаком: %d</h4>" % len(negatives))
        self.checks_view.setHtml("".join(lines))

    # ============================ RAG-поиск ============================
    def set_rag_handler(self, fn):
        self.rag_btn.clicked.connect(lambda: self._run_rag(fn))

    def _run_rag(self, fn):
        q = self.rag_input.text().strip()
        if not q:
            return
        self.rag_view.clear()
        try:
            res = fn(q) or []
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Поиск", str(e))
            return
        for r in res:
            it = QtWidgets.QListWidgetItem(
                "стр. %s: %s" % (r.get("page", "?"), r.get("snippet", "")[:120]))
            it.setData(QtCore.Qt.UserRole, r)
            self.rag_view.addItem(it)

    def _rag_jump(self, item):
        r = item.data(QtCore.Qt.UserRole)
        if r:
            self.jump.emit({"page": r.get("page"), "value": "",
                            "type": "число",
                            "path": r.get("path"), "doc": r.get("doc")})

    def rows_for_export(self):
        return list(self.rows)
