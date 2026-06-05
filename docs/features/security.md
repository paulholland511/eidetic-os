# Feature: Security hardening for community skills

**Source:** [`eidetic_os/security.py`](../../eidetic_os/security.py),
[`eidetic_os/sandbox.py`](../../eidetic_os/sandbox.py) ·
**CLI:** `eidetic security scan <path>`, `eidetic security report`

A skill you install from a registry is *someone else's code*. Eidetic OS treats it
that way. Two layers stand between an untrusted skill and your machine:

1. **Static analysis** — before a skill is installed, every `.py` file it ships
   is parsed and checked for the patterns that let code take over the box. This
   never *runs* the skill, so scanning a hostile skill is itself safe.
2. **Runtime sandbox** — when a skill's code does run, it can be launched in an
   isolated child process under a CPU / memory / time budget with a minimal
   environment and network denied by default.

Together with the [append-only audit trail](./skills-and-automation.md), every
install attempt is scanned, gated, and recorded.

---

## Static analysis — the AST scanner

`scan_skill(path)` walks every `.py` file under a skill directory and parses each
one with Python's standard-library `ast` module. Matching patterns become
**findings**, each carrying a severity, a short code, the message, and a
`file:line:col` location.

| Severity | Meaning | Examples |
|---|---|---|
| **BLOCK** | Arbitrary code or command execution | `os.system`, `os.popen`, `subprocess.*(..., shell=True)`, `eval`, `exec`, `__import__`, `compile`, a file that doesn't parse |
| **WARN** | Legitimate but worth a human's eyes | `os.environ` access, `import socket`, `import ctypes`, `open(..., 'w')`, `subprocess.*` without a shell |
| **INFO** | Notable but expected | `import requests` / `httpx` / `urllib` |

`is_safe(report)` returns `True` only when there are **no** BLOCK-level findings.

The scanner resolves import aliases, so it sees through indirection:

```python
from subprocess import run as r
r("rm -rf /", shell=True)        # → BLOCK subprocess-shell

import os as operating
operating.system("whoami")        # → BLOCK os-system
```

A file that fails to parse is reported as a BLOCK `syntax-error` rather than
being silently skipped — unparseable code hides its behaviour from analysis and
must not be installed blind.

### Scan a skill by hand

```bash
eidetic security scan ./some-skill/          # scan a directory
eidetic security scan ./some-skill/code.py   # scan one file
```

The command prints each finding grouped by severity and exits non-zero if any
BLOCK finding is present — handy in CI for a skill repo.

---

## The install gate

`eidetic skills install <name>` scans the skill's source before copying anything:

- **BLOCK findings → install refused.** The report is shown and nothing is
  written. `--force` does **not** override a BLOCK; code that executes arbitrary
  commands is never installed.
- **WARN findings → install requires `--force`.** The warnings are shown; re-run
  with `--force` to accept them and proceed.
- **INFO findings** are shown but never block.
- **Clean skills** install exactly as before.

Every attempt — installed, blocked, or needing force — is written to the audit
trail under the `skill_install` action, so there's always a record of *what* you
installed and *what the scanner found*.

---

## The runtime sandbox

`run_sandboxed(script_path, ...)` launches a Python script in a fresh child
process under a budget:

```python
from eidetic_os.sandbox import run_sandboxed

result = run_sandboxed(
    "skill/code.py",
    timeout=30,        # wall-clock seconds; the process group is killed if exceeded
    memory_mb=256,     # address-space cap (POSIX)
    allow_network=False,  # network denied by default
)
print(result.exit_code, result.timed_out, result.duration_seconds)
```

What it restricts:

- **Time** — a wall-clock timeout kills the whole process group.
- **CPU** — a CPU-seconds limit (`RLIMIT_CPU`) catches busy loops that produce no
  output and so never trip the wall-clock read.
- **Memory** — an address-space limit (`RLIMIT_AS` / `RLIMIT_DATA`) turns a
  runaway allocation into a `MemoryError` instead of swapping the machine.
- **Environment** — the child sees a minimal, explicit environment (`PATH`,
  locale, …) — never the parent's secrets, tokens, or vault paths.
- **Network** — denied by default. The interpreter runs in isolated mode (`-I`),
  ignoring `PYTHON*` variables and user site-packages.

### A note on network denial

Network denial is **best-effort on macOS**. Without an in-process syscall
firewall (which macOS does not offer to an unprivileged process), the sandbox
points the child at an unroutable proxy so high-level HTTP clients
(`requests`, `httpx`, `urllib`) fail fast — but a determined script opening a raw
socket is not stopped at the kernel on macOS. On Linux the resource limits are
enforced by the kernel. Do not treat `allow_network=False` as a hard guarantee
on macOS; treat it as defence in depth alongside the static scan.

---

## `eidetic security report`

Summarises the security-relevant audit history — how many installs were
attempted, allowed, and blocked, plus the most recent attempts:

```bash
eidetic security report
eidetic security report --since 30d
```

---

## Design notes

- **Static analysis is advisory, not a proof.** A scanner can be evaded by
  sufficiently dynamic code; that's exactly why a BLOCK includes *unparseable*
  files and why the runtime sandbox exists as a second layer.
- **Pure, side-effect-free scanning.** `scan_skill` only reads files and returns
  a frozen `SecurityReport`; it never executes the code it inspects.
- **Honest about platform limits.** Memory and network enforcement depend on the
  OS; the docs and docstrings say so rather than implying a guarantee that isn't
  there.
