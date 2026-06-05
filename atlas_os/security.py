"""Static security analysis for community skills.

Before Atlas OS installs a skill it can't fully trust — anything pulled from a
registry or handed to you by someone else — this module reads every ``.py`` file
the skill ships and parses it with the standard-library :mod:`ast` module,
flagging the patterns that let untrusted code take over the machine: a shell
spawned with ``shell=True``, ``os.system``, ``eval``/``exec``, dynamic
``__import__`` and friends.

The scan is *static* — it never runs the skill's code, so analysing a hostile
skill is itself safe. Findings carry a :class:`Severity`:

``BLOCK``
    Arbitrary code or command execution. :func:`is_safe` refuses any report that
    contains one of these, and ``atlas skills install`` will not proceed.
``WARN``
    Capabilities that are legitimate but worth a human's eyes — environment
    access, raw sockets, writing files, spawning a subprocess without a shell.
``INFO``
    Notable-but-expected behaviour, e.g. importing an HTTP client.

The companion :mod:`atlas_os.sandbox` covers the *runtime* side — executing a
vetted skill under a CPU/memory/time budget — for defence in depth.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class Severity(str, Enum):
    """How dangerous a finding is. Ordered ``BLOCK`` > ``WARN`` > ``INFO``."""

    BLOCK = "BLOCK"
    WARN = "WARN"
    INFO = "INFO"

    @property
    def rank(self) -> int:
        """Numeric weight for sorting (higher = more severe)."""
        return {"INFO": 0, "WARN": 1, "BLOCK": 2}[self.value]


@dataclass(frozen=True)
class Finding:
    """One flagged pattern: where it is, how bad it is, and why."""

    severity: Severity
    code: str  # short stable identifier, e.g. "exec-call"
    message: str  # human-readable explanation
    file: Path
    line: int
    column: int

    def location(self, *, relative_to: Path | None = None) -> str:
        """``path:line:col`` for display; relative to ``relative_to`` if given."""
        shown = self.file
        if relative_to is not None:
            try:
                shown = self.file.relative_to(relative_to)
            except ValueError:
                shown = self.file
        return f"{shown}:{self.line}:{self.column}"


@dataclass(frozen=True)
class SecurityReport:
    """The result of scanning a skill directory.

    Holds every :class:`Finding`, the files that were scanned, and any files that
    could not be parsed (a syntax error is itself suspicious, so it surfaces as a
    ``BLOCK`` finding rather than being silently dropped).
    """

    skill_path: Path
    findings: tuple[Finding, ...] = ()
    scanned_files: tuple[Path, ...] = ()

    def with_severity(self, severity: Severity) -> tuple[Finding, ...]:
        """All findings at exactly ``severity``."""
        return tuple(f for f in self.findings if f.severity is severity)

    @property
    def blocks(self) -> tuple[Finding, ...]:
        """``BLOCK``-level findings — any one of these makes the skill unsafe."""
        return self.with_severity(Severity.BLOCK)

    @property
    def warnings(self) -> tuple[Finding, ...]:
        """``WARN``-level findings."""
        return self.with_severity(Severity.WARN)

    @property
    def infos(self) -> tuple[Finding, ...]:
        """``INFO``-level findings."""
        return self.with_severity(Severity.INFO)

    @property
    def counts(self) -> dict[str, int]:
        """``{"BLOCK": n, "WARN": n, "INFO": n}`` for summaries."""
        return {s.value: len(self.with_severity(s)) for s in Severity}


def is_safe(report: SecurityReport) -> bool:
    """True only when a report has **no** ``BLOCK``-level findings."""
    return not report.blocks


# ─────────────────────────────────────────────────────────────────────────────
# Dangerous-pattern catalogue
# ─────────────────────────────────────────────────────────────────────────────
# Fully-qualified callables that mean "run arbitrary code / commands". A call to
# any of these is a hard BLOCK regardless of arguments.
_BLOCK_CALLS: dict[str, tuple[str, str]] = {
    "eval": ("eval-call", "eval() executes arbitrary code"),
    "exec": ("exec-call", "exec() executes arbitrary code"),
    "__import__": ("dynamic-import", "__import__() loads modules dynamically"),
    "compile": ("compile-call", "compile() builds executable code objects"),
    "os.system": ("os-system", "os.system() runs an arbitrary shell command"),
    "os.popen": ("os-popen", "os.popen() runs an arbitrary shell command"),
}

# subprocess entry points. With ``shell=True`` they are a BLOCK (a shell parses
# the command); without it they are a WARN (still process execution).
_SUBPROCESS_CALLS: frozenset[str] = frozenset(
    {
        "subprocess.run",
        "subprocess.call",
        "subprocess.check_call",
        "subprocess.check_output",
        "subprocess.Popen",
        "subprocess.getoutput",
        "subprocess.getstatusoutput",
    }
)

# Imports worth surfacing: module name → (severity, code, message).
_IMPORT_FLAGS: dict[str, tuple[Severity, str, str]] = {
    "socket": (Severity.WARN, "socket-import", "imports socket (raw network access)"),
    "requests": (Severity.INFO, "requests-import", "imports requests (network access)"),
    "httpx": (Severity.INFO, "httpx-import", "imports httpx (network access)"),
    "urllib": (Severity.INFO, "urllib-import", "imports urllib (network access)"),
    "ctypes": (Severity.WARN, "ctypes-import", "imports ctypes (native memory / FFI)"),
}

# Write-ish file modes for open(): any of these characters means the call can
# create or mutate a file on disk.
_WRITE_MODE_CHARS: frozenset[str] = frozenset({"w", "a", "x", "+"})


def _call_target(func: ast.expr, aliases: dict[str, str]) -> str | None:
    """Resolve a call's callee to a canonical dotted name, honouring imports.

    ``aliases`` maps a local name to the canonical thing it refers to (built by
    :class:`_ImportCollector`). ``run`` → ``subprocess.run`` for
    ``from subprocess import run``; ``sp.run`` → ``subprocess.run`` for
    ``import subprocess as sp``. Returns ``None`` for callees we can't name
    statically (e.g. ``get_func()()``).
    """
    if isinstance(func, ast.Name):
        return aliases.get(func.id, func.id)
    if isinstance(func, ast.Attribute):
        base = _attr_root(func.value, aliases)
        if base is None:
            return None
        return f"{base}.{func.attr}"
    return None


def _attr_root(node: ast.expr, aliases: dict[str, str]) -> str | None:
    """Dotted name of an attribute chain's base, mapping the leftmost alias."""
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        base = _attr_root(node.value, aliases)
        return f"{base}.{node.attr}" if base is not None else None
    return None


def _has_shell_true(call: ast.Call) -> bool:
    """True if the call passes ``shell=True`` as a literal keyword argument."""
    for keyword in call.keywords:
        if keyword.arg == "shell" and _is_literal_true(keyword.value):
            return True
    return False


def _is_literal_true(node: ast.expr) -> bool:
    """True if ``node`` is the literal ``True`` (covers any truthy constant)."""
    return isinstance(node, ast.Constant) and bool(node.value)


def _open_write_mode(call: ast.Call) -> str | None:
    """Return the literal write mode an ``open()`` call uses, or None.

    Looks at the second positional argument and the ``mode=`` keyword. Only
    literal strings are inspected; a computed mode is left to the WARN-free path
    (we don't guess).
    """
    mode: str | None = None
    if len(call.args) >= 2 and isinstance(call.args[1], ast.Constant):
        value = call.args[1].value
        if isinstance(value, str):
            mode = value
    for keyword in call.keywords:
        if keyword.arg == "mode" and isinstance(keyword.value, ast.Constant):
            value = keyword.value.value
            if isinstance(value, str):
                mode = value
    if mode is not None and any(ch in _WRITE_MODE_CHARS for ch in mode):
        return mode
    return None


class _ImportCollector(ast.NodeVisitor):
    """First pass: build the alias map and flag notable imports."""

    def __init__(self, file: Path) -> None:
        self.file = file
        self.aliases: dict[str, str] = {}
        self.findings: list[Finding] = []

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802 (ast API)
        for alias in node.names:
            local = alias.asname or alias.name.split(".")[0]
            self.aliases[local] = alias.name
            self._flag_module(alias.name, node)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        module = node.module or ""
        if module:
            self._flag_module(module, node)
        for alias in node.names:
            local = alias.asname or alias.name
            self.aliases[local] = f"{module}.{alias.name}" if module else alias.name
        self.generic_visit(node)

    def _flag_module(self, module: str, node: ast.stmt) -> None:
        root = module.split(".")[0]
        flag = _IMPORT_FLAGS.get(root)
        if flag is not None:
            severity, code, message = flag
            self.findings.append(
                Finding(severity, code, message, self.file, node.lineno, node.col_offset)
            )


class _CallScanner(ast.NodeVisitor):
    """Second pass: flag dangerous calls using the collected alias map."""

    def __init__(self, file: Path, aliases: dict[str, str]) -> None:
        self.file = file
        self.aliases = aliases
        self.findings: list[Finding] = []

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802 (ast API)
        target = _call_target(node.func, self.aliases)
        if target is not None:
            self._classify(target, node)
        self.generic_visit(node)

    def _classify(self, target: str, node: ast.Call) -> None:
        block = _BLOCK_CALLS.get(target)
        if block is not None:
            code, message = block
            self._add(Severity.BLOCK, code, message, node)
            return

        if target in _SUBPROCESS_CALLS:
            short = target.rsplit(".", 1)[-1]
            if _has_shell_true(node):
                self._add(
                    Severity.BLOCK,
                    "subprocess-shell",
                    f"subprocess.{short}(..., shell=True) runs a shell command",
                    node,
                )
            else:
                self._add(
                    Severity.WARN,
                    "subprocess-exec",
                    f"subprocess.{short}() spawns a process",
                    node,
                )
            return

        if target in ("open", "io.open", "builtins.open"):
            mode = _open_write_mode(node)
            if mode is not None:
                self._add(
                    Severity.WARN,
                    "open-write",
                    f"open() in write mode {mode!r} can create/modify files",
                    node,
                )

    def _add(self, severity: Severity, code: str, message: str, node: ast.Call) -> None:
        self.findings.append(
            Finding(severity, code, message, self.file, node.lineno, node.col_offset)
        )


class _AttributeScanner(ast.NodeVisitor):
    """Second pass companion: flag bare ``os.environ`` access."""

    def __init__(self, file: Path, aliases: dict[str, str]) -> None:
        self.file = file
        self.aliases = aliases
        self.findings: list[Finding] = []

    def visit_Attribute(self, node: ast.Attribute) -> None:  # noqa: N802 (ast API)
        root = _attr_root(node, self.aliases)
        if root in ("os.environ", "os.getenv", "os.putenv", "os.environb"):
            self.findings.append(
                Finding(
                    Severity.WARN,
                    "env-access",
                    f"{root} reads or mutates environment variables",
                    self.file,
                    node.lineno,
                    node.col_offset,
                )
            )
        self.generic_visit(node)


def scan_source(source: str, file: Path) -> list[Finding]:
    """Scan one Python source string, returning its findings.

    A :class:`SyntaxError` is reported as a ``BLOCK`` finding (unparseable code
    hides its behaviour from static analysis and must not be installed blind).
    """
    try:
        tree = ast.parse(source, filename=str(file))
    except SyntaxError as exc:
        return [
            Finding(
                Severity.BLOCK,
                "syntax-error",
                f"file does not parse as Python ({exc.msg}); cannot be vetted",
                file,
                exc.lineno or 1,
                exc.offset or 0,
            )
        ]

    imports = _ImportCollector(file)
    imports.visit(tree)

    calls = _CallScanner(file, imports.aliases)
    calls.visit(tree)

    attrs = _AttributeScanner(file, imports.aliases)
    attrs.visit(tree)

    return imports.findings + calls.findings + attrs.findings


def _sort_key(finding: Finding) -> tuple[int, str, int, int]:
    """Order findings most-severe first, then by file and position."""
    return (-finding.severity.rank, str(finding.file), finding.line, finding.column)


def scan_skill(path: Path) -> SecurityReport:
    """Statically scan every ``.py`` file under a skill directory.

    ``path`` may be a skill directory (every ``*.py`` beneath it is scanned) or a
    single ``.py`` file. Findings are sorted most-severe first. Files that cannot
    be read surface as ``BLOCK`` findings rather than being skipped.
    """
    path = Path(path)
    if path.is_file():
        py_files = [path] if path.suffix == ".py" else []
    else:
        py_files = sorted(p for p in path.rglob("*.py") if p.is_file())

    findings: list[Finding] = []
    scanned: list[Path] = []
    for py_file in py_files:
        scanned.append(py_file)
        try:
            source = py_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            findings.append(
                Finding(
                    Severity.BLOCK,
                    "unreadable",
                    f"file could not be read for scanning ({exc})",
                    py_file,
                    1,
                    0,
                )
            )
            continue
        findings.extend(scan_source(source, py_file))

    findings.sort(key=_sort_key)
    return SecurityReport(
        skill_path=path,
        findings=tuple(findings),
        scanned_files=tuple(scanned),
    )
