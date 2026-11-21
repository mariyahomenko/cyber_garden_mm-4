import re
from PyQt5 import QtWidgets, QtCore, QtGui

from .. import theme
from ..renderer import render_answer_html
from .widgets import SearchLineEdit


class AnswerWindow(QtWidgets.QMainWindow):
    link_clicked = QtCore.pyqtSignal(QtCore.QUrl)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ответ")
        self.resize(1000, 720)
        self._entry = None
        self._base_html = ""
        self._zoom_factor = 1.0
        self._matches = []
        self._match_idx = -1

        central = QtWidgets.QWidget()
        central.setObjectName("Card")
        self.setCentralWidget(central)
        v = QtWidgets.QVBoxLayout(central)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(8)

        self.answer_search = SearchLineEdit("Поиск по ответу...")
        self.answer_search.textChanged.connect(self._on_search_changed)
        self.answer_search.returnPressed.connect(self.search_answer)
        self.answer_search.prev_requested.connect(self.prev_match)
        self.answer_search.next_requested.connect(self.next_match)
        v.addWidget(self.answer_search)

        self.output = QtWidgets.QTextBrowser()
        self.output.setOpenExternalLinks(False)
        self.output.setOpenLinks(False)
        self.output.anchorClicked.connect(self._on_anchor_clicked)
        self.output.setLineWrapMode(QtWidgets.QTextEdit.WidgetWidth)
        self.output.setWordWrapMode(
            QtGui.QTextOption.WrapAtWordBoundaryOrAnywhere)
        self.output.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarAlwaysOff)
        v.addWidget(self.output, 1)
        zoom_bar = QtWidgets.QHBoxLayout()
        zoom_bar.addStretch()
        self.btn_zoom_out = QtWidgets.QPushButton("−")
        self.btn_zoom_out.setFixedSize(38, 38)
        self.btn_zoom_out.clicked.connect(lambda: self._zoom(-1))
        zoom_bar.addWidget(self.btn_zoom_out)
        self.zoom_label = QtWidgets.QLabel("100%")
        zoom_bar.addWidget(self.zoom_label)
        self.btn_zoom_in = QtWidgets.QPushButton("+")
        self.btn_zoom_in.setFixedSize(38, 38)
        self.btn_zoom_in.clicked.connect(lambda: self._zoom(1))
        zoom_bar.addWidget(self.btn_zoom_in)
        v.addLayout(zoom_bar)

        self.question_label = QtWidgets.QLabel("")
        self.question_label.setWordWrap(True)
        v.addWidget(self.question_label)

        QtWidgets.QShortcut(
            QtGui.QKeySequence("Ctrl+F"), self).activated.connect(
                lambda: (self.answer_search.setFocus(),
                         self.answer_search.selectAll()))

        self.retheme()
        self._center_on_screen()

    def retheme(self):
        self.answer_search.retheme()
        self.output.setStyleSheet(theme.INPUT_QSS)
        for button in (self.btn_zoom_out, self.btn_zoom_in):
            button.setStyleSheet(theme.BUTTON_QSS)
        self.question_label.setStyleSheet(theme.LABEL_QSS)
        if self._entry:
            self.set_entry(self._entry)

    def _center_on_screen(self):
        scr = QtWidgets.QApplication.primaryScreen().availableGeometry()
        w = min(1000, int(scr.width() * 0.9))
        h = min(720, int(scr.height() * 0.9))
        self.resize(w, h)
        self.move(scr.center() - self.rect().center())

    def set_entry(self, entry):
        self._entry = entry or {}
        text = self._entry.get("text", "") or ""
        self._base_html = render_answer_html(
            text,
            self._entry.get("formulas", []),
            self._entry.get("anchors", []),
            doc_name=self._entry.get("doc"),
        )
        self._apply_zoom()
        parts = []
        doc = (self._entry.get("doc") or "").strip()
        if doc:
            parts.append("Файл: " + doc)
        q = (self._entry.get("question") or "").strip()
        if q:
            parts.append("Вопрос: " + q)
        ctx = self._entry.get("context_pages")
        if ctx:
            parts.append("Контекст: стр. %s" % ", ".join(map(str, ctx)))
        self.question_label.setText("    |    ".join(parts))
        self._matches = []
        self._match_idx = -1
        self.answer_search.set_counter(0, 0)
        self.output.verticalScrollBar().setValue(0)

    def _zoom(self, delta):
        self._zoom_factor = max(0.65, min(2.4, self._zoom_factor * (1.12 ** delta)))
        self._apply_zoom()

    def _reset_zoom(self):
        self._zoom_factor = 1.0
        self._apply_zoom()

    def _apply_zoom(self):
        # Мы пересобираем HTML, потому что QTextEdit.zoomIn не масштабирует
        # встроенные CSS-размеры и изображения формул.
        if not self._base_html:
            return
        factor = self._zoom_factor
        def scale(match):
            value = float(match.group(1)) * factor
            return "font-size:%0.2f%s" % (value, match.group(2))
        html = re.sub(r"font-size\s*:\s*([0-9.]+)(px|pt)", scale,
                      self._base_html, flags=re.I)
        def scale_width(match):
            value = float(match.group(1)) * factor
            return "width:%0.2fpx" % value
        html = re.sub(r"width\s*:\s*([0-9.]+)px", scale_width,
                      html, flags=re.I)
        html = re.sub(r"(<body[^>]*>)", r"\1<style>body{font-size:%0.2fpx}</style>" % (14 * factor), html, count=1, flags=re.I)
        self.output.setHtml(html)
        self.zoom_label.setText("%d%%" % round(factor * 100))

    def _on_anchor_clicked(self, url):
        self.link_clicked.emit(url)

    @staticmethod
    def _find_all(text, q):
        res, start = [], 0
        ql, tl = q.lower(), text.lower()
        while True:
            i = tl.find(ql, start)
            if i == -1:
                break
            res.append((i, i + len(q)))
            start = i + 1
        return res

    @staticmethod
    def _clear_highlights(browser):
        doc = browser.document()
        cur = QtGui.QTextCursor(doc)
        cur.setPosition(0)
        cur.setPosition(len(browser.toPlainText()),
                        QtGui.QTextCursor.KeepAnchor)
        fmt = QtGui.QTextCharFormat()
        fmt.setBackground(QtGui.QBrush(QtCore.Qt.transparent))
        fmt.setForeground(QtGui.QBrush(QtGui.QColor(theme.TEXT_COLOR)))
        cur.mergeCharFormat(fmt)

    @staticmethod
    def _highlight_and_center(browser, matches, idx):
        doc = browser.document()
        plain = browser.toPlainText()
        cur0 = QtGui.QTextCursor(doc)
        cur0.setPosition(0)
        cur0.setPosition(len(plain), QtGui.QTextCursor.KeepAnchor)
        fmt_clear = QtGui.QTextCharFormat()
        fmt_clear.setBackground(QtGui.QBrush(QtCore.Qt.transparent))
        fmt_clear.setForeground(QtGui.QBrush(QtGui.QColor(theme.TEXT_COLOR)))
        cur0.mergeCharFormat(fmt_clear)
        for i, (s, e) in enumerate(matches):
            cur = QtGui.QTextCursor(doc)
            cur.setPosition(s)
            cur.setPosition(e, QtGui.QTextCursor.KeepAnchor)
            fmt = QtGui.QTextCharFormat()
            if i == idx:
                fmt.setBackground(
                    QtGui.QBrush(QtGui.QColor(255, 140, 0)))
            else:
                fmt.setBackground(
                    QtGui.QBrush(QtGui.QColor(255, 220, 90)))
            fmt.setForeground(QtGui.QBrush(QtGui.QColor(30, 30, 46)))
            cur.mergeCharFormat(fmt)
        s, e = matches[idx]
        cur = QtGui.QTextCursor(doc)
        cur.setPosition(s)
        cur.setPosition(e, QtGui.QTextCursor.KeepAnchor)
        browser.setTextCursor(cur)
        browser.ensureCursorVisible()

    def _set_match_ui(self):
        total = len(self._matches)
        self.answer_search.set_counter(
            self._match_idx + 1 if total else 0, total)

    def _on_search_changed(self, text):
        q = text.strip()
        if not q:
            self._clear_highlights(self.output)
            self._matches = []
            self._match_idx = -1
            self._set_match_ui()
            return
        self._matches = self._find_all(self.output.toPlainText(), q)
        if not self._matches:
            self._match_idx = -1
            self._set_match_ui()
            self._clear_highlights(self.output)
            return
        self._match_idx = 0
        self._highlight_and_center(
            self.output, self._matches, self._match_idx)
        self._set_match_ui()

    def search_answer(self):
        q = self.answer_search.text().strip()
        if not q:
            self._on_search_changed("")
            return
        self._on_search_changed(q)
        if not self._matches:
            QtWidgets.QMessageBox.information(
                self, "Поиск", "«%s» не найдено." % q)

    def prev_match(self):
        if not self._matches:
            return
        self._match_idx = (self._match_idx - 1) % len(self._matches)
        self._highlight_and_center(
            self.output, self._matches, self._match_idx)
        self._set_match_ui()

    def next_match(self):
        if not self._matches:
            return
        self._match_idx = (self._match_idx + 1) % len(self._matches)
        self._highlight_and_center(
            self.output, self._matches, self._match_idx)
        self._set_match_ui()

    def closeEvent(self, event):
        # Закрытие окна ответа снимает все его выделения —
        # при повторном открытии чистое окно.
        self._matches = []
        self._match_idx = -1
        self.answer_search.clear()
        super().closeEvent(event)
