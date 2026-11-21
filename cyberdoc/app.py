import sys

import urllib3
from PyQt5 import QtCore, QtWidgets

from . import theme
from .ui.main_window import PDFSearchApp


def main():
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("CyberDoc")
    app.setStyle("Fusion")
    settings = QtCore.QSettings("CyberGarden", "CyberDoc")
    theme.apply_theme_to_app(app, settings.value("theme", "dark"))
    window = PDFSearchApp()
    window.show()
    # Ключ API при запуске НЕ запрашивается: окно ввода ключа появляется
    # только при первом «умном» поиске (ответ на вопрос).
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
