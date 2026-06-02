# Changelog

All notable changes to Atlas OS are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
aims to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `docs/CONFIGURATION.md` — authoritative reference for every environment
  variable (purpose, default, required/optional, consuming scripts).
- `docs/SCRIPTS.md` — complete CLI reference for all scripts and their flags,
  including the previously-undocumented `embed_vault.py` flags
  (`--incremental`, `--folder`, `--pdfs-only`, `--checkpoint-interval`,
  `--batch-size`).
- `docs/FAQ.md` — frequently asked questions and troubleshooting.
- `docs/README.md` — documentation index and recommended reading order.
- `CHANGELOG.md` — this file.

### Changed
- `.env.example` now documents `LM_STUDIO_URL` (used by
  `scripts/trading_briefing.py`, expects a `/v1` suffix) alongside
  `LM_STUDIO_ENDPOINT` (used by `trading/config.py`/`core.py`, no suffix),
  clarifying which script reads which.
- Root `README.md` expanded with a documentation map and a full configuration
  pointer.

## [0.1.0] — 2026-06-02

### Added
- Initial public release of Atlas OS — a local-first personal AI operating
  system built on Claude Cowork.
- Knowledge vault conventions with per-folder frontmatter schema enforcement
  (`schemas/`).
- Local RAG pipeline (`scripts/embed_vault.py`) and wikilink knowledge graph
  (`scripts/build_graph.py`).
- Git automation: auto-commit (`scripts/vault_commit.py`) and changelog
  (`scripts/vault_changelog.py`).
- Credential-free SMTP email sender (`scripts/send_email.py`).
- System health check across all subsystems (`scripts/health_check.py`).
- Optional multi-agent trading research SDK (`trading/`) and briefing generator
  (`scripts/trading_briefing.py`).
- Nine Claude Cowork scheduled-task skills (`skills/`).
- Templates for `CLAUDE.md`, memory structure, vault skeleton, and a static ops
  dashboard (`templates/`, `dashboard/`).
- Documentation: setup, architecture, rebuild runbook, scheduled tasks, data
  classification; `SECURITY.md`, `CONTRIBUTING.md`, MIT `LICENSE`.

[Unreleased]: https://github.com/paulholland511/atlas-os/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/paulholland511/atlas-os/releases/tag/v0.1.0
