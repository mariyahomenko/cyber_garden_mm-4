import pymupdf as fitz
from PyQt5 import QtWidgets, QtCore, QtGui
from .. import theme
from .. import pdfdoc as pdfdoc_mod
from ..pdfdoc import SEARCH_MODES, MODE_PHRASE, MODE_WORDS, MODE_SUBSTRING
from .widgets import IconButton, InlineIconButton


class TickOverlay(QtWidgets.QWidget):
    """Узкая полоска справа: отметки страниц с совпадениями поиска."""
    def __init__(self, total, parent=None):
        super().__init__(parent)
        self.total = max(1, total)
        self.pages = set()
        self.setFixedWidth(6)

    def set_pages(self, pages):
        self.pages = set(pages)
        self.update()

    def paintEvent(self, _event):
        p = QtGui.QPainter(self)
        p.fillRect(self.rect(), QtGui.QColor(theme.VIEW_BG))
        h = max(1, self.height())
        for pg in self.pages:
            y = int((pg + 0.5) / self.total * h)
            p.fillRect(0, max(0, y - 2), self.width(), 4,
                       QtGui.QColor(255, 200, 60))
        p.end()


class PDFViewerWindow(QtWidgets.QMainWindow):
    def __init__(self, pdf_doc, page_no=0, focus_rect=None,
                 search_query=None, parent=None):
        super().__init__(parent)
        self.pdf_doc = pdf_doc
        self.setWindowTitle("Просмотр — %s" % pdf_doc.name)
        self.resize(1300, 880)

        self.zoom = 1.3
        self.page_items = []
        self.search_results = []
        self.search_idx = -1
        self.nav_stack = []
        self.nav_idx = -1
        self._pulse_items = []
        self._thumb_cache = {}
        self._ai_highlight_items = []
        self._rubber_start = None
        self._rubber_active = False
        self._rubber_item = None
        self._text_page = -1
        self._saved_split_sizes = None

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        outer = QtWidgets.QHBoxLayout(central)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(8)
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        outer.addWidget(splitter)
        self._splitter = splitter

        self.left_wrap = QtWidgets.QWidget()
        self.left_wrap.setMinimumWidth(28)
        lv = QtWidgets.QVBoxLayout(self.left_wrap)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(4)

        nav_bar = QtWidgets.QHBoxLayout()
        lv.addLayout(nav_bar)
        self.btn_collapse = QtWidgets.QPushButton("‹")
        self.btn_collapse.setFixedWidth(28)
        self.btn_collapse.setToolTip("Свернуть/развернуть панель")
        self.btn_collapse.clicked.connect(self._toggle_left_panel)
        nav_bar.addWidget(self.btn_collapse)
        nav_bar.addStretch(1)

        self.left = QtWidgets.QTabWidget()
        lv.addWidget(self.left, 1)

        self.thumb_list = QtWidgets.QListWidget()
        self.thumb_list.setIconSize(QtCore.QSize(100, 140))
        self.thumb_list.itemClicked.connect(self._thumb_clicked)
        self.left.addTab(self.thumb_list, "Страницы")

        self.bm_list = QtWidgets.QListWidget()
        self.bm_list.itemDoubleClicked.connect(self._bm_jump)
        self.bm_list.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.bm_list.customContextMenuRequested.connect(self._bm_menu)
        self.left.addTab(self.bm_list, "Закладки")

        splitter.addWidget(self.left_wrap)
        splitter.setCollapsible(0, False)

        center = QtWidgets.QWidget()
        cv = QtWidgets.QVBoxLayout(center)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.setSpacing(6)

        tb1 = QtWidgets.QHBoxLayout()
        cv.addLayout(tb1)

        self.search_input = QtWidgets.QLineEdit()
        self.search_input.setPlaceholderText("Поиск в документе... (Ctrl+F)")
        self.search_input.textChanged.connect(self._on_search_text_changed)
        self.search_input.returnPressed.connect(
            lambda: self.run_search(silent=False))
        tb1.addWidget(self.search_input, 1)

        self._menu_btn_size = 26
        self.search_btn_menu = InlineIconButton(
            "menu", "Настройки поиска", self.search_input,
            size=self._menu_btn_size)

        self.search_menu = QtWidgets.QMenu(self.search_btn_menu)
        self.act_case = self.search_menu.addAction("Учитывать регистр")
        self.act_case.setCheckable(True)
        self.act_whole = self.search_menu.addAction("Только слово целиком")
        self.act_whole.setCheckable(True)
        self.search_btn_menu.setMenu(self.search_menu)

        self.search_input.setTextMargins(0, 0, self._menu_btn_size + 6, 0)

        self.btn_search = QtWidgets.QPushButton("Поиск")
        self.btn_search.setFixedHeight(36)
        self.btn_search.setFixedWidth(70)
        self.btn_search.clicked.connect(lambda: self.run_search(silent=False))
        tb1.addWidget(self.btn_search)

        self.btn_prev = QtWidgets.QPushButton("↑")
        self.btn_prev.setFixedSize(36, 36)
        self.btn_prev.clicked.connect(self.prev_match)
        self.btn_prev.setEnabled(False)
        tb1.addWidget(self.btn_prev)

        self.btn_next = QtWidgets.QPushButton("↓")
        self.btn_next.setFixedSize(36, 36)
        self.btn_next.clicked.connect(self.next_match)
        self.btn_next.setEnabled(False)
        tb1.addWidget(self.btn_next)

        self.match_label = QtWidgets.QLabel("0/0")
        tb1.addWidget(self.match_label)

        lbl = QtWidgets.QLabel("Стр.:")
        tb1.addWidget(lbl)
        self.page_spin = QtWidgets.QSpinBox()
        self.page_spin.setMinimum(1)
        self.page_spin.setMaximum(max(1, len(pdf_doc.doc)))
        self.page_spin.setFixedWidth(80)
        self.page_spin.setAlignment(QtCore.Qt.AlignCenter)
        self.page_spin.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        self.page_spin.valueChanged.connect(lambda v: self.nav_go(v - 1, None))
        tb1.addWidget(self.page_spin)

        self.btn_page_up = IconButton("up", "Предыдущая страница", size=30)
        self.btn_page_up.clicked.connect(lambda: self._page_step(-1))
        tb1.addWidget(self.btn_page_up)
        self.btn_page_down = IconButton("down", "Следующая страница", size=30)
        self.btn_page_down.clicked.connect(lambda: self._page_step(+1))
        tb1.addWidget(self.btn_page_down)

        self.btn_highlight = IconButton("marker", "Маркер", size=36)
        self.btn_highlight.setCheckable(True)
        self.btn_highlight.setToolTip(
            "Вкл/выкл: выделяйте область рамкой мышью, чтобы поставить маркер. "
            "Повторное выделение поверх маркера снимает его.")
        self.btn_highlight.toggled.connect(self._on_highlight_toggled)
        tb1.addWidget(self.btn_highlight)

        self.btn_bm = IconButton("bookmark", "Добавить закладку", size=36)
        self.btn_bm.setFixedWidth(46)
        self.btn_bm.setToolTip("Закладка на текущую страницу")
        self.btn_bm.clicked.connect(self.add_bookmark)
        tb1.addWidget(self.btn_bm)

        self.btn_text = IconButton("copy", "Текст страницы: выделять/копировать",
                                   size=36)
        self.btn_text.setCheckable(True)
        self.btn_text.setToolTip(
            "Панель текста страницы: можно выделять и копировать (Ctrl+C).")
        self.btn_text.toggled.connect(self._on_text_toggled)
        tb1.addWidget(self.btn_text)

        tb2 = QtWidgets.QHBoxLayout()
        cv.addLayout(tb2)
        self.btn_zoom_out = QtWidgets.QPushButton("-")
        self.btn_zoom_out.setFixedSize(36, 36)
        self.btn_zoom_out.clicked.connect(lambda: self._set_zoom(self.zoom / 1.2))
        tb2.addWidget(self.btn_zoom_out)

        self.zoom_label = QtWidgets.QLabel("130%")
        self.zoom_label.setFixedWidth(48)
        self.zoom_label.setAlignment(QtCore.Qt.AlignCenter)
        tb2.addWidget(self.zoom_label)

        self.btn_zoom_in = QtWidgets.QPushButton("+")
        self.btn_zoom_in.setFixedSize(36, 36)
        self.btn_zoom_in.clicked.connect(lambda: self._set_zoom(self.zoom * 1.2))
        tb2.addWidget(self.btn_zoom_in)

        self.btn_fit = QtWidgets.QPushButton("По ширине")
        self.btn_fit.setFixedHeight(36)
        self.btn_fit.clicked.connect(self._fit_width)
        tb2.addWidget(self.btn_fit)

        self.btn_100 = QtWidgets.QPushButton("100%")
        self.btn_100.setFixedHeight(36)
        self.btn_100.clicked.connect(lambda: self._set_zoom(1.0))
        tb2.addWidget(self.btn_100)

        tb2.addStretch(1)

        scene_wrap = QtWidgets.QWidget()
        sw = QtWidgets.QHBoxLayout(scene_wrap)
        sw.setContentsMargins(0, 0, 0, 0)
        sw.setSpacing(0)
        self.scene = QtWidgets.QGraphicsScene()
        self.view = QtWidgets.QGraphicsView(self.scene)
        self.view.setRenderHints(QtGui.QPainter.Antialiasing |
                                 QtGui.QPainter.SmoothPixmapTransform)
        self.view.setDragMode(QtWidgets.QGraphicsView.ScrollHandDrag)
        self.view.viewport().installEventFilter(self)
        sw.addWidget(self.view, 1)
        self.ticks = TickOverlay(len(pdf_doc.doc))
        sw.addWidget(self.ticks)
        cv.addWidget(scene_wrap, 1)

        splitter.addWidget(center)

        self.text_panel = QtWidgets.QWidget()
        self.text_panel.setMinimumWidth(0)
        tv = QtWidgets.QVBoxLayout(self.text_panel)
        tv.setContentsMargins(6, 6, 6, 6)
        tv.setSpacing(6)

        text_head = QtWidgets.QHBoxLayout()
        tv.addLayout(text_head)
        self.text_title = QtWidgets.QLabel("Текст страницы")
        text_head.addWidget(self.text_title, 1)
        self.btn_ocr = QtWidgets.QPushButton("Распознать (OCR)")
        self.btn_ocr.setToolTip(
            "Запустить OCR для текущей страницы (для сканов без текста)")
        self.btn_ocr.clicked.connect(self._run_ocr_for_current_page)
        self.btn_ocr.setVisible(False)
        text_head.addWidget(self.btn_ocr)
        self.btn_copy_page = QtWidgets.QPushButton("Копировать")
        self.btn_copy_page.setToolTip(
            "Скопировать весь текст текущей страницы в буфер")
        self.btn_copy_page.clicked.connect(self.copy_page_text)
        text_head.addWidget(self.btn_copy_page)

        self.text_view = QtWidgets.QTextBrowser()
        self.text_view.setOpenExternalLinks(False)
        self.text_view.setLineWrapMode(QtWidgets.QTextEdit.WidgetWidth)
        self.text_view.setWordWrapMode(
            QtGui.QTextOption.WrapAtWordBoundaryOrAnywhere)
        self.text_view.setTextInteractionFlags(
            QtCore.Qt.TextSelectableByMouse
            | QtCore.Qt.TextSelectableByKeyboard)
        tv.addWidget(self.text_view, 1)

        splitter.addWidget(self.text_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([280, 900, 0])
        self.text_panel.setVisible(False)

        QtWidgets.QShortcut(
            QtGui.QKeySequence("Ctrl+F"), self).activated.connect(
                lambda: (self.search_input.setFocus(),
                         self.search_input.selectAll()))
        QtWidgets.QShortcut(
            QtGui.QKeySequence("F3"), self).activated.connect(self.next_match)
        QtWidgets.QShortcut(
            QtGui.QKeySequence("Shift+F3"), self).activated.connect(
                self.prev_match)
        QtWidgets.QShortcut(
            QtGui.QKeySequence("Esc"), self).activated.connect(
                lambda: self.view.setFocus())

        self.retheme()
        self._populate_thumbs()
        self._refresh_bookmarks()
        self._render_all_pages()
        self._draw_highlights()
        self._draw_search_highlights()
        self._draw_ai_highlight()

        if 0 <= page_no < len(self.page_items):
            self.nav_go(page_no, focus_rect, push=False)
        if search_query:
            self.search_input.blockSignals(True)
            self.search_input.setText(search_query)
            self.search_input.blockSignals(False)
            self.run_search()

        self._update_nav_buttons()
        self._center_on_screen()

    def retheme(self):
        self.setStyleSheet(theme.LABEL_QSS)
        self.view.setStyleSheet(
            "QGraphicsView { background-color:%s; border:none; }"
            % theme.VIEW_BG)
        for w in (self.search_input, self.page_spin, self.text_view):
            w.setStyleSheet(theme.INPUT_QSS)
        self.search_btn_menu.retheme()
        self.btn_page_up.retheme()
        self.btn_page_down.retheme()
        self.btn_highlight.retheme()
        self.btn_bm.retheme()
        self.btn_text.retheme()
        for w in (self.btn_collapse, self.btn_search, self.btn_prev,
                  self.btn_next, self.btn_zoom_out, self.btn_zoom_in,
                  self.btn_fit, self.btn_100, self.btn_copy_page,
                  self.btn_ocr):
            w.setStyleSheet(theme.BUTTON_QSS)
        for w in (self.match_label, self.zoom_label, self.text_title):
            w.setStyleSheet(theme.LABEL_QSS)
        for w in (self.thumb_list, self.bm_list):
            w.setStyleSheet(theme.INPUT_QSS)
        self.ticks.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._place_search_menu_button()

    def _place_search_menu_button(self):
        if not hasattr(self, "search_btn_menu"):
            return
        h = self.search_input.height()
        s = self._menu_btn_size
        y = (h - s) // 2
        x = self.search_input.width() - s - 6
        self.search_btn_menu.move(x, y)
        self.search_btn_menu.raise_()

    def showEvent(self, event):
        super().showEvent(event)
        QtCore.QTimer.singleShot(0, self._place_search_menu_button)

    def _center_on_screen(self):
        scr = QtWidgets.QApplication.primaryScreen().availableGeometry()
        w = min(1300, int(scr.width() * 0.9))
        h = min(880, int(scr.height() * 0.9))
        self.resize(w, h)
        self.move(scr.center() - self.rect().center())

    def _toggle_left_panel(self):
        if self.left.isVisible():
            self._left_saved = self.left_wrap.width()
            self.left.setVisible(False)
            self.left_wrap.setFixedWidth(28)
            self.btn_collapse.setText("›")
        else:
            self.left.setVisible(True)
            self.left_wrap.setMinimumWidth(120)
            self.left_wrap.setMaximumWidth(16777215)
            self.left_wrap.resize(getattr(self, "_left_saved", 200),
                                  self.left_wrap.height())
            self.btn_collapse.setText("‹")

    def _on_text_toggled(self, checked):
        if checked:
            if self._saved_split_sizes is None:
                self._saved_split_sizes = self._splitter.sizes()
            self.text_panel.setVisible(True)
            sizes = self._splitter.sizes()
            total = sum(sizes) if sum(sizes) else self._splitter.width()
            left = sizes[0] if sizes and sizes[0] > 0 else 280
            if self._saved_split_sizes and self._saved_split_sizes[0] > 0:
                left = self._saved_split_sizes[0]
            target_text = max(260, int(total * 0.35))
            target_center = max(300, total - target_text - left)
            self._splitter.setSizes([left, target_center, target_text])
            self._update_text_panel(force=True)
        else:
            cur = self._splitter.sizes()
            left = cur[0] if cur and cur[0] > 0 else 280
            if self._saved_split_sizes and self._saved_split_sizes[0] > 0:
                left = self._saved_split_sizes[0]
            center = max(300, sum(cur) - left)
            self.text_panel.setVisible(False)
            self._splitter.setSizes([left, center, 0])
            self._saved_split_sizes = None

    def _update_text_panel(self, force=False):
        if not self.text_panel.isVisible():
            return
        pno = self._current_page()
        if pno == self._text_page and not force:
            return
        self._text_page = pno
        if not (0 <= pno < len(self.pdf_doc.doc)):
            return

        text = self.pdf_doc.pages_text[pno] or ""
        has_layer = self.pdf_doc.has_text_layer(pno)
        if (not has_layer) and len(text.strip()) < 20 \
                and pdfdoc_mod.OCR_AVAILABLE:
            text = self.pdf_doc.ocr_page(pno) or text
            has_layer = self.pdf_doc.has_text_layer(pno)

        if len(text.strip()) < 20:
            if pdfdoc_mod.OCR_AVAILABLE:
                msg = ("Текст не распознан (скан). "
                       "Нажмите «Распознать (OCR)» — если установлен "
                       "Tesseract (PyMuPDF-мост или pytesseract).")
                self.btn_ocr.setVisible(True)
            else:
                msg = ("Текст не распознан (скан). OCR-движок не найден: "
                       "установите Tesseract или pytesseract+Pillow, "
                       "чтобы включить распознавание.")
                self.btn_ocr.setVisible(False)
            self.text_view.setHtml(
                '<div style="color:%s; font-size:13px;">%s</div>'
                % (theme.html_colors()["hint"], msg))
            self.text_title.setText("Текст страницы %d" % (pno + 1))
            return

        self.btn_ocr.setVisible(not has_layer)
        safe = (text.replace("&", "&amp;").replace("<", "&lt;")
                    .replace(">", "&gt;"))
        safe = safe.replace("\n", "<br>")
        prefix = ""
        if not has_layer:
            prefix = ('<div style="color:%s; font-size:12px; '
                      'margin-bottom:4px;">[OCR]</div>'
                      % theme.html_colors()["hint"])
        self.text_view.setHtml(
            '%s<div style="color:%s; font-size:13px;">%s</div>'
            % (prefix, theme.html_colors()["text"], safe))
        self.text_title.setText("Текст страницы %d" % (pno + 1))

    def _run_ocr_for_current_page(self):
        pno = self._current_page()
        if not (0 <= pno < len(self.pdf_doc.doc)):
            return
        if not pdfdoc_mod.OCR_AVAILABLE:
            QtWidgets.QMessageBox.information(
                self, "OCR",
                "OCR-движок не найден. Установите Tesseract "
                "(PyMuPDF-мост) или пакеты pytesseract и Pillow.")
            return
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            text = self.pdf_doc.ocr_page(pno)
        except Exception as e:
            QtWidgets.QApplication.restoreOverrideCursor()
            QtWidgets.QMessageBox.warning(
                self, "OCR", "Ошибка OCR: %s" % e)
            return
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
        if not text.strip():
            QtWidgets.QMessageBox.information(
                self, "OCR",
                "На странице не удалось распознать текст.")
            return
        self._text_page = -1
        self._update_text_panel(force=True)

    def copy_page_text(self):
        pno = self._current_page()
        if 0 <= pno < len(self.pdf_doc.pages_text):
            QtWidgets.QApplication.clipboard().setText(
                self.pdf_doc.pages_text[pno] or "")
            self.statusBar().showMessage("Текст страницы скопирован", 2000)

    def nav_go(self, pno, rect=None, push=True):
        if not (0 <= pno < len(self.page_items)):
            return
        if push:
            del self.nav_stack[self.nav_idx + 1:]
            self.nav_stack.append((pno, rect))
            self.nav_idx = len(self.nav_stack) - 1
        self._center_on_page(pno)
        if rect is not None:
            self._center_on_rect(pno, rect)
        self._update_nav_buttons()

    def nav_back(self):
        if self.nav_idx > 0:
            self.nav_idx -= 1
            pno, rect = self.nav_stack[self.nav_idx]
            self._center_on_page(pno)
            if rect is not None:
                self._center_on_rect(pno, rect)
            self._update_nav_buttons()

    def nav_forward(self):
        if self.nav_idx < len(self.nav_stack) - 1:
            self.nav_idx += 1
            pno, rect = self.nav_stack[self.nav_idx]
            self._center_on_page(pno)
            if rect is not None:
                self._center_on_rect(pno, rect)
            self._update_nav_buttons()

    def _update_nav_buttons(self):
        pass

    def _page_step(self, delta):
        if not self.page_items:
            return
        target = max(0, min(len(self.page_items) - 1,
                            self._current_page() + delta))
        self.nav_go(target, None)

    def pulse(self, pno, rect):
        self._clear_pulse()
        if not (0 <= pno < len(self.page_items)) or rect is None:
            return
        item, _, _, zoom = self.page_items[pno]
        ox, oy = item.pos().x(), item.pos().y()
        r = QtCore.QRectF(
            ox + rect.x0 * zoom - 4,
            oy + rect.y0 * zoom - 4,
            (rect.x1 - rect.x0) * zoom + 8,
            (rect.y1 - rect.y0) * zoom + 8)
        pen = QtGui.QPen(QtGui.QColor(255, 140, 0), 3)
        brush = QtGui.QBrush(QtGui.QColor(255, 170, 0, 90))
        pulse_item = self.scene.addRect(r, pen, brush)
        pulse_item.setZValue(20)
        self._pulse_items.append(pulse_item)
        QtCore.QTimer.singleShot(2500, self._clear_pulse)

    def _clear_pulse(self):
        for it in self._pulse_items:
            try:
                self.scene.removeItem(it)
            except Exception:
                pass
        self._pulse_items = []

    def _thumb(self, pno):
        if pno in self._thumb_cache:
            return self._thumb_cache[pno]
        page = self.pdf_doc.doc[pno]
        pix = page.get_pixmap(matrix=fitz.Matrix(0.18, 0.18))
        img = QtGui.QImage(pix.samples, pix.width, pix.height,
                           pix.stride, QtGui.QImage.Format_RGB888)
        pm = QtGui.QPixmap.fromImage(img)
        self._thumb_cache[pno] = pm
        return pm

    def _populate_thumbs(self):
        self.thumb_list.clear()
        for pno in range(len(self.pdf_doc.doc)):
            it = QtWidgets.QListWidgetItem(
                QtGui.QIcon(self._thumb(pno)), "")
            it.setData(QtCore.Qt.UserRole, pno)
            it.setToolTip("Страница %d" % (pno + 1))
            self.thumb_list.addItem(it)

    def _thumb_clicked(self, item):
        self.nav_go(item.data(QtCore.Qt.UserRole))

    def add_bookmark(self):
        pno = self._current_page()
        dlg = QtWidgets.QInputDialog(self)
        dlg.setInputMode(QtWidgets.QInputDialog.TextInput)
        dlg.setWindowTitle("Закладка")
        dlg.setLabelText("Заметка (можно пусто):")
        dlg.setTextValue("")
        sh = dlg.sizeHint()
        dlg.resize(int(sh.width() * 1.5), int(sh.height() * 1.5))
        if dlg.exec_() != QtWidgets.QDialog.Accepted:
            return
        note = dlg.textValue()
        self.pdf_doc.bookmarks.append(
            {"page": pno, "rect": None, "note": note.strip()})
        self._refresh_bookmarks()

    def _refresh_bookmarks(self):
        self.bm_list.clear()
        for i, bm in enumerate(self.pdf_doc.bookmarks):
            label = "Стр. %d" % (bm["page"] + 1)
            if bm.get("note"):
                label += " — " + bm["note"]
            it = QtWidgets.QListWidgetItem("☐ " + label)
            it.setData(QtCore.Qt.UserRole, i)
            self.bm_list.addItem(it)

    def _bm_jump(self, item):
        i = item.data(QtCore.Qt.UserRole)
        if i is None or i >= len(self.pdf_doc.bookmarks):
            return
        bm = self.pdf_doc.bookmarks[i]
        rect = fitz.Rect(bm["rect"]) if bm.get("rect") else None
        self.nav_go(bm["page"], rect)

    def _bm_menu(self, pos):
        item = self.bm_list.itemAt(pos)
        if item is None:
            return
        menu = QtWidgets.QMenu(self)
        act_del = menu.addAction("Удалить закладку")
        act = menu.exec_(self.bm_list.mapToGlobal(pos))
        if act == act_del:
            i = item.data(QtCore.Qt.UserRole)
            if i is not None and i < len(self.pdf_doc.bookmarks):
                del self.pdf_doc.bookmarks[i]
                self._refresh_bookmarks()

    def _current_page(self):
        c = self.view.mapToScene(self.view.viewport().rect().center())
        best, bd = 0, None
        for item, pno, _page, _z in self.page_items:
            d = abs(item.sceneBoundingRect().center().y() - c.y())
            if bd is None or d < bd:
                bd, best = d, pno
        return best

    def _set_zoom(self, z, keep=True):
        cur = self._current_page() if keep else None
        self.zoom = max(0.3, min(3.5, z))
        self.zoom_label.setText("%d%%" % round(self.zoom * 100))
        self._render_all_pages()
        self._draw_highlights()
        self._draw_search_highlights()
        self._draw_ai_highlight()
        if cur is not None:
            self._center_on_page(cur)

    def _fit_width(self):
        if not self.pdf_doc.doc:
            return
        w = self.pdf_doc.doc[0].rect.width
        if w > 0:
            self._set_zoom((self.view.viewport().width() - 30) / w)

    def eventFilter(self, obj, event):
        if obj is self.view.viewport():
            et = event.type()
            if et == QtCore.QEvent.Wheel:
                if event.modifiers() & QtCore.Qt.ControlModifier:
                    self._set_zoom(
                        self.zoom * (1.15 if event.angleDelta().y() > 0
                                     else 1 / 1.15))
                    return True
            elif et == QtCore.QEvent.MouseButtonPress:
                if event.button() == QtCore.Qt.LeftButton:
                    if self.btn_highlight.isChecked():
                        self._rubber_start = self.view.mapToScene(event.pos())
                        self._rubber_active = True
                        return True
            elif et == QtCore.QEvent.MouseMove:
                if self._rubber_active and self._rubber_start is not None:
                    self._update_rubber_feedback(event.pos())
                    return True
            elif et == QtCore.QEvent.MouseButtonRelease:
                if (event.button() == QtCore.Qt.LeftButton
                        and self._rubber_active):
                    self._finish_rubber(event.pos())
                    return True
        return super().eventFilter(obj, event)

    def _update_rubber_feedback(self, viewport_pos):
        start = self._rubber_start
        end = self.view.mapToScene(viewport_pos)
        rect = QtCore.QRectF(start, end).normalized()
        if self._rubber_item is not None:
            try:
                self.scene.removeItem(self._rubber_item)
            except Exception:
                pass
        pen = QtGui.QPen(QtGui.QColor(255, 170, 0), 1, QtCore.Qt.DashLine)
        self._rubber_item = self.scene.addRect(
            rect, pen, QtGui.QBrush(QtGui.QColor(255, 170, 0, 40)))
        self._rubber_item.setZValue(30)

    def _finish_rubber(self, viewport_pos):
        start = self._rubber_start
        end = self.view.mapToScene(viewport_pos)
        rect = QtCore.QRectF(start, end).normalized()
        self._rubber_start = None
        self._rubber_active = False
        if self._rubber_item is not None:
            try:
                self.scene.removeItem(self._rubber_item)
            except Exception:
                pass
            self._rubber_item = None

        if rect.width() < 3 or rect.height() < 3:
            return

        target_pno = None
        for item, pno, _page, zoom in self.page_items:
            if item.sceneBoundingRect().intersects(rect):
                target_pno = pno
                break
        if target_pno is None:
            return

        item, pno, page, zoom = self.page_items[target_pno]
        ox, oy = item.pos().x(), item.pos().y()

        pdf_rect = fitz.Rect(
            (rect.left() - ox) / zoom,
            (rect.top() - oy) / zoom,
            (rect.right() - ox) / zoom,
            (rect.bottom() - oy) / zoom)

        to_remove = []
        for (hp, hr), _c in list(self.pdf_doc.highlights.items()):
            if hp != pno:
                continue
            existing = fitz.Rect(*hr)
            if existing.intersects(pdf_rect):
                to_remove.append((hp, hr))

        if to_remove:
            for k in to_remove:
                self.pdf_doc.highlights.pop(k, None)
        else:
            self.pdf_doc.toggle_highlight(pno, pdf_rect)

        self._draw_highlights()

    def _on_highlight_toggled(self, checked):
        if checked:
            self.view.setDragMode(QtWidgets.QGraphicsView.NoDrag)
            self.view.viewport().setCursor(QtCore.Qt.CrossCursor)
        else:
            self.view.setDragMode(QtWidgets.QGraphicsView.ScrollHandDrag)
            self.view.viewport().unsetCursor()

    def _render_all_pages(self):
        self.scene.clear()
        self._pulse_items = []
        self._ai_highlight_items = []
        self._rubber_item = None
        self.page_items = []
        y = 0
        for pno, page in enumerate(self.pdf_doc.doc):
            pix = page.get_pixmap(matrix=fitz.Matrix(self.zoom, self.zoom))
            img = QtGui.QImage(pix.samples, pix.width, pix.height,
                               pix.stride, QtGui.QImage.Format_RGB888)
            pm = QtGui.QPixmap.fromImage(img)
            item = self.scene.addPixmap(pm)
            item.setPos(0, y)
            item.setData(0, pno)
            self.page_items.append((item, pno, page, self.zoom))
            y += pix.height + 20
        self.scene.setSceneRect(self.scene.itemsBoundingRect())

    def _center_on_page(self, pno):
        if not (0 <= pno < len(self.page_items)):
            return
        self.view.centerOn(self.page_items[pno][0])
        self.page_spin.blockSignals(True)
        self.page_spin.setValue(pno + 1)
        self.page_spin.blockSignals(False)
        self.thumb_list.blockSignals(True)
        self.thumb_list.setCurrentRow(pno)
        self.thumb_list.blockSignals(False)
        self._draw_ai_highlight()
        self._update_text_panel()

    def _center_on_rect(self, pno, rect):
        if not (0 <= pno < len(self.page_items)):
            return
        item, _, _, zoom = self.page_items[pno]
        ox, oy = item.pos().x(), item.pos().y()
        target = QtCore.QRectF(
            ox + rect.x0 * zoom - 50, oy + rect.y0 * zoom - 50,
            (rect.x1 - rect.x0) * zoom + 100,
            (rect.y1 - rect.y0) * zoom + 100)
        self.view.centerOn(target.center())
        self._draw_ai_highlight()

    def _draw_highlights(self):
        for it in list(self.scene.items()):
            if it.data(1) == "user_highlight":
                self.scene.removeItem(it)
        for (hp, hr), _c in self.pdf_doc.highlights.items():
            if hp >= len(self.page_items):
                continue
            item, _, _, zoom = self.page_items[hp]
            ox, oy = item.pos().x(), item.pos().y()
            r = QtCore.QRectF(
                ox + hr[0] * zoom, oy + hr[1] * zoom,
                (hr[2] - hr[0]) * zoom, (hr[3] - hr[1]) * zoom)
            el = self.scene.addRect(r, QtGui.QPen(QtCore.Qt.NoPen),
                                    QtGui.QBrush(QtGui.QColor(255, 170, 0, 130)))
            el.setData(1, "user_highlight")
            el.setZValue(10)

    def _draw_search_highlights(self):
        for it in list(self.scene.items()):
            if it.data(1) == "search_highlight":
                self.scene.removeItem(it)
        items = list(self.pdf_doc.search_highlights.keys())
        for i, (hp, hr) in enumerate(items):
            if hp >= len(self.page_items):
                continue
            item, _, _, zoom = self.page_items[hp]
            ox, oy = item.pos().x(), item.pos().y()
            r = QtCore.QRectF(
                ox + hr[0] * zoom - 1, oy + hr[1] * zoom - 1,
                (hr[2] - hr[0]) * zoom + 2,
                (hr[3] - hr[1]) * zoom + 2)
            if i == self.search_idx:
                pen = QtGui.QPen(QtGui.QColor(255, 90, 0, 220), 2)
                brush = QtGui.QBrush(QtGui.QColor(255, 170, 0, 130))
            else:
                pen = QtGui.QPen(QtGui.QColor(255, 200, 0, 180), 1)
                brush = QtGui.QBrush(QtGui.QColor(255, 220, 60, 70))
            el = self.scene.addRect(r, pen, brush)
            el.setData(1, "search_highlight")
            el.setZValue(5)
        self.ticks.set_pages(hp for hp, _hr in items)

    def _draw_ai_highlight(self):
        for it in self._ai_highlight_items:
            try:
                self.scene.removeItem(it)
            except Exception:
                pass
        self._ai_highlight_items = []
        for pno, rect in self.pdf_doc.get_ai_highlights():
            if not (0 <= pno < len(self.page_items)):
                continue
            item, _, _, zoom = self.page_items[pno]
            ox, oy = item.pos().x(), item.pos().y()
            r = QtCore.QRectF(
                ox + rect.x0 * zoom - 3, oy + rect.y0 * zoom - 3,
                (rect.x1 - rect.x0) * zoom + 6,
                (rect.y1 - rect.y0) * zoom + 6)
            pen = QtGui.QPen(QtGui.QColor(140, 100, 255, 230), 2,
                             QtCore.Qt.DashLine)
            brush = QtGui.QBrush(QtGui.QColor(140, 100, 255, 70))
            el = self.scene.addRect(r, pen, brush)
            el.setZValue(15)
            self._ai_highlight_items.append(el)

    # ============================ поиск ============================
    def _on_search_text_changed(self, text):
        if not text.strip():
            self.pdf_doc.clear_search_highlights()
            self.search_results = []
            self.search_idx = -1
            self.match_label.setText("0/0")
            self.btn_prev.setEnabled(False)
            self.btn_next.setEnabled(False)
            self._draw_search_highlights()

    def run_search(self, silent=False):
        q = self.search_input.text().strip()
        self.pdf_doc.clear_search_highlights()
        self.search_results = []
        self.search_idx = -1
        if not q:
            self._reset_search_ui()
            return

        case_sensitive = self.act_case.isChecked()
        whole_word = self.act_whole.isChecked()

        if whole_word:
            mode = MODE_WORDS
        else:
            if " " in q:
                mode = MODE_PHRASE
            else:
                mode = MODE_SUBSTRING

        try:
            self.search_results = self.pdf_doc.search(q, mode, case_sensitive)
        except Exception as e:
            self.search_results = []
            if not silent:
                QtWidgets.QMessageBox.warning(
                    self, "Поиск", "Ошибка поиска: %s" % e)
        if not self.search_results:
            self._reset_search_ui()
            if not silent:
                QtWidgets.QMessageBox.information(
                    self, "Поиск", "«%s» не найдено." % q)
            return
        for r in self.search_results:
            self.pdf_doc.add_search_highlight(r["page"], r["rect"])
        self.search_idx = 0
        self._show_match()

    def _reset_search_ui(self):
        self.search_idx = -1
        self.match_label.setText("0/0")
        self.btn_prev.setEnabled(False)
        self.btn_next.setEnabled(False)
        self._draw_search_highlights()

    def _show_match(self):
        if not self.search_results:
            return
        r = self.search_results[self.search_idx]
        self.match_label.setText(
            "%d/%d" % (self.search_idx + 1, len(self.search_results)))
        self.btn_prev.setEnabled(True)
        self.btn_next.setEnabled(True)
        self._draw_search_highlights()
        self._center_on_page(r["page"])
        self._center_on_rect(r["page"], r["rect"])
        self.pulse(r["page"], r["rect"])

    def next_match(self):
        if self.search_results:
            self.search_idx = (self.search_idx + 1) % len(self.search_results)
            self._show_match()

    def prev_match(self):
        if self.search_results:
            self.search_idx = (self.search_idx - 1) % len(self.search_results)
            self._show_match()

    def closeEvent(self, event):
        self.pdf_doc.clear_search_highlights()
        self.pdf_doc.clear_ai_highlight()
        self.pdf_doc.thumbs.clear()
        self._thumb_cache.clear()
        super().closeEvent(event)
