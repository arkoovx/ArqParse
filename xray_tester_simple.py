"""Совместимость со старым импортом top-level модуля."""

from importlib import import_module as _import_module
import sys as _sys


_module = _import_module("arqparse.core.xray_tester_simple")
_sys.modules[__name__] = _module
