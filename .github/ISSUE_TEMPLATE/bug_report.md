---
name: Bug report
about: Report something that isn't working as documented
title: "[Bug] "
labels: bug
assignees: ""
---

<!--
Before filing: please run `atlas doctor` and skim docs/FAQ.md — many issues are
configuration (missing env vars, vault not a git repo, LLM endpoint unreachable).
NEVER paste real secrets, API keys, app passwords, vault content, or PII into
this issue. Redact paths, hostnames, and email addresses.
-->

## Description

A clear and concise description of what the bug is.

## Steps to reproduce

1. Run `...`
2. With config `...`
3. See error

## Expected behavior

What you expected to happen.

## Actual behavior

What actually happened.

## Environment

- OS: <!-- e.g. macOS 15.5, Ubuntu 24.04, Windows 11 + WSL2 -->
- Python version: <!-- output of `python --version` -->
- Atlas OS version: <!-- output of `atlas --version`, or the git commit SHA -->
- Install method: <!-- pip install -e . / uv tool install / pipx / Docker -->

## Logs / screenshots

<!-- Paste relevant output (redacted). Use ``` fences. Attach screenshots if helpful. -->

```
<paste here>
```
