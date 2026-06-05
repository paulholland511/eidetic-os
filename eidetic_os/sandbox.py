"""Run untrusted skill code under a CPU / memory / time / network budget.

:mod:`eidetic_os.security` vets a skill *statically* before it is installed; this
module is the *runtime* half of the same defence. :func:`run_sandboxed` launches
a Python script in a fresh, isolated child process and caps what it can consume:

* **Time** — a wall-clock ``timeout``; the whole process group is killed if it
  is exceeded.
* **Memory** — an address-space limit via :func:`resource.setrlimit` (POSIX), so
  a runaway allocation fails with ``MemoryError`` instead of swapping the box.
* **CPU** — a CPU-seconds limit as a backstop against a busy loop that produces
  no output and so never trips the wall-clock read.
* **Environment** — the child sees a minimal, explicit environment, not the
  parent's (which may hold API keys, tokens, vault paths).
* **Network** — denied by default. Where the platform offers no in-process
  syscall firewall (macOS), denial is *best-effort*: the child is pointed at an
  unroutable proxy so high-level HTTP clients fail fast. Opt back in with
  ``allow_network=True``. This is documented honestly because it matters: do not
  treat ``allow_network=False`` as a kernel-enforced guarantee on macOS.

The interpreter is started with ``-I`` (isolated mode), so it ignores
``PYTHON*`` environment variables and the user site-packages directory.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

try:  # POSIX resource limits (macOS + Linux). Absent on Windows.
    import resource
except ImportError:  # pragma: no cover - Windows fallback
    resource = None  # type: ignore[assignment]


# Environment keys that are safe-to-harmless to pass through to the child so a
# vetted skill still behaves (locale, a minimal PATH). Everything else — every
# secret, token, and host the parent holds — is dropped.
_PASSTHROUGH_ENV: tuple[str, ...] = ("PATH", "LANG", "LC_ALL", "LC_CTYPE", "TZ", "TMPDIR")

# An unroutable address (RFC 5737 TEST-NET-1) used as a dead proxy so that
# requests/httpx/urllib fail fast when network access is denied.
_DEAD_PROXY = "http://192.0.2.0:9"


@dataclass(frozen=True)
class SandboxResult:
    """Outcome of a sandboxed run."""

    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool
    duration_seconds: float

    @property
    def ok(self) -> bool:
        """True if the script exited cleanly (code 0) and did not time out."""
        return self.exit_code == 0 and not self.timed_out


def build_sandbox_env(
    *, allow_network: bool, extra: dict[str, str] | None = None
) -> dict[str, str]:
    """Construct the minimal environment handed to the sandboxed child.

    Only :data:`_PASSTHROUGH_ENV` keys are inherited from the parent. When
    ``allow_network`` is False, proxy variables are pointed at an unroutable
    address so high-level HTTP libraries fail fast. ``extra`` is merged last and
    wins, letting a caller inject skill-specific configuration explicitly.
    """
    env: dict[str, str] = {}
    for key in _PASSTHROUGH_ENV:
        value = os.environ.get(key)
        if value is not None:
            env[key] = value
    env.setdefault("PATH", "/usr/bin:/bin")
    # Tell the interpreter not to write .pyc files into the (untrusted) skill dir.
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    if not allow_network:
        for proxy_key in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
            env[proxy_key] = _DEAD_PROXY
        env["no_proxy"] = ""
        env["NO_PROXY"] = ""

    if extra:
        env.update(extra)
    return env


def _limit_preexec(memory_mb: int, cpu_seconds: int):
    """Build a ``preexec_fn`` that applies rlimits and a new session, or None.

    Returns ``None`` when :mod:`resource` is unavailable (Windows), in which case
    the run falls back to wall-clock timeout enforcement only.
    """
    if resource is None:  # pragma: no cover - Windows fallback
        return None

    def _apply() -> None:  # pragma: no cover - runs in the forked child
        # New session/process group so we can kill the whole tree on timeout.
        os.setsid()

        memory_bytes = memory_mb * 1024 * 1024
        for limit_name in ("RLIMIT_AS", "RLIMIT_DATA"):
            limit = getattr(resource, limit_name, None)
            if limit is None:
                continue
            try:
                resource.setrlimit(limit, (memory_bytes, memory_bytes))
            except (ValueError, OSError):
                # Some platforms refuse RLIMIT_AS; the other limit still applies.
                pass

        # CPU-seconds backstop for output-less busy loops. Pad by 1s so the
        # wall-clock timeout is normally the first to fire for honest scripts.
        cpu_limit = getattr(resource, "RLIMIT_CPU", None)
        if cpu_limit is not None:
            try:
                resource.setrlimit(cpu_limit, (cpu_seconds + 1, cpu_seconds + 1))
            except (ValueError, OSError):
                pass

    return _apply


def _terminate_group(process: subprocess.Popen[str]) -> None:
    """Kill the child's whole process group (best effort)."""
    try:
        os.killpg(os.getpgid(process.pid), 9)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            process.kill()
        except OSError:
            pass


def run_sandboxed(
    script_path: str | Path,
    *,
    timeout: int = 30,
    memory_mb: int = 256,
    allow_network: bool = False,
    args: list[str] | None = None,
    env: dict[str, str] | None = None,
) -> SandboxResult:
    """Execute a Python script in an isolated, resource-limited subprocess.

    Parameters
    ----------
    script_path:
        The ``.py`` file to run.
    timeout:
        Wall-clock seconds before the process group is killed.
    memory_mb:
        Address-space cap (POSIX only); a breach raises ``MemoryError`` in the
        child, which then exits non-zero.
    allow_network:
        Leave the parent's proxy configuration alone instead of pointing it at a
        dead address. Best-effort on macOS — see the module docstring.
    args:
        Extra command-line arguments passed to the script.
    env:
        Extra environment entries merged into the minimal sandbox environment.

    Returns a :class:`SandboxResult` with the captured output and whether the run
    hit the timeout. Raises :class:`FileNotFoundError` if the script is missing.
    """
    script = Path(script_path)
    if not script.is_file():
        raise FileNotFoundError(f"no such script: {script}")

    command = [sys.executable, "-I", str(script), *(args or [])]
    child_env = build_sandbox_env(allow_network=allow_network, extra=env)
    preexec = _limit_preexec(memory_mb, timeout)

    start = time.monotonic()
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(script.parent),
        env=child_env,
        preexec_fn=preexec,  # noqa: PLW1509 (intentional: rlimits in the child)
    )

    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        _terminate_group(process)
        stdout, stderr = process.communicate()
    duration = time.monotonic() - start

    return SandboxResult(
        exit_code=process.returncode if process.returncode is not None else -1,
        stdout=stdout or "",
        stderr=stderr or "",
        timed_out=timed_out,
        duration_seconds=round(duration, 3),
    )
