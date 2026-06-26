"""Make psychro + model importable as plain top-level modules for tests.

Avoids triggering custom_components/window_advisor/__init__.py which imports HA.
"""
import sys
from pathlib import Path

INNER = Path(__file__).resolve().parent.parent / "custom_components" / "window_advisor"
sys.path.insert(0, str(INNER))

# Pre-create a stub package so model.py's `from . import psychro` resolves.
import importlib.util
import types

pkg = types.ModuleType("wa_pure")
pkg.__path__ = [str(INNER)]
sys.modules["wa_pure"] = pkg

for sub in ("psychro", "model"):
    spec = importlib.util.spec_from_file_location(f"wa_pure.{sub}", INNER / f"{sub}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"wa_pure.{sub}"] = mod
    spec.loader.exec_module(mod)
