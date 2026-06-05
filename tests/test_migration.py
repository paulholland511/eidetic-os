"""Backend-to-backend migration tests.

``vector_backend.migrate`` must move every chunk from one engine to another with
no loss — the count matches and search still returns the right answers. The
matrix covers every ordered pair of available backends (SQLite always; LanceDB /
ChromaDB only where installed), so e.g. sqlite→lancedb and lancedb→chroma are all
exercised when the extras are present.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atlas_os import vector_backend
from atlas_os.vector_backend import VectorBackend
from tests.test_vector_backends import BACKEND_FACTORIES, _entries

_NAMES = list(BACKEND_FACTORIES)


def _open(name: str, rag_dir: Path) -> VectorBackend:
    return BACKEND_FACTORIES[name](rag_dir)  # may pytest.skip


@pytest.mark.parametrize("src_name", _NAMES)
@pytest.mark.parametrize("dst_name", _NAMES)
def test_migrate_preserves_everything(
    src_name: str, dst_name: str, tmp_path: Path
) -> None:
    source = _open(src_name, tmp_path / "src")
    target = _open(dst_name, tmp_path / "dst")
    try:
        source.insert(_entries())

        copied = vector_backend.migrate(source, target)

        assert copied == source.count()
        assert target.count() == source.count() == 3
        assert target.files() == source.files()

        # Search parity: the same query ranks the same file first in both stores.
        src_top = source.search([1.0, 0.0, 0.0], k=1)[0]
        dst_top = target.search([1.0, 0.0, 0.0], k=1)[0]
        assert dst_top["file"] == src_top["file"] == "research/a.md"
        assert dst_top["text"] == src_top["text"]
    finally:
        source.close()
        target.close()


def test_migrate_reports_progress(tmp_path: Path) -> None:
    source = _open("sqlite", tmp_path / "src")
    target = _open("sqlite", tmp_path / "dst")
    try:
        source.insert(_entries())
        seen: list[int] = []
        copied = vector_backend.migrate(
            source, target, batch_size=1, on_progress=seen.append
        )
        assert copied == 3
        # One callback per batch of one → the running total climbs to 3.
        assert seen == [1, 2, 3]
    finally:
        source.close()
        target.close()


def test_migrate_empty_source(tmp_path: Path) -> None:
    source = _open("sqlite", tmp_path / "src")
    target = _open("sqlite", tmp_path / "dst")
    try:
        assert vector_backend.migrate(source, target) == 0
        assert target.count() == 0
    finally:
        source.close()
        target.close()
