import json
import os
from PyQt5 import QtWidgets, QtCore, QtGui

from .. import theme
from ..client import make_client, build_prompt, PROVIDERS
from ..parser import parse_answer, PLACEHOLDER_RE
from ..pdfdoc import PDFDocument, MODE_PHRASE, MODE_WORDS
from ..renderer import render_answer_html
from ..export_utils import export_json, export_tz_json
from .research_dialog import ResearchDialog
from .answer_window import AnswerWindow
from .pdf_viewer import PDFViewerWindow
from .widgets import (IconButton, SearchLineEdit, BarTextEdit,
                      BarTextBrowser, make_bar, BTN_SIZE)
import fitz

SETTINGS = QtCore.QSettings("CyberGarden", "CyberDoc")
APP_NAME = "CyberDoc"


class PDFSearchApp(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("%s — AI-ассистент по научным статьям" % APP_NAME)
        self.resize(1280, 820)
        self.docs = {}
        self.current_path = None
        self.viewer = None
        self.answer_window = None
        self.history = []
        self.history_idx = -1
        self._matches = []
        self._match_idx = -1

        self.provider = (SETTINGS.value("provider", "deepseek") or "deepseek")
        if self.provider not in PROVIDERS:
            self.provider = "deepseek"
        self.client = make_client(self.provider)

        central = QtWidgets.QWidget()
        central.setObjectName("Card")
        self.setCentralWidget(central)
        outer = QtWidgets.QVBoxLayout(central)
        outer.setContentsMargins(16, 16, 16, 14)
        outer.setSpacing(12)

        # Верхняя панель задаёт визуальную иерархию приложения.
        self.header = QtWidgets.QFrame()
        self.header.setObjectName("Header")
        header_layout = QtWidgets.QHBoxLayout(self.header)
        header_layout.setContentsMargins(18, 6, 18, 6)
        header_layout.setSpacing(12)
        self.header.setFixedHeight(44)
        brand_box = QtWidgets.QHBoxLayout()
        brand_box.setSpacing(10)
        self.brand_label = QtWidgets.QLabel("CYBERDOC")
        self.brand_label.setObjectName("Brand")
        self.subtitle_label = QtWidgets.QLabel("Умный поиск и проверка научных PDF")
        self.subtitle_label.setObjectName("Subtitle")
        brand_box.addWidget(self.brand_label)
        brand_box.addWidget(self.subtitle_label)
        header_layout.addLayout(brand_box)
        header_layout.addStretch(1)
        self.header_meta = QtWidgets.QLabel("0 документов")
        self.header_meta.setObjectName("Subtitle")
        header_layout.addWidget(self.header_meta)
        self.header_status = QtWidgets.QLabel("●  Готово к работе")
        self.header_status.setObjectName("StatusPill")
        header_layout.addWidget(self.header_status)
        outer.addWidget(self.header)

        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.splitter.setHandleWidth(6)
        self.splitter.setChildrenCollapsible(False)
        outer.addWidget(self.splitter)

        # --- левая панель (документы), ширина меняется разделителем ---
        self.docs_panel = QtWidgets.QWidget()
        self.docs_panel.setObjectName("Panel")
        self.docs_panel.setMinimumWidth(240)
        dv = QtWidgets.QVBoxLayout(self.docs_panel)
        dv.setContentsMargins(14, 14, 14, 14)
        dv.setSpacing(10)

        # Заголовок + кнопка сворачивания
        head = QtWidgets.QHBoxLayout()
        dv.addLayout(head)
        self.btn_collapse_docs = QtWidgets.QPushButton("‹")
        self.btn_collapse_docs.setFixedWidth(28)
        self.btn_collapse_docs.setToolTip("Свернуть/развернуть панель")
        self.btn_collapse_docs.clicked.connect(self._toggle_docs_panel)
        head.addWidget(self.btn_collapse_docs)

        self.docs_title = QtWidgets.QLabel("Библиотека PDF")
        self.docs_title.setAlignment(QtCore.Qt.AlignCenter)
        head.addWidget(self.docs_title, 1)

        # «заглушка» справа, чтобы заголовок был по центру
        spacer = QtWidgets.QWidget()
        spacer.setFixedWidth(28)
        head.addWidget(spacer)

        self.docs_subtitle = QtWidgets.QLabel("Документы  •  поиск  •  контекст")
        self.docs_subtitle.setAlignment(QtCore.Qt.AlignCenter)
        self.docs_subtitle.setObjectName("Subtitle")
        dv.addWidget(self.docs_subtitle)

        # контейнер содержимого панели, чтобы его можно было скрывать
        self.docs_body = QtWidgets.QWidget()
        dbv = QtWidgets.QVBoxLayout(self.docs_body)
        dbv.setContentsMargins(0, 0, 0, 0)
        dbv.setSpacing(8)
        dv.addWidget(self.docs_body, 1)

        # Ctrl+клик — выделить несколько, Shift+клик — диапазон
        self.docs_list = QtWidgets.QListWidget()
        self.docs_list.setSelectionMode(
            QtWidgets.QAbstractItemView.ExtendedSelection)
        self.docs_list.currentItemChanged.connect(self._doc_selected)
        self.docs_list.itemSelectionChanged.connect(
            self._update_search_placeholder)
        # PDF открывается двойным кликом по имени файла
        self.docs_list.itemDoubleClicked.connect(self._doc_double_clicked)
        dbv.addWidget(self.docs_list, 1)

        db = QtWidgets.QHBoxLayout()
        dbv.addLayout(db)
        self.btn_add_doc = QtWidgets.QPushButton("+ PDF")
        self.btn_add_doc.clicked.connect(lambda: self.load_pdf())
        db.addWidget(self.btn_add_doc)
        self.btn_del_doc = IconButton("close", "Убрать выбранные документы", size=42)
        self.btn_del_doc.setFixedWidth(46)
        self.btn_del_doc.setToolTip("Убрать выбранные документы из списка")
        self.btn_del_doc.clicked.connect(self.remove_current_doc)
        db.addWidget(self.btn_del_doc)

        # «Загрузить PDF»: под «+ PDF», над поиском по всем файлам
        self.btn_load = QtWidgets.QPushButton("Открыть окно PDF")
        self.btn_load.clicked.connect(lambda: self.open_pdf_viewer())
        dbv.addWidget(self.btn_load)

        self.docs_search = QtWidgets.QLineEdit()
        self.docs_search.setPlaceholderText("Поиск по документам...")
        self.docs_search.returnPressed.connect(self.search_all_docs)
        dbv.addWidget(self.docs_search)

        self.splitter.addWidget(self.docs_panel)
        self.splitter.setCollapsible(0, False)

        # --- центр ---
        center = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(center)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Поиск по ответу: скрыт, открывается кнопкой-лупой (или Ctrl+F).
        # Стрелки и счётчик лежат внутри поля, текст под них не заезжает.
        self.answer_search = SearchLineEdit("Поиск по ответу...")
        self.answer_search.textChanged.connect(self._on_answer_search_changed)
        self.answer_search.returnPressed.connect(self.search_answer_main)
        self.answer_search.prev_requested.connect(self.prev_match_main)
        self.answer_search.next_requested.connect(self.next_match_main)
        self.answer_search.hide()
        layout.addWidget(self.answer_search)

        # ====== Поле ответа (кнопки внутри поля, у нижнего края) ======
        self.output = BarTextBrowser()
        self.output.setObjectName("AnswerSurface")
        self.output.setOpenExternalLinks(False)
        self.output.setOpenLinks(False)
        self.output.anchorClicked.connect(self.on_link_clicked)
        self.output.setLineWrapMode(QtWidgets.QTextEdit.WidgetWidth)
        self.output.setWordWrapMode(
            QtGui.QTextOption.WrapAtWordBoundaryOrAnywhere)
        self.output.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarAlwaysOff)
        self.output.setPlaceholderText("Здесь появится ответ...")
        self.output.setHtml("""<div style='padding:28px; color:%s;'>
        <div style='font-size:24px; font-weight:700; margin-bottom:8px;'>Чем могу помочь?</div>
        <div style='font-size:14px; color:%s;'>Загрузите PDF слева и задайте вопрос по статье. Ответы будут связаны с конкретными страницами и цитатами.</div>
        </div>""" % (theme.html_colors()["text"], theme.html_colors()["hint"]))

        # слева: выбор модели (на кнопке — название модели)
        self.btn_model = QtWidgets.QPushButton(self.client.model)
        self.btn_model.setObjectName("ModelButton")
        self.btn_model.setToolTip("Модели")
        self.btn_model.setFixedHeight(BTN_SIZE)
        self.btn_model.setCursor(QtCore.Qt.PointingHandCursor)
        self.btn_model.setFocusPolicy(QtCore.Qt.NoFocus)
        self.btn_model.clicked.connect(self._show_models_menu)

        # справа: все кнопки одного размера
        self.btn_search_answer = IconButton(
            "search", "Поиск по ответу (Ctrl+F)")
        self.btn_search_answer.clicked.connect(self._toggle_answer_search)
        self.btn_copy = IconButton("copy", "Скопировать ответ")
        self.btn_copy.clicked.connect(self.copy_answer)
        self.btn_open_answer = IconButton("window", "Открыть окно ответа")
        self.btn_open_answer.clicked.connect(self.on_open_answer_window)
        self.btn_prev_answer = IconButton("prev", "Предыдущий ответ")
        self.btn_prev_answer.clicked.connect(self.prev_answer)
        self.answer_label = QtWidgets.QLabel("0/0")
        self.answer_label.setAlignment(QtCore.Qt.AlignCenter)
        self.answer_label.setFixedWidth(40)
        self.btn_next_answer = IconButton("next", "Следующий ответ")
        self.btn_next_answer.clicked.connect(self.next_answer)
        for b in (self.btn_copy, self.btn_open_answer,
                  self.btn_prev_answer, self.btn_next_answer):
            b.setEnabled(False)

        self.btn_research = IconButton("data", "Научные данные")
        self.btn_research.clicked.connect(self.open_research)
        self._research_dialog = None
        self.output.set_bottom_bar(make_bar(
            left=[self.btn_model],
            right=[self.btn_search_answer, self.btn_research, self.btn_copy,
                   self.btn_open_answer, self.btn_prev_answer,
                   self.answer_label, self.btn_next_answer]), BTN_SIZE)
        layout.addWidget(self.output, 1)

        # ====== Поле вопроса — внизу; «найти ответ» — лупа внутри поля ======
        self.input_question = BarTextEdit()
        self.input_question.setObjectName("QuestionBox")
        self.input_question.setPlaceholderText(
            "Спросите о данных в статье... Enter — отправить, "
            "Shift+Enter — новая строка. Можно перетащить PDF в окно.")
        self.input_question.setFixedHeight(110)
        self.input_question.installEventFilter(self)
        self.btn_ask = IconButton("search", "Найти ответ")
        self.btn_ask.setObjectName("AskButton")
        self.btn_ask.clicked.connect(self.ask_question)
        self.input_question.set_bottom_bar(
            make_bar(right=[self.btn_ask]), BTN_SIZE)
        layout.addWidget(self.input_question)

        self.splitter.addWidget(center)
        self.splitter.setSizes([380, 900])

        QtWidgets.QShortcut(
            QtGui.QKeySequence("Ctrl+O"), self).activated.connect(
                lambda: self.load_pdf())
        QtWidgets.QShortcut(
            QtGui.QKeySequence("Ctrl+F"), self).activated.connect(
                self._open_answer_search)
        QtWidgets.QShortcut(
            QtGui.QKeySequence("Ctrl+L"), self).activated.connect(
                lambda: self.input_question.setFocus())
        QtWidgets.QShortcut(
            QtGui.QKeySequence("Ctrl+Q"), self).activated.connect(self.close)

        # Перетаскивание PDF в окно
        self.setAcceptDrops(True)

        self.retheme()
        self._update_header_status()
        self._restore_session()
        self._center_on_screen()

    # ----------------------------------------------------------------
    # тема
    # ----------------------------------------------------------------
    def retheme(self):
        """Перекраска виджетов главного окна под текущую тему."""
        self.btn_research.retheme()
        self.docs_title.setStyleSheet(
            "QLabel { color:%s; font-size:17px; font-weight:800; }"
            % theme.TEXT_COLOR)
        self.docs_subtitle.setStyleSheet(theme.HINT_QSS)
        self.brand_label.setStyleSheet("QLabel { color:%s; font-size:16px; font-weight:800; letter-spacing:1px; }" % theme.TEXT_COLOR)
        self.subtitle_label.setStyleSheet("QLabel { color:%s; font-size:10px; }" % theme.TEXT_COLOR)
        self.header_meta.setStyleSheet("QLabel { color:%s; font-size:12px; }" % theme.TEXT_COLOR)
        self.header_status.setStyleSheet("QLabel#StatusPill { color:%s; background:rgba(88,214,163,0.10); border:1px solid rgba(88,214,163,0.30); border-radius:12px; padding:6px 12px; font-size:12px; font-weight:700; }" % ("#58d6a3" if theme.current_theme()=="dark" else "#218b69"))
        for w in (self.docs_list, self.docs_search, self.input_question,
                  self.output):
            w.setStyleSheet(theme.INPUT_QSS)
        for w in (self.btn_collapse_docs, self.btn_add_doc, self.btn_del_doc,
                  self.btn_load):
            w.setStyleSheet(theme.BUTTON_QSS)
        for w in (self.btn_search_answer, self.btn_copy, self.btn_open_answer,
                  self.btn_prev_answer, self.btn_next_answer,
                  self.btn_ask):
            w.retheme()
        self.btn_model.setStyleSheet(theme.ICON_BTN_QSS + "QPushButton { padding: 0px 13px; border-radius:10px; font-size:12px; font-weight:700; }")
        self.output.setStyleSheet(theme.INPUT_QSS + "QTextBrowser#AnswerSurface { border-radius:14px; border:1px solid %s; background:%s; padding:4px; }" % ("#2c3557" if theme.current_theme()=="dark" else "#d5dced", "#1d2541" if theme.current_theme()=="dark" else "#ffffff"))
        self.answer_search.retheme()
        self.answer_label.setStyleSheet(
            "QLabel { color:%s; font-size:12px; font-weight:700; background:%s; border:1px solid %s; border-radius:10px; padding:4px 7px; }"
            % (theme.TEXT_COLOR, "#252f50" if theme.current_theme()=="dark" else "#eef0fb", "#364263" if theme.current_theme()=="dark" else "#cbd2e4"))
        # перерисовать HTML-ответы под новую тему
        if 0 <= self.history_idx < len(self.history):
            self.render_answer()

    def _update_header_status(self, busy=False):
        count = len(self.docs)
        self.header_meta.setText("%d %s" % (count, "документ" if count == 1 else "документов"))
        if busy:
            self.header_status.setText("●  Анализирую…")
        elif count:
            self.header_status.setText("●  Готово к работе")
        else:
            self.header_status.setText("●  Добавьте PDF")

    # --------------------- сворачивание левой панели ---------------------
    def _toggle_docs_panel(self):
        if self.docs_body.isVisible():
            self._docs_saved = self.docs_panel.width()
            self.docs_body.setVisible(False)
            self.docs_title.setVisible(False)
            self.docs_panel.setFixedWidth(40)
            self.btn_collapse_docs.setText("›")
        else:
            self.docs_body.setVisible(True)
            self.docs_title.setVisible(True)
            self.docs_panel.setMinimumWidth(120)
            self.docs_panel.setMaximumWidth(16777215)
            total = max(1, self.splitter.width())
            w = getattr(self, "_docs_saved", 220)
            self.splitter.setSizes([w, max(1, total - w)])
            self.btn_collapse_docs.setText("‹")

    # ================================================================
    # модели / ключ API
    # ================================================================
    def _show_models_menu(self):
        menu = QtWidgets.QMenu(self)
        for key, cls in PROVIDERS.items():
            act = menu.addAction("%s  (%s)" % (cls.name, cls.default_model))
            act.setCheckable(True)
            act.setChecked(key == self.provider)
            act.triggered.connect(lambda _c, k=key: self._set_provider(k))
        menu.addSeparator()
        act_key = menu.addAction("Ввести / сменить ключ…")
        act_key.triggered.connect(self._change_key)
        # кнопка у нижнего края — меню раскрываем вверх
        pos = self.btn_model.mapToGlobal(
            QtCore.QPoint(0, -menu.sizeHint().height()))
        menu.exec_(pos)

    def _set_provider(self, provider):
        if provider == self.provider or provider not in PROVIDERS:
            return
        if self.client is not None:
            self.client.api_key = ""
            if hasattr(self.client, "client_id"):
                self.client.client_id = ""
            if hasattr(self.client, "_token"):
                self.client._token = None
                self.client._token_exp_ms = 0
        self.provider = provider
        SETTINGS.setValue("provider", provider)
        self.client = make_client(provider)
        self.btn_model.setText(self.client.model)

    def _change_key(self):
        if not self.client.ensure_key(self, force=True):
            self._update_header_status()  # или показать «ключ не изменён»

    # ================================================================
    # drag & drop
    # ================================================================
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith(".pdf"):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path and path.lower().endswith(".pdf"):
                self.load_pdf(path)

    # ----------------------------------------------------------------
    def _center_on_screen(self):
        scr = QtWidgets.QApplication.primaryScreen().availableGeometry()
        w = min(1280, int(scr.width() * 0.9))
        h = min(820, int(scr.height() * 0.9))
        self.resize(w, h)
        self.move(scr.center() - self.rect().center())


    # ================================================================
    # документы
    # ================================================================
    def load_pdf(self, path=None):
        if not path:
            path, _ = QtWidgets.QFileDialog.getOpenFileName(
                self, "Выберите PDF", "", "PDF (*.pdf)")
        if not path:
            return
        if path in self.docs:
            self._switch_doc(path)
            return
        try:
            doc = PDFDocument(path)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Ошибка PDF", str(e))
            return
        self.docs[path] = doc
        it = QtWidgets.QListWidgetItem(doc.name)
        it.setData(QtCore.Qt.UserRole, path)
        it.setToolTip(path)
        self.docs_list.addItem(it)
        self._switch_doc(path)
        self._update_header_status()
        self.output.setHtml(
            '<div style="color:%s;"><b>Загружено:</b> %s<br>'
            'Страниц: %d. Можно задавать вопросы.</div>'
            % (theme.html_colors()["text"], doc.name, len(doc)))

    def _switch_doc(self, path, update_list=True):
        if path not in self.docs:
            return
        self.current_path = path
        doc = self.docs[path]
        if update_list:
            self.docs_list.blockSignals(True)
            multi = len(self.docs_list.selectedItems()) > 1
            for i in range(self.docs_list.count()):
                it = self.docs_list.item(i)
                if it.data(QtCore.Qt.UserRole) != path:
                    continue
                if multi and it.isSelected():
                    # не сбрасываем выбор нескольких файлов
                    self.docs_list.setCurrentItem(
                        it, QtCore.QItemSelectionModel.NoUpdate)
                else:
                    self.docs_list.setCurrentItem(it)
                break
            self.docs_list.blockSignals(False)
            self._update_search_placeholder()
        self.setWindowTitle("%s — %s" % (APP_NAME, doc.name))
        if (self.viewer is not None and self.viewer.isVisible()
                and self.viewer.pdf_doc is not doc):
            self.viewer.close()
            self.viewer = None

    def _doc_selected(self, cur, _prev):
        if cur is not None:
            self._switch_doc(cur.data(QtCore.Qt.UserRole), update_list=False)

    def _doc_double_clicked(self, item):
        """Двойной клик по имени файла открывает окно PDF."""
        path = item.data(QtCore.Qt.UserRole)
        if path not in self.docs:
            return
        self._switch_doc(path, update_list=False)
        self.open_pdf_viewer(0)

    def remove_current_doc(self):
        items = self.docs_list.selectedItems()
        if not items and self.docs_list.currentItem() is not None:
            items = [self.docs_list.currentItem()]
        for item in items:
            path = item.data(QtCore.Qt.UserRole)
            if path == self.current_path:
                if self.viewer is not None:
                    self.viewer.close()
                    self.viewer = None
                self.current_path = None
                self.setWindowTitle(
                    "%s — AI-ассистент по научным статьям" % APP_NAME)
            self.docs_list.takeItem(self.docs_list.row(item))
            self.docs.pop(path, None)
        self._update_search_placeholder()
        self._update_header_status()

    def current_doc(self):
        return self.docs.get(self.current_path)

    # ---------------- поиск по файлам ----------------
    def _search_scope(self):
        """Выбрано несколько файлов — ищем в них, иначе — во всех."""
        sel = [it.data(QtCore.Qt.UserRole)
               for it in self.docs_list.selectedItems()]
        if len(sel) > 1:
            return [p for p in sel if p in self.docs]
        return list(self.docs.keys())

    def _update_search_placeholder(self):
        n = len(self.docs_list.selectedItems())
        if n > 1:
            self.docs_search.setPlaceholderText("Искать в выбранных (%d)..." % n)
        else:
            self.docs_search.setPlaceholderText("Поиск по документам...")

    def search_all_docs(self):
        q = self.docs_search.text().strip()
        if not q or not self.docs:
            return
        scope = self._search_scope()
        counts = {}
        for path in scope:
            try:
                n = len(self.docs[path].search_exact_ci(q))
            except Exception:
                n = 0
            if n:
                counts[path] = n
        if counts:
            best_path = max(counts, key=counts.get)
            self._switch_doc(best_path)
            self.open_pdf_viewer(0, search_query=q)
        else:
            where = ("ни в одном из выбранных документов"
                     if len(self.docs_list.selectedItems()) > 1
                     else "ни в одном документе")
            QtWidgets.QMessageBox.information(
                self, "Поиск", "«%s» не найдено %s." % (q, where))

    # ================================================================
    # PDF вьюер
    # ================================================================
    def open_pdf_viewer(self, page_no=0, focus_rect=None,
                        search_query=None, pulse_rect=None):
        doc = self.current_doc()
        if not doc:
            return
        if (self.viewer is not None and self.viewer.isVisible()
                and self.viewer.pdf_doc is doc):
            self.viewer.nav_go(page_no, focus_rect)
            if search_query:
                self.viewer.search_input.setText(search_query)
                self.viewer.run_search()
            if pulse_rect is not None:
                self.viewer.pulse(page_no, pulse_rect)
            self.viewer.raise_()
            self.viewer.activateWindow()
            return
        if self.viewer is not None:
            self.viewer.close()
        # Без родителя: окно независимое, при клике поднимается над другими
        self.viewer = PDFViewerWindow(doc, page_no, focus_rect,
                                      search_query, parent=None)
        if pulse_rect is not None:
            self.viewer.pulse(page_no, pulse_rect)
        self.viewer.show()
        self.viewer.raise_()
        self.viewer.activateWindow()

    # ================================================================
    # вопрос → ответ
    # ================================================================
    def eventFilter(self, obj, event):
        if (obj is self.input_question
                and event.type() == QtCore.QEvent.KeyPress):
            if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
                if event.modifiers() & QtCore.Qt.ShiftModifier:
                    return False
                self.ask_question()
                return True
        return super().eventFilter(obj, event)

    def open_research(self):
        if self._research_dialog is None:
            self._research_dialog = ResearchDialog(self.docs, self)
        self._research_dialog.show()
        self._research_dialog.raise_()
        self._research_dialog.activateWindow()

    def ask_question(self):
        question = self.input_question.toPlainText().strip()
        if not question:
            return
        doc = self.current_doc()
        if not doc:
            QtWidgets.QMessageBox.information(
                self, "PDF", "Сначала загрузите PDF!")
            return
        # Ключ (для GigaChat — ключ и ID клиента) спрашиваем только здесь,
        # при первом «умном» поиске.
        if not self.client.ensure_key(self):
            return
        self.input_question.clear()
        self._update_header_status(busy=True)
        self.btn_ask.setEnabled(False)
        old_placeholder = self.input_question.placeholderText()
        self.input_question.setPlaceholderText("%s думает..." % self.client.name)
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        QtWidgets.QApplication.processEvents()
        try:
            ctx = self.client.rank_pages(
                doc.pages_text, question, top_n=12)
            self.client.last_context_pages = ctx
            prompt = build_prompt(doc.pages_text, ctx, question,
                                  doc_name=doc.name)
            raw = self.client.ask(prompt, parent=self)
            entry = parse_answer(raw)
            entry["doc"] = doc.name
            entry["path"] = self.current_path
            entry["question"] = question
            entry["context_pages"] = [doc.to_article_page(i) for i in ctx]
            # Резолвим якоря в rect-ы сразу
            for a in entry.get("anchors", []):
                try:
                    rect = doc.resolve_anchor(a["page"], a["quote"])
                except Exception:
                    rect = None
                a["rect"] = None
                if rect is not None:
                    a["rect"] = [rect.x0, rect.y0, rect.x1, rect.y1]
            self.history.append(entry)
            self.history_idx = len(self.history) - 1
            self.render_answer()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Ошибка API", str(e))
        finally:
            self.btn_ask.setEnabled(True)
            self.input_question.setPlaceholderText(old_placeholder)
            QtWidgets.QApplication.restoreOverrideCursor()
            self._update_header_status()

    # ================================================================
    # история ответов
    # ================================================================
    def _set_answer_buttons(self):
        has = 0 <= self.history_idx < len(self.history)
        self.btn_open_answer.setEnabled(has)
        self.btn_copy.setEnabled(has)
        self.btn_prev_answer.setEnabled(has and self.history_idx > 0)
        self.btn_next_answer.setEnabled(
            has and self.history_idx < len(self.history) - 1)
        self.answer_label.setText(
            "%d/%d" % (self.history_idx + 1, len(self.history))
            if has else "0/0")

    def render_answer(self):
        if not (0 <= self.history_idx < len(self.history)):
            self.output.clear()
            self._set_answer_buttons()
            return
        entry = self.history[self.history_idx]
        self.output.setHtml(render_answer_html(
            entry["text"], entry["formulas"], entry["anchors"],
            doc_name=entry.get("doc")))
        self._set_answer_buttons()
        self.output.verticalScrollBar().setValue(0)
        self._matches = []
        self._match_idx = -1
        self.answer_search.set_counter(0, 0)
        if self.answer_search.isVisible() and self.answer_search.text().strip():
            self._on_answer_search_changed(self.answer_search.text())
        if self.answer_window is not None and self.answer_window.isVisible():
            self.answer_window.set_entry(entry)

    def prev_answer(self):
        if self.history_idx > 0:
            self.history_idx -= 1
            self.render_answer()

    def next_answer(self):
        if self.history_idx < len(self.history) - 1:
            self.history_idx += 1
            self.render_answer()

    @staticmethod
    def _answer_plain_text(entry):
        """Текст ответа для буфера обмена: формулы — в виде LaTeX."""
        text = entry.get("text", "") or ""
        formulas = entry.get("formulas", []) or []

        def repl(m):
            idx = int(m.group(1))
            return formulas[idx]["latex"] if idx < len(formulas) else ""
        return PLACEHOLDER_RE.sub(repl, text)

    def copy_answer(self):
        if not (0 <= self.history_idx < len(self.history)):
            return
        QtWidgets.QApplication.clipboard().setText(
            self._answer_plain_text(self.history[self.history_idx]))

    def on_open_answer_window(self):
        if not (0 <= self.history_idx < len(self.history)):
            return
        if self.answer_window is None or not self.answer_window.isVisible():
            # Без родителя: независимое окно, поднимается кликом
            self.answer_window = AnswerWindow(parent=None)
            self.answer_window.link_clicked.connect(self.on_link_clicked)
            self.answer_window.set_entry(self.history[self.history_idx])
            self.answer_window.show()
        else:
            self.answer_window.set_entry(self.history[self.history_idx])
        self.answer_window.raise_()
        self.answer_window.activateWindow()

    def _show_export_menu(self):
        menu = QtWidgets.QMenu(self)
        act_load_ans = menu.addAction("Загрузить ответы (JSON)...")
        act_load_ans.triggered.connect(self._import_answers_json)
        act_ans = menu.addAction("Ответы (JSON)...")
        act_ans.triggered.connect(self._export_answers_json)
        act_tz = menu.addAction("Данные по ТЗ (JSON)...")
        act_tz.triggered.connect(self._export_tz)
        pos = self.btn_export.mapToGlobal(
            QtCore.QPoint(self.btn_export.width() - menu.sizeHint().width(),
                          -menu.sizeHint().height()))
        menu.exec_(pos)

    # ================================================================
    # ссылки
    # ================================================================
    def on_link_clicked(self, url):
        s = url.toString()
        doc = self.current_doc()
        if not doc:
            return
        if s.startswith("page:"):
            try:
                pno = doc.to_pdf_index(int(s.split(":", 1)[1]))
            except ValueError:
                return
            if pno is not None:
                doc.clear_ai_highlight()
                # подсвечиваем на открываемой странице ВСЕ вхождения
                # запроса поиска по PDF (если поиск в окне просмотра активен)
                q = ""
                if (self.viewer is not None and self.viewer.isVisible()
                        and self.viewer.pdf_doc is doc):
                    q = self.viewer.search_input.text().strip()
                if q:
                    rects = doc.find_all_on_page(
                        pno, q, self.viewer.search_mode.currentData(),
                        self.viewer.case_check.isChecked())
                    if rects:
                        doc.set_ai_highlights([(pno, r) for r in rects])
                self.open_pdf_viewer(pno,
                                     pulse_rect=doc.get_ai_highlight()
                                     and doc.get_ai_highlight()[1])
            return
        if s.startswith("anchor:"):
            if not (0 <= self.history_idx < len(self.history)):
                return
            entry = self.history[self.history_idx]
            try:
                ai = int(s.split(":", 1)[1])
                a = entry["anchors"][ai]
            except (ValueError, IndexError):
                return
            pno = doc.to_pdf_index(a["page"])
            if pno is None:
                return
            # Берём сохранённый rect, иначе резолвим заново
            rect = None
            if a.get("rect"):
                rect = fitz.Rect(*a["rect"])
            else:
                rect = doc.resolve_anchor(a["page"], a["quote"])
            # Подсвечиваем ВСЕ вхождения цитаты якоря на странице
            rects = []
            if a.get("quote"):
                rects = doc.find_all_on_page(pno, a["quote"])
                if not rects:
                    rects = doc.find_all_on_page(
                        pno, " ".join(a["quote"].split()[:3]))
            if rect is not None and not rects:
                rects = [rect]
            if rects:
                doc.set_ai_highlights([(pno, r) for r in rects])
            self.open_pdf_viewer(pno, focus_rect=rects[0] if rects else None,
                                 pulse_rect=rects[0] if rects else None)
            return
        if s.startswith("formula:"):
            if not (0 <= self.history_idx < len(self.history)):
                return
            entry = self.history[self.history_idx]
            try:
                fi = int(s.split(":", 1)[1])
                f = entry["formulas"][fi]
            except (ValueError, IndexError):
                return
            if f.get("page") is None:
                return
            pno = doc.to_pdf_index(f["page"])
            if pno is None:
                return
            anchor_rect = None
            page_anchors = [
                a for a in entry.get("anchors", [])
                if a.get("page") == f["page"]
            ]
            if page_anchors:
                anchor_rect = doc.resolve_anchor(
                    page_anchors[0]["page"], page_anchors[0]["quote"])
            else:
                for a in entry.get("anchors", []):
                    anchor_rect = doc.resolve_anchor(a["page"], a["quote"])
                    if anchor_rect is not None:
                        break

            rect = doc.find_formula_rect(pno, anchor_rect)
            items = []
            if rect is not None:
                items.append((pno, rect))
            elif anchor_rect is not None:
                items.append((pno, anchor_rect))
            if anchor_rect is not None:
                for r in doc.find_all_on_page(pno, page_anchors[0]["quote"]
                                              if page_anchors else ""):
                    items.append((pno, r))
            if items:
                doc.set_ai_highlights(items)
                self.open_pdf_viewer(pno, focus_rect=items[0][1],
                                     pulse_rect=items[0][1])


    # ================================================================
    # поиск в ответе
    # ================================================================
    def _open_answer_search(self):
        self.answer_search.show()
        self.answer_search.setFocus()
        self.answer_search.selectAll()

    def _toggle_answer_search(self):
        if self.answer_search.isVisible():
            self.answer_search.hide()
            self._clear_browser_highlights(self.output)
            self._matches = []
            self._match_idx = -1
            self.answer_search.set_counter(0, 0)
        else:
            self._open_answer_search()

    def _set_match_ui(self):
        total = len(self._matches)
        self.answer_search.set_counter(
            self._match_idx + 1 if total else 0, total)

    def _on_answer_search_changed(self, text):
        q = text.strip()
        if not q:
            self._clear_browser_highlights(self.output)
            self._matches = []
            self._match_idx = -1
            self._set_match_ui()
            return
        self._matches = self._find_all(self.output.toPlainText(), q)
        if not self._matches:
            self._match_idx = -1
            self._set_match_ui()
            self._clear_browser_highlights(self.output)
            return
        self._match_idx = 0
        self._highlight_and_center(
            self.output, self._matches, self._match_idx)
        self._set_match_ui()

    def search_answer_main(self):
        q = self.answer_search.text().strip()
        if not q:
            self._on_answer_search_changed("")
            return
        self._on_answer_search_changed(q)
        if not self._matches:
            QtWidgets.QMessageBox.information(
                self, "Поиск", "«%s» не найдено." % q)

    def prev_match_main(self):
        if not self._matches:
            return
        self._match_idx = (self._match_idx - 1) % len(self._matches)
        self._highlight_and_center(
            self.output, self._matches, self._match_idx)
        self._set_match_ui()

    def next_match_main(self):
        if not self._matches:
            return
        self._match_idx = (self._match_idx + 1) % len(self._matches)
        self._highlight_and_center(
            self.output, self._matches, self._match_idx)
        self._set_match_ui()

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
    def _clear_browser_highlights(browser):
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


    # ================================================================
    # экспорт
    # ================================================================
    def _import_answers_json(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Загрузить ответы", "", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
            if not isinstance(payload, dict) or not isinstance(payload.get("answers"), list):
                raise ValueError("Файл должен содержать массив answers")
            answers = []
            for entry in payload["answers"]:
                if not isinstance(entry, dict):
                    raise ValueError("Каждый ответ должен быть объектом JSON")
                # Keep the exported answer shape; absent optional fields are safe defaults.
                item = dict(entry)
                item.setdefault("text", "")
                item.setdefault("formulas", [])
                item.setdefault("anchors", [])
                answers.append(item)
            self.history = answers
            self.history_idx = len(answers) - 1
            bookmarks = payload.get("bookmarks")
            if isinstance(bookmarks, dict):
                for doc_path, raw in bookmarks.items():
                    if doc_path in self.docs and isinstance(raw, list):
                        self.docs[doc_path].bookmarks = raw
            self.render_answer()
            QtWidgets.QMessageBox.information(
                self, "Загрузка", "Загружено ответов: %d" % len(answers))
        except (OSError, ValueError, TypeError, UnicodeError, json.JSONDecodeError) as exc:
            QtWidgets.QMessageBox.critical(self, "Загрузка ответов", str(exc))

    def _export_answers_json(self):
        if not self.history:
            QtWidgets.QMessageBox.information(
                self, "Экспорт", "Пока нет ответов для экспорта.")
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Экспорт ответов", "answers.json", "JSON (*.json)")
        if not path:
            return
        try:
            export_json(path, self.current_path or "",
                        self.history,
                        {p: d.bookmarks for p, d in self.docs.items()})
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Экспорт", str(e))

    def _export_tz(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Экспорт данных по ТЗ", "cyberdoc_dataset.json",
            "JSON (*.json)")
        if not path:
            return
        try:
            export_tz_json(path, APP_NAME, "1.0", self.client,
                           self.provider, self.docs, self.history)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Экспорт", str(e))

    # ================================================================
    # сессия
    # ================================================================
    def _restore_session(self):
        geo = SETTINGS.value("geometry")
        if geo:
            self.restoreGeometry(geo)
        paths = SETTINGS.value("open_docs", []) or []
        if not isinstance(paths, (list, tuple)):
            paths = [paths]
        for p in paths:
            if p and os.path.exists(p):
                self.load_pdf(p)
        bm_data = SETTINGS.value("bookmarks", {}) or {}
        if not isinstance(bm_data, dict):
            bm_data = {}
        for path, raw in bm_data.items():
            if path in self.docs:
                try:
                    self.docs[path].bookmarks = json.loads(raw)
                except Exception:
                    pass

    def closeEvent(self, event):
        # Credentials are session-only and are cleared before process exit.
        self.client.api_key = ""
        if hasattr(self.client, "client_id"):
            self.client.client_id = ""
        if hasattr(self.client, "_token"):
            self.client._token = None
        SETTINGS.setValue("geometry", self.saveGeometry())
        SETTINGS.setValue("open_docs", list(self.docs.keys()))
        SETTINGS.setValue("bookmarks", {
            p: json.dumps(d.bookmarks, ensure_ascii=False)
            for p, d in self.docs.items()})
        if self.viewer is not None:
            self.viewer.close()
        if self.answer_window is not None:
            self.answer_window.close()
        super().closeEvent(event)

