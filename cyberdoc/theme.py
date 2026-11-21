"""CyberDoc visual theme: deep indigo surfaces with violet/blue accents."""
from PyQt5 import QtWidgets

THEMES = ("dark", "light")
_PALETTES = {
    "dark": {
        "window1":"#0f1222", "window2":"#151a31", "window3":"#0b0e1c",
        "card":"#181e36", "card_border":"#2c3557", "surface":"#1d2541",
        "surface_raised":"#252f50", "input_bg":"#202844", "input_bg_focus":"#263052",
        "text":"#f1f3ff", "text_dim":"#98a1c3", "border":"#364263",
        "scroll_bg":"#151b31", "scroll_handle":"#4b5b89", "header":"#252f50",
        "view_bg":"#101528", "accent":"#9a7bff", "accent2":"#6548d9",
        "accent3":"#55b6ff", "success":"#58d6a3", "warm":"#ffd166",
        "dialog_bg":"#202844", "dialog_text":"#f1f3ff",
    },
    "light": {
        "window1":"#edf0fa", "window2":"#f7f8fd", "window3":"#e5e9f5",
        "card":"#ffffff", "card_border":"#d5dced", "surface":"#f6f7fc",
        "surface_raised":"#eef0fb", "input_bg":"#ffffff", "input_bg_focus":"#f4f2ff",
        "text":"#232743", "text_dim":"#68708e", "border":"#cbd2e4",
        "scroll_bg":"#e6eaf5", "scroll_handle":"#aab5d3", "header":"#e9ecf8",
        "view_bg":"#dfe4f0", "accent":"#8063ed", "accent2":"#5d43ce",
        "accent3":"#258bd1", "success":"#218b69", "warm":"#c78900",
        "dialog_bg":"#ffffff", "dialog_text":"#232743",
    },
}
CURRENT = "dark"

def current_theme(): return CURRENT

def set_theme(name):
    global CURRENT, INPUT_QSS, BUTTON_QSS, LABEL_QSS, HINT_QSS
    global MAIN_QSS, TABLE_QSS, SCROLL_QSS, MENU_QSS, DIALOG_QSS
    global ICON_BTN_QSS, CHECK_QSS, VIEW_BG, ACCENT, TEXT_COLOR
    name = (name or "dark").lower()
    if name not in _PALETTES: name = "dark"
    CURRENT = name; p = _PALETTES[name]
    MAIN_QSS = """
QMainWindow { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 %(window1)s,stop:0.55 %(window2)s,stop:1 %(window3)s); }
QWidget#Card { background-color:%(card)s; border:1px solid %(card_border)s; border-radius:18px; }
QWidget#Header { background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 %(surface_raised)s,stop:1 %(surface)s); border:1px solid %(card_border)s; border-radius:16px; }
QWidget#Panel { background-color:%(surface)s; border:1px solid %(card_border)s; border-radius:14px; }
QLabel#Brand { color:%(text)s; font-size:20px; font-weight:800; letter-spacing:1px; }
QLabel#Subtitle { color:%(text_dim)s; font-size:12px; }
QLabel#StatusPill { color:%(success)s; background-color:rgba(88,214,163,0.10); border:1px solid rgba(88,214,163,0.30); border-radius:12px; padding:6px 12px; font-size:12px; font-weight:700; }
QStatusBar { background-color:%(window1)s; color:%(text_dim)s; border-top:1px solid %(card_border)s; }
QToolTip { background-color:%(dialog_bg)s; color:%(dialog_text)s; border:1px solid %(border)s; padding:7px 10px; border-radius:7px; }
QSplitter::handle { background:%(card_border)s; }
QSplitter::handle:hover { background:%(accent)s; }
""" % p
    INPUT_QSS = """
QLineEdit, QTextEdit, QTextBrowser, QSpinBox, QComboBox { background-color:%(input_bg)s; color:%(text)s; border:1px solid %(border)s; border-radius:10px; padding:9px 12px; font-size:14px; selection-background-color:%(accent)s; selection-color:white; }
QLineEdit:hover, QTextEdit:hover, QTextBrowser:hover { border-color:%(accent)s; }
QLineEdit:focus, QTextEdit:focus, QTextBrowser:focus { border:1px solid %(accent)s; background-color:%(input_bg_focus)s; }
QTextBrowser { background-color:%(input_bg)s; }
QTextEdit#QuestionBox { min-height:90px; border:1px solid %(border)s; }
QTextEdit#QuestionBox:focus { border:1px solid %(accent)s; background-color:%(input_bg_focus)s; }
QSpinBox { color:%(text)s; }
QSpinBox::up-button, QSpinBox::down-button { background-color:%(border)s; border:none; width:17px; }
QComboBox QAbstractItemView { background-color:%(input_bg)s; color:%(text)s; selection-background-color:%(accent2)s; border:1px solid %(border)s; }
""" % p
    BUTTON_QSS = """
QPushButton { background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 %(accent)s,stop:1 %(accent2)s); color:white; border:none; border-radius:10px; padding:10px 16px; font-size:14px; font-weight:700; }
QPushButton:hover { background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #ae97ff,stop:1 %(accent)s); }
QPushButton:pressed { background:%(accent2)s; padding-top:11px; }
QPushButton:disabled { background:%(scroll_handle)s; color:%(text_dim)s; }
QPushButton:checked { background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 %(warm)s,stop:1 #e5a91b); color:#14142b; }
""" % p
    LABEL_QSS = "QLabel { color:%(text)s; font-size:14px; }" % p
    HINT_QSS = "QLabel { color:%(text_dim)s; font-size:12px; }" % p
    TABLE_QSS = """
QTableWidget { background-color:%(input_bg)s; color:%(text)s; alternate-background-color:%(surface)s; gridline-color:%(card_border)s; border:1px solid %(border)s; border-radius:10px; font-size:13px; }
QHeaderView::section { background-color:%(header)s; color:%(text)s; border:none; padding:8px; font-weight:700; }
QTableWidget::item:selected { background-color:%(accent2)s; }
QListWidget, QTreeWidget { background-color:%(input_bg)s; color:%(text)s; border:1px solid %(border)s; border-radius:10px; font-size:13px; padding:5px; }
QListWidget::item, QTreeWidget::item { padding:9px 10px; border-radius:7px; margin:2px 0; }
QListWidget::item:hover, QTreeWidget::item:hover { background-color:%(surface_raised)s; }
QListWidget::item:selected, QTreeWidget::item:selected { background-color:%(accent2)s; color:white; }
QTabWidget::pane { border:1px solid %(border)s; border-radius:10px; background:%(surface)s; }
QTabBar::tab { background:%(input_bg)s; color:%(text_dim)s; padding:9px 16px; border-top-left-radius:8px; border-top-right-radius:8px; margin-right:3px; }
QTabBar::tab:selected { background:%(accent2)s; color:white; }
QTabBar::tab:hover:!selected { background:%(surface_raised)s; color:%(text)s; }
""" % p
    SCROLL_QSS = """
QScrollBar:vertical { background:%(scroll_bg)s; width:12px; border-radius:6px; margin:2px; }
QScrollBar::handle:vertical { background:%(scroll_handle)s; border-radius:6px; min-height:34px; }
QScrollBar::handle:vertical:hover { background:%(accent2)s; }
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical { height:0; }
QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical { background:transparent; }
QScrollBar:horizontal { background:%(scroll_bg)s; height:12px; border-radius:6px; margin:2px; }
QScrollBar::handle:horizontal { background:%(scroll_handle)s; border-radius:6px; min-width:34px; }
QScrollBar::handle:horizontal:hover { background:%(accent2)s; }
QScrollBar::add-line:horizontal,QScrollBar::sub-line:horizontal { width:0; }
QMenuBar { background-color:%(window1)s; color:%(text)s; }
QMenuBar::item:selected { background-color:%(accent2)s; color:white; }
""" % p
    MENU_QSS = "QMenu { background-color:%(dialog_bg)s; color:%(dialog_text)s; border:1px solid %(border)s; border-radius:8px; padding:5px; } QMenu::item { padding:8px 26px; border-radius:5px; } QMenu::item:selected { background-color:%(accent2)s; color:white; }""" % p
    DIALOG_QSS = """
QMessageBox,QInputDialog,QDialog,QFileDialog { background-color:%(dialog_bg)s; }
QMessageBox QLabel,QInputDialog QLabel,QDialog QLabel { color:%(dialog_text)s; font-size:13px; }
QDialog QGroupBox { color:%(dialog_text)s; border:1px solid %(border)s; border-radius:9px; margin-top:12px; padding:10px; }
QDialog QGroupBox::title { subcontrol-origin:margin; left:10px; padding:0 5px; }
QDialog QCheckBox,QDialog QRadioButton { color:%(dialog_text)s; }
""" % p
    ICON_BTN_QSS = """
QPushButton { background:%(surface_raised)s; color:%(text)s; border:1px solid %(border)s; border-radius:10px; padding:0px; }
QPushButton:hover { background:%(accent2)s; border-color:%(accent)s; color:white; }
QPushButton:pressed { background:%(accent2)s; }
QPushButton:disabled { background:%(input_bg)s; border-color:%(border)s; color:%(text_dim)s; }
QPushButton:checked { background:%(warm)s; color:#14142b; border-color:%(warm)s; }
QPushButton#AskButton { background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 %(accent)s,stop:1 %(accent2)s); border:none; color:white; }
QPushButton#AskButton:hover { background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #b29cff,stop:1 %(accent)s); }
QPushButton#AskButton:disabled { background:%(scroll_handle)s; }
""" % p
    CHECK_QSS = """
QCheckBox { color:%(text)s; font-size:14px; spacing:7px; }
QCheckBox::indicator { width:16px; height:16px; background:%(input_bg)s; border:1px solid %(border)s; border-radius:4px; }
QCheckBox::indicator:hover { border-color:%(accent)s; }
QCheckBox::indicator:checked { background:%(accent2)s; border-color:%(accent)s; }
""" % p
    VIEW_BG, ACCENT, TEXT_COLOR = p["view_bg"], p["accent2"], p["text"]

def app_stylesheet(theme=None):
    name=(theme or CURRENT).lower(); saved=CURRENT; set_theme(name)
    sheet=MAIN_QSS+INPUT_QSS+TABLE_QSS+SCROLL_QSS+MENU_QSS+DIALOG_QSS
    set_theme(saved); return sheet

def html_colors():
    if CURRENT == "dark":
        return {"text":"#edf0ff","link":"#b09aff","block":"#27304e","formula":"#ffe08a","hint":"#98a1c3"}
    return {"text":"#20243b","link":"#5b3fd4","block":"#eef0f8","formula":"#7a4a00","hint":"#68708e"}

def apply_theme_to_app(app, theme):
    set_theme(theme); app.setStyleSheet(app_stylesheet())
    for w in app.topLevelWidgets():
        w.style().unpolish(w); w.style().polish(w); w.update()
        restyle=getattr(w,"retheme",None)
        if callable(restyle):
            try: restyle()
            except Exception: pass

set_theme("dark")
