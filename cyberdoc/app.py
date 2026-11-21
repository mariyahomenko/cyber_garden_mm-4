import os
import sys

import urllib3
from PyQt5 import QtCore, QtGui, QtWidgets

from . import theme
from .ui.main_window import PDFSearchApp


def _load_app_font(app):
    """Загружает кастомный шрифт из файла и делает его шрифтом по умолчанию."""
    base = os.path.dirname(os.path.abspath(__file__))
    font_path = os.path.join(base, "assets", "fonts", "Custom.ttf")
    if not os.path.exists(font_path):
        return
    font_id = QtGui.QFontDatabase.addApplicationFont(font_path)
    if font_id == -1:
        return
    families = QtGui.QFontDatabase.applicationFontFamilies(font_id)
    if not families:
        return
    font = QtGui.QFont(families[0])
    font.setPointSize(10)
    app.setFont(font)


def main():
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("CyberDoc")
    app.setStyle("Fusion")

    _load_app_font(app)

    settings = QtCore.QSettings("CyberGarden", "CyberDoc")
    theme.apply_theme_to_app(app, settings.value("theme", "dark"))
    window = PDFSearchApp()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
