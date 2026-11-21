"""Запуск: python main.py"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from cyberdoc.app import main

main()
