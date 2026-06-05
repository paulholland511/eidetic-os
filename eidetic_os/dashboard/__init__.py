"""The Eidetic OS lightweight web dashboard.

A small, local-first Flask application that surfaces the things you already run
from the ``eidetic`` command line — system health, the audit trail, scheduled
tasks, the skills catalog, vector-store stats, and RAG search — in a browser.

It is intentionally minimal: a single Flask app, Jinja2 templates, and one
hand-written dark-theme stylesheet. No JavaScript framework, no build step, no
bundled data. Every number it shows is read live from the existing Eidetic OS
modules (:mod:`eidetic_os.vectordb`, :mod:`eidetic_os.audit`,
:mod:`eidetic_os._skills`, …), so the dashboard is a *view* over your machine and
never a second source of truth.

Flask is an optional dependency — install it with ``pip install
'eidetic-os[dashboard]'``. The data-gathering layer (:mod:`eidetic_os.dashboard.data`)
has no Flask dependency at all, so it can be imported and tested on its own; only
:func:`eidetic_os.dashboard.app.create_app` needs Flask.

Launch it with ``eidetic dashboard`` (defaults to http://127.0.0.1:8501).
"""

from __future__ import annotations

__all__ = ["create_app"]


def create_app(*args: object, **kwargs: object):  # noqa: ANN401 - thin re-export
    """Build the dashboard Flask app. Re-exported from :mod:`.app`.

    Imported lazily so ``import eidetic_os.dashboard`` works without Flask present;
    the import error (with an install hint) only surfaces when you actually build
    the app.
    """
    from eidetic_os.dashboard.app import create_app as _create_app

    return _create_app(*args, **kwargs)
