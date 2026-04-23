import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def pytest_ignore_collect(collection_path, config):
    path = Path(str(collection_path))
    if path.name != "test_gui_merge.py":
        return False
    return (
        importlib.util.find_spec("kivy") is None
        or importlib.util.find_spec("kivymd") is None
    )
