"""Concrete :class:`~atlas_os.vector_backend.VectorBackend` implementations.

Each engine lives in its own module and is imported lazily by
:func:`atlas_os.vector_backend.get_backend`, so importing this package costs
nothing and never pulls in an optional dependency:

* :mod:`~atlas_os.vector_backends.sqlite_backend` — the zero-config default,
  wrapping :class:`atlas_os.vectordb.VectorStore`. No extra dependencies.
* :mod:`~atlas_os.vector_backends.lancedb_backend` — LanceDB: columnar,
  on-disk, zero-copy scans and rich metadata filtering (``atlas-os[lancedb]``).
* :mod:`~atlas_os.vector_backends.chroma_backend` — ChromaDB: a popular
  embedding database with a persistent local client (``atlas-os[chroma]``).

The naming (``vector_backends``) deliberately sits apart from the existing
:mod:`atlas_os.backends` module, which detects *LLM* backends (LM Studio,
Ollama, …) — a different axis entirely.
"""

from __future__ import annotations
