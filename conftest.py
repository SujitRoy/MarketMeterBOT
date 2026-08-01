"""
conftest.py — pytest root config for MarketMeter.

Phase 2: ensures src/ is on sys.path so `from marketmeter.X import Y` works
in tests without manually setting PYTHONPATH. Loaded automatically by pytest
at the start of every test run, before any test module is imported.

Phase 6 will retire this in favour of `pip install -e .` for the test runner,
at which point src/ will be importable globally.
"""
import sys
from pathlib import Path

# Resolve src/ relative to this conftest.py location (project root).
_ROOT = Path(__file__).resolve().parent
_SRC = _ROOT / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Tests can run from the project root without PYTHONPATH env; this is the
# canonical place to add cross-test fixtures (Phase 6).
