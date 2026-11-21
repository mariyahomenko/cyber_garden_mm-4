"""Мелкие виджеты и иконки (рисуются кодом, внешних файлов не нужно).

* IconButton        — квадратная кнопка с иконкой и подсказкой;
* SearchLineEdit    — поле поиска со счётчиком и стрелками ↑↓ внутри поля;
* InlineIconButton  — неяркая кнопка-иконка для встраивания ВНУТРЬ поля;
* BarTextEdit /
  BarTextBrowser    — текстовые поля с «полосой» кнопок внутри, у нижнего
                      края. Под полосу резервируется место (отступ области
                      просмотра), поэтому текст никогда не заезжает на кнопки.
"""

from PyQt5 import QtWidgets, QtCore, QtGui

from .. import theme

ICON_PX = 19
BTN_SIZE = 38          # единый размер кнопок внутри полей


# ======================================================================
# иконки
# ======================================================================
def _make_icon(draw, color="#ffffff", size=ICON_PX):
    dpr = 2
    pm = QtGui.QPixmap(size * dpr, size * dpr)
    pm.setDevicePixelRatio(dpr)
    pm.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    p.setPen(QtGui.QPen(QtGui.QColor(color), 1.8, QtCore.Qt.SolidLine,
                        QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin))
    p.setBrush(QtCore.Qt.NoBrush)
    draw(p, size)
    p.end()
    return QtGui.QIcon(pm)


def _pt(x, y):
    return QtCore.QPointF(x, y)


def _draw_search(p, s):
    p.drawEllipse(_pt(6.5, 6.5), 4.6, 4.6)
    p.drawLine(_pt(10.0, 10.0), _pt(14.2, 14.2))


def _draw_copy(p, s):
    p.drawRoundedRect(QtCore.QRectF(5.5, 5.5, 8, 8.5), 1.5, 1.5)
    p.drawPolyline(QtGui.QPolygonF(
        [_pt(3.5, 10.5), _pt(2.5, 10.5), _pt(2.5, 2.5),
         _pt(9.5, 2.5), _pt(9.5, 3.5)]))


def _draw_window(p, s):
    p.drawRoundedRect(QtCore.QRectF(2, 3, 12, 10), 1.5, 1.5)
    p.drawLine(_pt(2, 6.2), _pt(14, 6.2))


def _draw_prev(p, s):
    p.drawPolyline(QtGui.QPolygonF(
        [_pt(9.8, 3.5), _pt(5.2, 8), _pt(9.8, 12.5)]))


def _draw_next(p, s):
    p.drawPolyline(QtGui.QPolygonF(
        [_pt(6.2, 3.5), _pt(10.8, 8), _pt(6.2, 12.5)]))


def _draw_up(p, s):
    p.drawPolyline(QtGui.QPolygonF(
        [_pt(3.5, 10.2), _pt(8, 5.6), _pt(12.5, 10.2)]))


def _draw_down(p, s):
    p.drawPolyline(QtGui.QPolygonF(
        [_pt(3.5, 5.8), _pt(8, 10.4), _pt(12.5, 5.8)]))


def _draw_marker(p, s):
    p.drawPolyline(QtGui.QPolygonF([_pt(3, 11), _pt(10.5, 3.5), _pt(13, 6), _pt(5.5, 13.5)]))
    p.drawLine(_pt(2, 14), _pt(9, 14))

def _draw_bookmark(p, s):
    p.drawPolyline(QtGui.QPolygonF([_pt(4, 2), _pt(12, 2), _pt(12, 14), _pt(8, 11), _pt(4, 14), _pt(4, 2)]))

def _draw_close(p, s):
    p.drawLine(_pt(4, 4), _pt(12, 12))
    p.drawLine(_pt(12, 4), _pt(4, 12))

def _draw_data(p, s):
    p.drawRect(QtCore.QRectF(2, 3, 12, 10))
    p.drawLine(_pt(2, 7), _pt(14, 7))
    p.drawLine(_pt(7, 3), _pt(7, 13))

def _draw_export(p, s):
    p.drawLine(_pt(8, 2.5), _pt(8, 10.2))
    p.drawPolyline(QtGui.QPolygonF(
        [_pt(4.9, 7.2), _pt(8, 10.4), _pt(11.1, 7.2)]))
    p.drawPolyline(QtGui.QPolygonF(
        [_pt(3, 11), _pt(3, 13.5), _pt(13, 13.5), _pt(13, 11)]))


def _draw_menu(p, s):
    """Три точки — меню настроек. Компактнее и ровнее, чем глиф «▼»."""
    for y in (4.5, 8.0, 11.5):
        p.drawPoint(_pt(8, y))
    # точки крупнее: рисуем кружки
    p.setBrush(QtGui.QBrush(p.pen().color()))
    for y in (4.5, 8.0, 11.5):
        p.drawEllipse(_pt(8, y), 1.2, 1.2)
    p.setBrush(QtCore.Qt.NoBrush)


_DRAWERS = {
    "search": _draw_search, "copy": _draw_copy, "window": _draw_window,
    "prev": _draw_prev, "next": _draw_next, "up": _draw_up,
    "down": _draw_down, "export": _draw_export, "marker": _draw_marker,
    "bookmark": _draw_bookmark, "close": _draw_close, "data": _draw_data,
    "menu": _draw_menu,
}
_ICON_CACHE = {}


def icon(name, color="#ffffff"):
    key = (name, color)
    if key not in _ICON_CACHE:
        _ICON_CACHE[key] = _make_icon(_DRAWERS[name], color)
    return _ICON_CACHE[key]


# ======================================================================
# кнопка
# ======================================================================
class IconButton(QtWidgets.QPushButton):
    """Квадратная кнопка с иконкой; текста нет, пояснение — в подсказке."""

    def __init__(self, icon_name, tooltip, parent=None, size=BTN_SIZE):
        super().__init__(parent)
        self.setIcon(icon(icon_name))
        self.setIconSize(QtCore.QSize(ICON_PX, ICON_PX))
        self.setToolTip(tooltip)
        self.setFixedSize(size, size)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        self.retheme()

    def retheme(self):
        self.setStyleSheet(theme.ICON_BTN_QSS)


class InlineIconButton(IconButton):
    """Неяркая кнопка-иконка для встраивания ВНУТРЬ поля ввода.

    Прозрачный фон, без рамки, приглушённый цвет иконки. При наведении
    подсветка мягче, чем у обычных кнопок. Используется как «стрелка»
    справа внутри QLineEdit.
    """

    def __init__(self, icon_name, tooltip, parent=None, size=26):
        # Сохраняем имя иконки ДО super().__init__, иначе retheme()
        # (вызываемый из IconButton.__init__) его не найдёт.
        self._icon_name = icon_name
        super().__init__(icon_name, tooltip, parent, size=size)
        self.setIconSize(QtCore.QSize(14, 14))
        self.retheme()

    def retheme(self):
        name = getattr(self, "_icon_name", None)
        if name is None:
            # Пока атрибут не задан — просто не трогаем иконку.
            return
        dim = theme.html_colors()["hint"]
        self.setIcon(icon(name, dim))
        self.setStyleSheet(
            "QPushButton { background:transparent; border:none;"
            " border-radius:6px; padding:0px; }"
            "QPushButton:hover { background:rgba(127,127,127,0.18); }"
            "QPushButton:pressed { background:rgba(127,127,127,0.28); }"
            "QPushButton::menu-indicator { image:none; width:0px; }")
        

# ======================================================================
# поле поиска со стрелками внутри
# ======================================================================
class SearchLineEdit(QtWidgets.QLineEdit):
    prev_requested = QtCore.pyqtSignal()
    next_requested = QtCore.pyqtSignal()

    _BTN = 24
    _COUNT_W = 44
    _GAP = 3

    def __init__(self, placeholder="", parent=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.count_label = QtWidgets.QLabel("0/0", self)
        self.count_label.setAlignment(QtCore.Qt.AlignCenter)
        self.count_label.setFixedWidth(self._COUNT_W)
        self.btn_prev = IconButton("up", "Предыдущее совпадение (Shift+F3)",
                                   self, size=self._BTN)
        self.btn_next = IconButton("down", "Следующее совпадение (F3)",
                                   self, size=self._BTN)
        self.btn_prev.clicked.connect(self.prev_requested)
        self.btn_next.clicked.connect(self.next_requested)
        self.btn_prev.setEnabled(False)
        self.btn_next.setEnabled(False)
        # место под счётчик и стрелки: текст под них не заезжает
        reserve = self._COUNT_W + 2 * self._BTN + 4 * self._GAP
        self.setTextMargins(0, 0, reserve, 0)
        self.retheme()

    def set_counter(self, idx, total):
        """idx — номер текущего совпадения (1..total) или 0."""
        self.count_label.setText("%d/%d" % (idx, total))
        self.btn_prev.setEnabled(total > 1)
        self.btn_next.setEnabled(total > 1)

    def retheme(self):
        self.setStyleSheet(theme.INPUT_QSS)
        self.count_label.setStyleSheet(
            "QLabel { color:%s; font-size:12px; background:transparent; }"
            % theme.TEXT_COLOR)
        self.btn_prev.retheme()
        self.btn_next.retheme()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        h = self.height()
        y = (h - self._BTN) // 2
        x = self.width() - self._GAP - 2
        x -= self._BTN
        self.btn_next.move(x, y)
        x -= self._GAP + self._BTN
        self.btn_prev.move(x, y)
        x -= self._GAP + self._COUNT_W
        self.count_label.move(x, (h - self.count_label.height()) // 2)


# ======================================================================
# поля с полосой кнопок внутри (у нижнего края)
# ======================================================================
class _BottomBarMixin:
    """Резервирует у нижнего края поля полосу под кнопки.

    Полоса лежит ВНУТРИ рамки поля, под областью текста: отступ области
    просмотра (viewport margins) гарантирует, что текст не окажется ни над,
    ни под кнопками.
    """

    _BAR_GAP = 4
    _bar = None
    _bar_h = 0

    def _bar_init(self):
        self._bar = None
        self._bar_h = 0

    def set_bottom_bar(self, widget, height):
        self._bar = widget
        self._bar_h = height
        widget.setParent(self)
        self.setViewportMargins(0, 0, 0, height + 2 * self._BAR_GAP)
        self.viewport().installEventFilter(self)
        widget.show()
        self._place_bar()
        QtCore.QTimer.singleShot(0, self._place_bar)

    def _place_bar(self):
        if self._bar is None:
            return
        vp = self.viewport().geometry()
        self._bar.setGeometry(vp.left(), vp.bottom() + 1 + self._BAR_GAP,
                              vp.width(), self._bar_h)
        self._bar.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._place_bar()

    def eventFilter(self, obj, event):
        if (self._bar is not None and obj is self.viewport()
                and event.type() == QtCore.QEvent.Resize):
            self._place_bar()
        return super().eventFilter(obj, event)


class BarTextEdit(_BottomBarMixin, QtWidgets.QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._bar_init()

    def keyPressEvent(self, event):
        if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            if not (event.modifiers() & QtCore.Qt.ShiftModifier):
                event.ignore()
                return
        super().keyPressEvent(event)


class BarTextBrowser(_BottomBarMixin, QtWidgets.QTextBrowser):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._bar_init()


def make_bar(*, left=(), right=(), height=BTN_SIZE):
    """Горизонтальная полоса: left-виджеты слева, right-виджеты справа."""
    bar = QtWidgets.QWidget()
    bar.setObjectName("CdBar")
    bar.setStyleSheet("QWidget#CdBar { background: transparent; }")
    lay = QtWidgets.QHBoxLayout(bar)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(4)
    for w in left:
        lay.addWidget(w)
    lay.addStretch(1)
    for w in right:
        lay.addWidget(w)
    bar.setFixedHeight(height)
    return bar
