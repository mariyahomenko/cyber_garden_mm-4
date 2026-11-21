"""Точка входа: позволяет запускать пакет двумя способами:

    python -m <папка_пакета>
    python <папка_пакета>/__main__.py
"""

import os
import sys

_pkg = __package__
if not _pkg:
    here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(here))
    _pkg = os.path.basename(here)

_mod = __import__(_pkg + ".app", fromlist=["main"])
_mod.main()
