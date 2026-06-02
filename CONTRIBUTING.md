# Contributing to Atlas OS

Thanks for your interest! Atlas OS is a template project, so contributions that
make it more useful, more portable, or safer are very welcome.

## The golden rule

**Never commit personal data, credentials, or PII.** Atlas OS is public and is
built to be safe to publish. Before every commit, ensure you are not adding:

- Real names, email addresses, phone numbers, or postal addresses
- API keys, passwords, tokens, or app passwords (use env vars)
- IP addresses of private/personal infrastructure (use `localhost` / env vars)
- Vault content, notes, spreadsheets, or exported data
- Vector stores (`vectors.json`), graphs (`graph.json`), or `.env` files

When in doubt, run a scan before committing:

```bash
grep -rniE "(@gmail|@outlook|@[a-z]+\.(com|co\.uk)|[0-9]{1,3}(\.[0-9]{1,3}){3}|api[_-]?key|password|secret)" . \
  --exclude-dir=.git --exclude-dir=.venv
```

Replace any match with an environment variable or a placeholder.

## Development environment

Atlas OS targets **Python 3.11+** (3.13 preferred). From a fresh checkout:

```bash
git clone https://github.com/paulholland511/atlas-os.git
cd atlas-os

# Create and activate a virtual environment (uv shown; venv/conda are fine too)
python -m venv .venv && source .venv/bin/activate

# Install the package (editable) plus the dev tooling
pip install -e ".[all]"        # core + optional extras (pdf, trading)
pip install -r requirements.txt  # test runner, linter, auditor
```

You can now run the CLI:

```bash
atlas --version
atlas doctor       # validates Python, vault, git, RAG index, endpoints
```

The tests are hermetic — they stub every external dependency and point
`VAULT_PATH`/`RAG_DIR` at a temp directory — so **no `.env`, network, or real
vault is needed to develop or test.**

## Running the checks

Run the same three checks CI runs, before opening a PR:

```bash
ruff check scripts tests       # lint
pytest                         # test suite (config in pyproject.toml)
pip-audit -r requirements.txt  # dependency CVE audit
```

`pytest` config lives in `pyproject.toml`; `tests/conftest.py` redirects the
vault to a throwaway temp directory before any script is imported.

## Coding standards (Python)

- Python 3.11+ (3.13 preferred)
- Type hints on public functions; docstrings explaining purpose
- All configuration via environment variables — no hardcoded paths/hosts/secrets
- Format/lint with `ruff` (line length 100); keep dependencies minimal
- Prefer pure functions and atomic file writes
- No new external dependencies without good reason — document any you add in
  `requirements.txt` / `pyproject.toml` and in the PR

## Skills & templates

- Keep `SKILL.md` files generic — use `{{PLACEHOLDER}}` tokens, never real values.
- New templates should ship with `.template` suffixes or clearly-placeholdered content.

## Project structure

```
atlas-os/
├── atlas_os/        the `atlas` CLI package (init, doctor, skills, wrappers)
├── scripts/         embed · graph · commit · changelog · email · health · trade
├── trading/         optional multi-agent research SDK
├── tests/           hermetic pytest suite (scripts + CLI; no network)
├── schemas/         frontmatter schema enforcement + docs
├── skills/          scheduled-task SKILL.md prompts (templated)
├── templates/       CLAUDE.md, memory structure, vault skeleton, ops dashboard
├── dashboard/       static ops dashboard + setup notes
├── docs/            setup, configuration, scripts, architecture, FAQ, features/
└── .github/         CI workflow + issue/PR templates
```

See the README's [Architecture](README.md#architecture) and
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for how the pieces fit together.

## Submitting a pull request

1. Fork and branch (`feat/...`, `fix/...`, `docs/...`).
2. Make your change; run `ruff check scripts tests`, `pytest`, and the PII scan above.
3. Update docs where relevant — README, `docs/`, and `CHANGELOG.md` (add to the
   `[Unreleased]` section). Note any new env vars in `.env.example` and
   `docs/CONFIGURATION.md`.
4. Open a PR using the template; describe what changed and why. CI (ruff →
   pytest → pip-audit) must pass.

## Reporting security issues

See [`SECURITY.md`](SECURITY.md) — do not open public issues for vulnerabilities.
