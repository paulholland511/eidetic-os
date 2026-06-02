# Scheduled Tasks

Atlas OS automations are Claude Cowork **skills** run on a schedule. Each lives
in `skills/<name>/SKILL.md`. To install one, copy its folder into your Claude
scheduled-tasks directory and replace the `{{PLACEHOLDER}}` tokens with your real
values, then register it on the cadence below.

## Placeholders used across skills

| Token | Meaning |
|---|---|
| `{{VAULT_PATH}}` | Absolute path to your vault |
| `{{ATLAS_OS}}` | Absolute path to this repo |
| `{{USER_EMAIL}}` | Where reports are sent |
| `{{EMBED_HOST}}` / `{{EMBED_PORT}}` | Local embeddings endpoint |
| `{{LLM_PORT}}` | Local chat-completions port |
| `{{JOB_TRACKER_PATH}}` | Your job-tracker `.xlsx` (keep outside the repo) |
| `{{WATCHLIST}}` | Companies/recruiters or tickers you track |
| `{{NEWSLETTER_BRAND}}` | Your newsletter name |
| `{{READER_ROLE}}` | Perspective the newsletter is written for |

## The tasks

| Skill | Suggested cadence | What it does |
|---|---|---|
| `nightly-obsidian-index` | Nightly (e.g. 02:00) | Index new/changed notes, sync the wiki to 100% coverage, append the hot cache, commit the vault, write a morning briefing |
| `nightly-rag-incremental` | Nightly (after the index) | Embed only notes changed since the last run |
| `daily-job-tracker-update` | Weekday mornings | Scan email for application updates; update the tracker |
| `afternoon-job-tracker-update` | Weekday ~14:00 | Catch afternoon emails; update the tracker |
| `atlas-daily-report-email` | Daily (e.g. 09:30) | Email a status report (job search, system health, action items) |
| `daily-trading-report` | Daily (e.g. 13:00) | Run the analyst agents on your watchlist; email a research report |
| `friday-it-newsletter` | Fridays AM | Compile and email a weekly IT-news digest; save to the vault |
| `weekly-system-health-check` | Weekly | Probe every subsystem; email a health report; auto-fix safe issues |
| `weekly-rag-full-reembed` | Weekly (e.g. Sun early AM) | Re-embed the entire vault from scratch |

> The job-tracker, trading, and newsletter tasks are entirely optional and only
> useful if those workflows apply to you. Start with the index + RAG + health
> tasks and add others as needed.

## Notes on safety

- Job-tracker and trading tasks touch **confidential** data (see
  [`DATA-CLASSIFICATION.md`](DATA-CLASSIFICATION.md)). Keep those files outside
  this repo and never commit them.
- Tasks that send email need `SENDER_EMAIL` and `SMTP_APP_PASSWORD` in the
  environment — never inline credentials in a `SKILL.md`.
- Each task is written to run unattended: it makes reasonable choices rather than
  asking questions. Review the prompt before enabling it so you're comfortable
  with what it will do.
