# Changelog

All notable changes to Atlas OS are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
aims to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] — 2026-06-02

### Added
- **Installable package** with a unified **`atlas` CLI** (`pyproject.toml`,
  `atlas_os/`). Install via `uv tool install` / `pipx` / `pip install -e .`.
  Subcommands `embed`, `graph`, `commit`, `changelog`, `health`, `email`, and
  `schemas` wrap the existing scripts and forward their flags; configuration
  (`.env`) is auto-loaded.
- **`atlas init`** — guided onboarding: auto-detects a local LLM (LM Studio /
  Ollama / any OpenAI-compatible endpoint), writes `.env`, scaffolds the vault
  skeleton, initialises the vault git repo, and optionally installs the
  `CLAUDE.md` template. Supports `--vault`, `--yes`, `--force`.
- **`atlas doctor`** — validates the whole setup (Python, vault, git, RAG
  index, embeddings endpoint, SMTP) and reports OK / WARN / FAIL with a
  non-zero exit on failures.
- Optional dependency extras: `atlas-os[trading]` (yfinance),
  `atlas-os[pdf]` (pdfplumber), `atlas-os[all]`.
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
- The scripts/schemas/templates are now bundled into the wheel (under
  `atlas_os_data/`) so an installed `atlas` works without the source checkout;
  in a source checkout the CLI uses the live files.
- `.env.example` now documents `LM_STUDIO_URL` (used by
  `scripts/trading_briefing.py`, expects a `/v1` suffix) alongside
  `LM_STUDIO_ENDPOINT` (used by `trading/config.py`/`core.py`, no suffix),
  clarifying which script reads which.
- Root `README.md` expanded with the install/CLI quick start, a CLI command
  table, badges, a documentation map, and a configuration pointer.
- `docs/SETUP.md` restructured into "install the package" (recommended) vs
  "run from a source checkout".

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

[Unreleased]: https://github.com/paulholland511/atlas-os/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/paulholland511/atlas-os/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/paulholland511/atlas-os/releases/tag/v0.1.0
