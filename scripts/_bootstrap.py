"""Make the ``eidetic_os`` package importable from a standalone script run.

The pipeline scripts run two ways:

1. Installed (``eidetic embed`` → wheel): ``eidetic_os`` is on ``sys.path`` already,
   so ``import eidetic_os`` just works.
2. Source checkout (``python scripts/embed_vault.py``): the package isn't
   installed, so we walk up from this file to the repo root (the dir containing
   ``eidetic_os/__init__.py``) and put it on ``sys.path``.

Call :func:`ensure_eidetic_os` at the top of a script before importing the shared
hardening helpers (``eidetic_os.retry`` / ``netio`` / ``fileio`` / ``gitutil`` /
``scriptkit``). It returns ``True`` if the package is importable, ``False`` if
not — letting a script degrade gracefully rather than crash on import.
"""

from __future__ import annotations

import sys
from pathlib import Path


def ensure_eidetic_os() -> bool:
    """Ensure ``import eidetic_os`` works; return whether it is importable."""
    try:
        import eidetic_os  # noqa: F401
        return True
    except ImportError:
        pass
    for parent in Path(__file__).resolve().parents:
        if (parent / "eidetic_os" / "__init__.py").exists():
            sys.path.insert(0, str(parent))
            break
    try:
        import eidetic_os  # noqa: F401
        return True
    except ImportError:
        return False
