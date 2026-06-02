---
type: dashboard
title: Operations Dashboard
created: 2026-01-01
updated: 2026-01-01
tags: [dashboard, ops]
status: seed
---

# Operations Dashboard

A single-pane overview of your Atlas OS. If you use Obsidian, the
[Dataview](https://blacksmithgu.github.io/obsidian-dataview/) plugin can turn
the queries below into live tables. Otherwise treat this as a manual checklist.

## System Status

- **RAG index:** run `health_check.py` — vectors present? last embed recent?
- **Scheduled tasks:** all `SKILL.md` files present in the Scheduled dir?
- **Git:** vault committed and clean?

## Recent Activity

```dataview
TABLE file.mtime AS "Modified"
FROM ""
SORT file.mtime DESC
LIMIT 10
```

## Active Projects

```dataview
TABLE status, updated
FROM "projects"
WHERE status = "active"
SORT updated DESC
```

## Open Decisions

```dataview
LIST
FROM "decisions"
WHERE status = "draft"
```

## Quick Links

- [[index]] — wiki index
- [[hot]] — modification log
- [[log]] — sync log
