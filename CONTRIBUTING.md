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

## Coding standards (Python)

- Python 3.11+ (3.13 preferred)
- Type hints on public functions; docstrings explaining purpose
- All configuration via environment variables — no hardcoded paths/hosts/secrets
- Format/lint with `ruff`; keep dependencies minimal
- Prefer pure functions and atomic file writes

## Skills & templates

- Keep `SKILL.md` files generic — use `{{PLACEHOLDER}}` tokens, never real values.
- New templates should ship with `.template` suffixes or clearly-placeholdered content.

## Workflow

1. Fork and branch (`feat/...`, `fix/...`).
2. Make your change; run the PII scan above.
3. Open a PR describing what and why. Note any new env vars in `.env.example`.

## Reporting security issues

See [`SECURITY.md`](SECURITY.md) — do not open public issues for vulnerabilities.
