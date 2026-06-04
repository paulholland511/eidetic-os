#!/usr/bin/env python3
"""Render the per-topic animated terminal GIFs for the Atlas OS README and docs.

Produces four focused screencasts that supplement the headline ``demo.gif``:

    install.gif    `pip install atlas-os` + version check (animated download bar)
    setup.gif      `atlas init` interactive wizard, with typed answers
    search.gif     `atlas search` hybrid RAG results
    dashboard.gif  `atlas dashboard` launch + health summary

Shares the look of ``scripts/make_demo_gif.py`` (macOS terminal chrome, Menlo,
typewriter prompts, supersampled text). Pure synthetic output, Pillow only.

    python3 scripts/make_doc_gifs.py            # writes the four GIFs in repo root
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# ── canvas / theme ────────────────────────────────────────────────────────────
WIDTH, HEIGHT = 820, 460
TITLEBAR_H = 30
PAD_X, PAD_Y = 16, 12
LINE_H = 18
FONT_SIZE = 13
SCALE = 2  # supersample for crisp text, then downscale

BG = (30, 31, 34)
TITLEBAR = (44, 46, 51)
TITLEBAR_TXT = (170, 173, 180)
FG = (208, 211, 215)
PROMPT_SYMB = (98, 209, 150)
CURSOR = (208, 211, 215)

GREEN = (87, 200, 122)
YELLOW = (224, 190, 92)
RED = (224, 108, 108)
CYAN = (86, 182, 194)
BLUE = (102, 170, 255)
DIM = (128, 132, 140)
BOLD_W = (236, 238, 240)
MAGENTA = (197, 134, 192)

TRAFFIC = [(255, 95, 86), (255, 189, 46), (39, 201, 63)]


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in (
        "/System/Library/Fonts/Menlo.ttc",
        "/System/Library/Fonts/Monaco.ttf",
        "/System/Library/Fonts/Supplemental/Courier New.ttf",
    ):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


FONT = _load_font(FONT_SIZE * SCALE)
FONT_BOLD = _load_font(FONT_SIZE * SCALE)
TITLE_FONT = _load_font(13 * SCALE)
CHAR_W = FONT.getbbox("M")[2]

VISIBLE_LINES = (HEIGHT - TITLEBAR_H - 2 * PAD_Y) // LINE_H


# ── line model ────────────────────────────────────────────────────────────────
@dataclass
class Span:
    text: str
    color: tuple[int, int, int] = FG
    bold: bool = False


@dataclass
class Line:
    spans: list[Span] = field(default_factory=list)


def L(*spans: Span) -> Line:
    return Line(list(spans))


def S(text: str, color: tuple[int, int, int] = FG, bold: bool = False) -> Span:
    return Span(text, color, bold)


def prompt_line(cmd: str) -> Line:
    return L(S("$ ", PROMPT_SYMB, bold=True), S(cmd, BOLD_W))


# ── frame rendering ───────────────────────────────────────────────────────────
def _draw_titlebar(d: ImageDraw.ImageDraw, title: str) -> None:
    d.rectangle([0, 0, WIDTH * SCALE, TITLEBAR_H * SCALE], fill=TITLEBAR)
    cy = (TITLEBAR_H // 2) * SCALE
    for i, col in enumerate(TRAFFIC):
        cx = (18 + i * 20) * SCALE
        r = 6 * SCALE
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)
    tw = d.textlength(title, font=TITLE_FONT)
    d.text(
        ((WIDTH * SCALE - tw) / 2, (TITLEBAR_H * SCALE - TITLE_FONT.size) / 2 - SCALE),
        title,
        font=TITLE_FONT,
        fill=TITLEBAR_TXT,
    )


def render_frame(
    lines: list[Line], typed: int | None, show_cursor: bool, title: str
) -> Image.Image:
    """Draw the visible buffer. ``typed`` truncates the last line's last span to
    that many characters (typewriter); ``show_cursor`` draws a block cursor."""
    img = Image.new("RGB", (WIDTH * SCALE, HEIGHT * SCALE), BG)
    d = ImageDraw.Draw(img)
    _draw_titlebar(d, title)

    view = lines[-VISIBLE_LINES:]
    y = (TITLEBAR_H + PAD_Y) * SCALE
    for li, line in enumerate(view):
        x = PAD_X * SCALE
        is_last = li == len(view) - 1
        for si, span in enumerate(line.spans):
            text = span.text
            if is_last and typed is not None and si == len(line.spans) - 1:
                text = text[:typed]
            font = FONT_BOLD if span.bold else FONT
            d.text((x, y), text, font=font, fill=span.color)
            x += len(text) * CHAR_W
        if is_last and show_cursor:
            d.rectangle(
                [x, y + 2 * SCALE, x + CHAR_W - SCALE, y + LINE_H * SCALE - 2 * SCALE],
                fill=CURSOR,
            )
        y += LINE_H * SCALE

    return img.resize((WIDTH, HEIGHT), Image.LANCZOS)


# ── timeline builder ──────────────────────────────────────────────────────────
TYPE_MS = 55
CHARS_PER_TICK = 2
CURSOR_BLINK_MS = 380
REVEAL_MS = 55
BLANK_MS = 26


class Builder:
    """Accumulates frames for one GIF. A line whose LAST span holds text can be
    typewritten; everything else is revealed whole."""

    def __init__(self, title: str) -> None:
        self.title = title
        self.buffer: list[Line] = []
        self.frames: list[Image.Image] = []
        self.durations: list[int] = []

    def _frame(self, typed: int | None, cursor: bool, ms: int) -> None:
        self.frames.append(render_frame(self.buffer, typed, cursor, self.title))
        self.durations.append(ms)

    def append(self, line: Line) -> None:
        self.buffer.append(line)

    def typewrite(self, blink_before: bool = True, ms: int = TYPE_MS) -> None:
        full = self.buffer[-1].spans[-1].text
        if blink_before:
            self._frame(0, True, CURSOR_BLINK_MS)
            self._frame(0, False, 200)
        for i in range(CHARS_PER_TICK, len(full) + CHARS_PER_TICK, CHARS_PER_TICK):
            self._frame(min(i, len(full)), True, ms)
        self._frame(len(full), True, 300)

    def cmd(self, command: str) -> None:
        self.append(prompt_line(command))
        self.typewrite(blink_before=True)

    def reveal(self, line: Line) -> None:
        self.append(line)
        self._frame(None, False, BLANK_MS if not line.spans else REVEAL_MS)

    def hold(self, ms: int, cursor: bool = False) -> None:
        self._frame(None, cursor, ms)

    def progress_download(self, label: str, kb: float, steps: int = 22) -> None:
        """Animate a pip-style download bar filling to 100%."""
        self.reveal(L(S("  " + label, DIM)))
        self.append(L(S("", DIM)))  # placeholder for the bar line
        bar_w = 34
        for s in range(steps + 1):
            frac = s / steps
            filled = round(bar_w * frac)
            bar = "━" * filled + "╺" + "━" * max(0, bar_w - filled - 1)
            done = kb * frac
            color = GREEN if frac >= 1.0 else CYAN
            self.buffer[-1] = L(
                S("  ", FG),
                S(bar[:filled], color),
                S(bar[filled:], DIM),
                S(f"  {done:4.1f}/{kb:.1f} kB", DIM),
            )
            self._frame(None, False, 34)

    def end_prompt(self, ms: int = 1500) -> None:
        self.append(L(S("$ ", PROMPT_SYMB, bold=True), S("", BOLD_W)))
        self._frame(0, True, ms)
        self._frame(0, False, 240)

    def save(self, out: Path) -> None:
        self.frames[0].save(
            out,
            save_all=True,
            append_images=self.frames[1:],
            duration=self.durations,
            loop=0,
            optimize=True,
            disposal=2,
        )

    @property
    def total_ms(self) -> int:
        return sum(self.durations)


# ── 1. install.gif ────────────────────────────────────────────────────────────
def build_install() -> Builder:
    b = Builder("atlas — ~/atlas-os — zsh")
    b.cmd("pip install atlas-os")
    b.reveal(L(S("Collecting atlas-os", FG)))
    b.hold(350)
    b.progress_download("Downloading atlas_os-1.2.0-py3-none-any.whl (45 kB)", 45.0, steps=30)
    b.hold(500)
    b.reveal(L(S("Installing collected packages: atlas-os", FG)))
    b.hold(900)
    b.reveal(L(S("Successfully installed atlas-os-1.2.0", GREEN, bold=True)))
    b.hold(1400)
    b.cmd("atlas --version")
    b.reveal(L(S("Atlas OS ", BOLD_W, bold=True), S("v1.2.0", CYAN, bold=True)))
    b.end_prompt(2400)
    return b


# ── 2. setup.gif ──────────────────────────────────────────────────────────────
def build_setup() -> Builder:
    b = Builder("atlas — ~/atlas-os — zsh")
    b.cmd("atlas init")
    b.reveal(L())
    b.reveal(L(S("  ▲  Atlas OS — Interactive Setup", CYAN, bold=True)))
    b.reveal(L())
    # typed input: vault path (pause = user reading the prompt before typing)
    b.append(L(S("  Vault path [~/vault]: ", FG), S("~/Documents/my-vault", BLUE)))
    b.typewrite(blink_before=True, ms=70)
    b.hold(450)
    b.reveal(L(S("  ✓ ", GREEN), S("Created ~/Documents/my-vault", FG)))
    b.reveal(L())
    b.reveal(L(S("  Scanning for LLM backends…", FG)))
    b.hold(1100)
    b.reveal(L(S("  ✓ ", GREEN), S("Found LM Studio at localhost:5555 ", FG), S("(qwen3.5-9b)", DIM)))
    b.hold(350)
    b.reveal(L(S("  ✓ ", GREEN), S("Found Ollama at localhost:11434 ", FG), S("(llama3.2)", DIM)))
    b.reveal(L())
    b.hold(500)
    # typed input: email y/N
    b.append(L(S("  Email notifications? [y/N]: ", FG), S("y", BLUE)))
    b.typewrite(blink_before=True, ms=70)
    b.hold(450)
    b.append(L(S("  SMTP email: ", FG), S("user@example.com", BLUE)))
    b.typewrite(blink_before=True, ms=70)
    b.hold(450)
    b.reveal(L(S("  ✓ ", GREEN), S(".env written", FG)))
    b.reveal(L())
    b.hold(600)
    b.reveal(L(S("  ✓ You're ready! ", GREEN, bold=True), S("Run 'atlas doctor' to verify.", FG)))
    b.end_prompt(2600)
    return b


# ── 3. search.gif ─────────────────────────────────────────────────────────────
def _result(score: str, path: str, heading: str, snippet: str) -> list[Line]:
    return [
        L(S(f"[{score}] ", YELLOW), S(path, BLUE)),
        L(S("      › ", DIM), S(heading, MAGENTA)),
        L(S(f'      {snippet}', DIM)),
        L(),
    ]


def build_search() -> Builder:
    b = Builder("atlas — ~/atlas-os — zsh")
    b.cmd('atlas search "kubernetes deployment strategy"')
    b.reveal(L())
    b.reveal(L(S("Searching ", FG), S("2,451", BOLD_W, bold=True), S(" chunks across ", FG), S("312", BOLD_W, bold=True), S(" files…", FG)))
    b.reveal(L())
    b.hold(1100)
    for line in _result(
        "0.94", "wiki/sources/k8s-rolling-updates.md", "Rolling Update Strategy",
        '"Use maxSurge and maxUnavailable to control…"',
    ):
        b.reveal(line)
    b.hold(1150)
    for line in _result(
        "0.87", "wiki/sources/devops-runbook.md", "Blue-Green Deployments",
        '"Route traffic between two identical environments…"',
    ):
        b.reveal(line)
    b.hold(1150)
    for line in _result(
        "0.82", "wiki/session-logs/2026-05-28.md", "Infrastructure Discussion",
        '"Decided on canary deployments for the…"',
    ):
        b.reveal(line)
    b.hold(900)
    b.reveal(L(S("4 results ", BOLD_W, bold=True), S("(hybrid BM25 + vector, 0.3s)", DIM)))
    b.end_prompt(2600)
    return b


# ── 4. dashboard.gif ──────────────────────────────────────────────────────────
def build_dashboard() -> Builder:
    b = Builder("atlas — ~/atlas-os — zsh")
    b.cmd("atlas dashboard")
    b.reveal(L(S("  ▲  Atlas OS Dashboard", CYAN, bold=True)))
    b.reveal(L(S("Starting on ", FG), S("http://localhost:8501", BLUE), S("…", FG)))
    b.reveal(L())
    b.hold(1100)
    b.reveal(L(S("  ✓ ", GREEN), S("System health: ", FG), S("12 OK", GREEN), S(" · ", DIM), S("0 WARN", DIM), S(" · ", DIM), S("0 FAIL", DIM)))
    b.hold(300)
    b.reveal(L(S("  ✓ ", GREEN), S("Vector store: ", FG), S("2,451", BOLD_W, bold=True), S(" chunks · ", FG), S("312", BOLD_W, bold=True), S(" files", FG)))
    b.hold(300)
    b.reveal(L(S("  ✓ ", GREEN), S("Skills: ", FG), S("8", BOLD_W, bold=True), S(" installed", FG)))
    b.reveal(L())
    b.hold(900)
    b.reveal(L(S("Dashboard ready → ", BOLD_W, bold=True), S("http://localhost:8501", BLUE)))
    b.end_prompt(2800)
    return b


# ── main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    targets = {
        "install.gif": build_install,
        "setup.gif": build_setup,
        "search.gif": build_search,
        "dashboard.gif": build_dashboard,
    }
    for name, build in targets.items():
        b = build()
        out = repo_root / name
        b.save(out)
        print(
            f"{name:<16} {len(b.frames):>4} frames · "
            f"{b.total_ms/1000:>5.1f}s · {out.stat().st_size/1024:>6.0f} KB"
        )


if __name__ == "__main__":
    main()
