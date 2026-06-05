"""Concrete :class:`~eidetic_os.vector_backend.VectorBackend` implementations.

Each engine lives in its own module and is imported lazily by
:func:`eidetic_os.vector_backend.get_backend`, so importing this package costs
nothing and never pulls in an optional dependency:

* :mod:`~eidetic_os.vector_backends.sqlite_backend` — the zero-config default,
  wrapping :class:`eidetic_os.vectordb.VectorStore`. No extra dependencies.
* :mod:`~eidetic_os.vector_backends.lancedb_backend` — LanceDB: columnar,
  on-disk, zero-copy scans and rich metadata filtering (``eidetic-os[lancedb]``).
* :mod:`~eidetic_os.vector_backends.chroma_backend` — ChromaDB: a popular
  embedding database with a persistent local client (``eidetic-os[chroma]``).

The naming (``vector_backends``) deliberately sits apart from the existing
:mod:`eidetic_os.backends` module, which detects *LLM* backends (LM Studio,
Ollama, …) — a different axis entirely.
"""

from __future__ import annotations
