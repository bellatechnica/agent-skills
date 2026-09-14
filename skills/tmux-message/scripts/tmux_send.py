#!/usr/bin/env python3
"""Send one non-idempotent message to a structurally clear tmux composer."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
from typing import BinaryIO
import unicodedata
import uuid


CLEAR = "CLEAR"
OCCUPIED = "OCCUPIED"
DIALOG = "DIALOG"
UNKNOWN = "UNKNOWN"
SENT = "SENT"
DELIVERY_UNVERIFIED = "DELIVERY_UNVERIFIED"

EXIT_OCCUPIED = 1
EXIT_DIALOG = 2
EXIT_UNKNOWN = 3
EXIT_DELIVERY_UNVERIFIED = 4
EXIT_USAGE = 64

VERIFY_DELAYS_SECONDS = (0.05, 0.1, 0.2, 0.4, 0.8, 1.6)

_OUTCOME_DECIDED = False

CSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
OSC_RE = re.compile(r"\x1b\].*?(?:\x07|\x1b\\)")
SGR_RE = re.compile(r"\x1b\[([0-9;]*)m")
CODEX_FOOTER_RE = re.compile(r"^  \S.* · \S")
CLAUDE_FOOTER_RE = re.compile(r"^  ⏵⏵ \S")
CLAUDE_SELECTED_PANEL_RE = re.compile(r"^\s*●(?:\s|$)")
CLAUDE_MAIN_SELECTED_RE = re.compile(r"^\s*●\s+main(?:\s|$)")
CLAUDE_AGENT_MESSAGE_RE = re.compile(r"^Message @")
AGY_FOOTER_RE = re.compile(r".*\S · (?:low|medium|high)$", re.IGNORECASE)
CLAUDE_PASTE_PLACEHOLDER_RE = re.compile(
    r"\[(?:Pasted text #\d+(?: \+\d+ lines)?|\.\.\.Truncated text #\d+ \+\d+ lines\.\.\.)\]"
)
CODEX_PASTE_PLACEHOLDER_RE = re.compile(
    r"\[Pasted Content \d+ chars\](?: #\d+)?"
)
OPENCODE_PASTE_PLACEHOLDER_RE = re.compile(r"\[Pasted ~\d+ lines\]")
OPENCODE_HOME_PLACEHOLDERS = frozenset(
    f'Ask anything{ellipsis} "{example}"'
    for ellipsis in ("...", "…")
    for example in (
        "Fix a TODO in the codebase",
        "What is the tech stack of this project?",
        "Fix broken tests",
    )
)
OPENCODE_NORMAL_HINT_RE = re.compile(r"\bctrl\+p\s+commands\b", re.IGNORECASE)
DIALOG_PATTERNS = (
    re.compile(r"\benter to (?:confirm|select|submit)\b.*\besc to (?:cancel|close)\b"),
    re.compile(r"\bpress enter to (?:continue|select)\b"),
    re.compile(r"\benter to select\b"),
    re.compile(r"\bspace to toggle\b.*\benter to confirm\b"),
    re.compile(r"\btab/arrow keys to navigate\b.*\besc to cancel\b"),
    re.compile(r"\bshift\+tab use plan mode\b.*\besc dismiss\b"),
    re.compile(r"\btype a name and press enter\b"),
)


class UsageError(Exception):
    """The command line does not satisfy the public invocation contract."""


class SignalInterruption(Exception):
    """A catchable process signal interrupted delivery."""


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise UsageError(message)

    def exit(self, status: int = 0, message: str | None = None) -> None:
        raise UsageError(message.strip() if message else "help requested")


@dataclass(frozen=True)
class PaneIdentity:
    pane_id: str
    pane_pid: str
    pane_width: int
    socket_path: str
    server_pid: str
    requested_target: str


@dataclass(frozen=True)
class Composer:
    client: str
    text: str
    has_dim_text: bool
    has_non_dim_text: bool


@dataclass(frozen=True)
class CaptureResult:
    state: str
    detail_class: str
    detail: str
    composer: Composer | None


@dataclass(frozen=True)
class OpenCodeRegion:
    top: int
    bottom: int
    left: int
    right: int


@dataclass(frozen=True)
class ClaudeRegion:
    top: int
    bottom: int
    trailing_panel: tuple[str, ...]


def _visible(raw: str) -> str:
    return CSI_RE.sub("", OSC_RE.sub("", raw))


def _visible_with_style(
    raw: str,
) -> list[tuple[str, bool, tuple[int, ...] | None]]:
    """Return visible characters with their SGR dim and foreground states."""
    result: list[tuple[str, bool, tuple[int, ...] | None]] = []
    dim = False
    foreground: tuple[int, ...] | None = None
    position = 0
    escape_re = re.compile(r"\x1b\].*?(?:\x07|\x1b\\)|\x1b\[[0-?]*[ -/]*[@-~]")
    for match in escape_re.finditer(raw):
        result.extend(
            (char, dim, foreground) for char in raw[position : match.start()]
        )
        sgr = SGR_RE.fullmatch(match.group())
        if sgr:
            params = [int(value) if value else 0 for value in sgr.group(1).split(";")]
            index = 0
            while index < len(params):
                code = params[index]
                if code in (38, 48, 58) and index + 1 < len(params):
                    color_mode = params[index + 1]
                    if color_mode == 5 and index + 2 < len(params):
                        if code == 38:
                            foreground = (38, 5, params[index + 2])
                        index += 3
                        continue
                    if color_mode == 2 and index + 4 < len(params):
                        if code == 38:
                            foreground = (38, 2, *params[index + 2 : index + 5])
                        index += 5
                        continue
                if code == 0:
                    dim = False
                    foreground = None
                elif code == 2:
                    dim = True
                elif code == 22:
                    dim = False
                elif 30 <= code <= 37 or 90 <= code <= 97:
                    foreground = (code,)
                elif code == 39:
                    foreground = None
                index += 1
        position = match.end()
    result.extend((char, dim, foreground) for char in raw[position:])
    return result


def _visible_with_dim(raw: str) -> list[tuple[str, bool]]:
    """Return visible characters paired with their SGR-dim state."""
    return [(char, dim) for char, dim, _foreground in _visible_with_style(raw)]


def _is_dialog(lines: list[str]) -> bool:
    visible_nonblank = [_visible(line).strip().casefold() for line in lines]
    nonblank = [line for line in visible_nonblank if line]
    if not nonblank:
        return False
    # These patterns describe the dialog footer, which is the unique bottommost
    # nonblank row. Looking earlier would let stale transcript text claim the UI.
    footer = nonblank[-1]
    return any(pattern.search(footer) for pattern in DIALOG_PATTERNS)


def _is_full_width_border(raw_line: str, pane_width: int | None) -> bool:
    visible = _visible(raw_line).rstrip()
    if not visible.startswith(("────", "━━━━")):
        return False
    if pane_width is None:
        return len(visible) >= 8
    return len(visible) >= pane_width - 1


def _is_plain_full_width_border(raw_line: str, pane_width: int | None) -> bool:
    visible = _visible(raw_line).rstrip()
    return _is_full_width_border(raw_line, pane_width) and set(visible) <= {"─", "━"}


def _content(annotated: list[tuple[str, bool]]) -> tuple[str, bool, bool]:
    text = "".join(char for char, _ in annotated)
    has_dim = any(dim for char, dim in annotated if not char.isspace())
    has_non_dim = any(not dim for char, dim in annotated if not char.isspace())
    return text, has_dim, has_non_dim


def _remove_prompt_separator(
    raw_line: str,
    prompt: str,
    *,
    trim_display_padding: bool = False,
) -> tuple[str, bool, bool] | None:
    annotated = _visible_with_dim(raw_line)
    if not annotated or annotated[0][0] != prompt:
        return None
    remainder = annotated[1:]
    if remainder and remainder[0][0] in (" ", "\u00a0"):
        remainder = remainder[1:]
    text, has_dim, has_non_dim = _content(remainder)
    if trim_display_padding:
        text = text.rstrip(" ")
    return text, has_dim, has_non_dim


def _continuation(
    raw_line: str,
    *,
    trim_display_padding: bool = False,
) -> tuple[str, bool, bool] | None:
    annotated = _visible_with_dim(raw_line)
    visible = "".join(char for char, _ in annotated)
    # Both clients render an empty logical continuation as one or more blank
    # styled cells even without capture-pane -N. The cells carry no recoverable
    # input-space information, so only a wholly blank row maps to an empty line.
    if not visible.strip():
        return "", False, False
    if not visible.startswith("  "):
        return None
    text, has_dim, has_non_dim = _content(annotated[2:])
    if trim_display_padding:
        text = text.rstrip(" ")
    return text, has_dim, has_non_dim


def _claude_region(
    lines: list[str], pane_width: int | None
) -> ClaudeRegion | None:
    bottom = None
    for index in range(len(lines) - 1, -1, -1):
        if _is_plain_full_width_border(lines[index], pane_width):
            bottom = index
            break
    if bottom is None:
        return None

    trailing_nonblank = [
        _visible(line).rstrip() for line in lines[bottom + 1 :] if _visible(line).strip()
    ]
    if not trailing_nonblank or not CLAUDE_FOOTER_RE.match(trailing_nonblank[0]):
        return None

    top = None
    for index in range(bottom - 1, -1, -1):
        if _is_full_width_border(lines[index], pane_width):
            top = index
            break
    if top is None:
        return None

    return ClaudeRegion(top, bottom, tuple(trailing_nonblank[1:]))


def _claude_composer(
    lines: list[str],
    pane_width: int | None,
    cursor_y: int | None = None,
) -> Composer | None:
    bounds = _claude_region(lines, pane_width)
    if bounds is None:
        return None
    if bounds.trailing_panel:
        if not (cursor_y is not None and bounds.top < cursor_y < bounds.bottom):
            return None
        selected_rows = [
            row for row in bounds.trailing_panel if CLAUDE_SELECTED_PANEL_RE.match(row)
        ]
        if len(selected_rows) != 1 or not CLAUDE_MAIN_SELECTED_RE.match(
            selected_rows[0]
        ):
            return None

    region = lines[bounds.top + 1 : bounds.bottom]
    prompt_indices = [
        index for index, line in enumerate(region) if _visible(line).startswith("❯")
    ]
    if prompt_indices != [0]:
        return None

    first = _remove_prompt_separator(
        region[0],
        "❯",
        trim_display_padding=True,
    )
    if first is None:
        return None
    text_lines = [first[0]]
    has_dim = first[1]
    has_non_dim = first[2]
    for line in region[1:]:
        continuation = _continuation(line, trim_display_padding=True)
        if continuation is None:
            return None
        text_lines.append(continuation[0])
        has_dim = has_dim or continuation[1]
        has_non_dim = has_non_dim or continuation[2]
    text = "\n".join(text_lines)
    if bounds.trailing_panel and CLAUDE_AGENT_MESSAGE_RE.match(text):
        return None
    return Composer("claude", text, has_dim, has_non_dim)


def _agy_composer(lines: list[str], pane_width: int | None) -> Composer | None:
    bottom = None
    for index in range(len(lines) - 1, -1, -1):
        if _is_plain_full_width_border(lines[index], pane_width):
            bottom = index
            break
    if bottom is None:
        return None

    trailing_nonblank = [
        _visible(line).rstrip() for line in lines[bottom + 1 :] if _visible(line).strip()
    ]
    if len(trailing_nonblank) != 1 or AGY_FOOTER_RE.fullmatch(
        trailing_nonblank[0]
    ) is None:
        return None

    top = None
    for index in range(bottom - 1, -1, -1):
        if _is_plain_full_width_border(lines[index], pane_width):
            top = index
            break
    if top is None:
        return None

    region = lines[top + 1 : bottom]
    prompt_indices = [
        index for index, line in enumerate(region) if _visible(line).startswith(">")
    ]
    if prompt_indices != [0]:
        return None

    first = _remove_prompt_separator(
        region[0],
        ">",
        trim_display_padding=True,
    )
    if first is None:
        return None
    text_lines = [first[0]]
    has_dim = first[1]
    has_non_dim = first[2]
    for line in region[1:]:
        continuation = _continuation(line, trim_display_padding=True)
        if continuation is None:
            return None
        text_lines.append(continuation[0])
        has_dim = has_dim or continuation[1]
        has_non_dim = has_non_dim or continuation[2]
    return Composer("agy", "\n".join(text_lines), has_dim, has_non_dim)


def _is_codex_footer(raw_line: str, pane_width: int | None) -> bool:
    visible = _visible(raw_line)
    if CODEX_FOOTER_RE.match(visible.rstrip()):
        return True
    if pane_width is None or not visible.startswith("  "):
        return False
    annotated = _visible_with_dim(raw_line)
    nonblank = [(char, dim) for char, dim in annotated if not char.isspace()]
    # Codex 0.153.3 renders a configurable status line across the footer's
    # pane-width-minus-indent area while a draft is present. Its text is not a
    # stable identifier, so require the renderer's full-width, all-dim shape.
    return (
        len(visible) >= pane_width - 2
        and bool(nonblank)
        and all(dim for _char, dim in nonblank)
    )


def _codex_composer(
    lines: list[str], pane_width: int | None
) -> Composer | None:
    footer = None
    for index in range(len(lines) - 1, -1, -1):
        if _visible(lines[index]).strip():
            footer = index
            break
    if footer is None or not _is_codex_footer(lines[footer], pane_width):
        return None

    separator = footer - 1
    if separator < 0 or _visible(lines[separator]).strip():
        return None

    prompt_indices = [
        index for index in range(separator) if _visible(lines[index]).startswith("›")
    ]
    if not prompt_indices:
        return None
    prompt = prompt_indices[-1]
    region = lines[prompt:separator]
    if any(_visible(line).startswith("›") for line in region[1:]):
        return None

    first = _remove_prompt_separator(region[0], "›")
    if first is None:
        return None
    text_lines = [first[0]]
    has_dim = first[1]
    has_non_dim = first[2]
    for line in region[1:]:
        continuation = _continuation(line)
        if continuation is None:
            return None
        text_lines.append(continuation[0])
        has_dim = has_dim or continuation[1]
        has_non_dim = has_non_dim or continuation[2]
    return Composer("codex", "\n".join(text_lines), has_dim, has_non_dim)


def _opencode_region(lines: list[str]) -> OpenCodeRegion | None:
    for bottom in range(len(lines) - 1, -1, -1):
        visible = _visible(lines[bottom]).rstrip()
        stripped = visible.lstrip(" ")
        if (
            len(stripped) < 8
            or not stripped.startswith("╹")
            or any(char not in "╹▀" for char in stripped)
        ):
            continue
        left = len(visible) - len(stripped)
        top = bottom - 1
        while top >= 0:
            row = _visible(lines[top])
            if (
                len(row) <= left
                or row[:left].strip()
                or row[left] != "┃"
            ):
                break
            top -= 1
        top += 1
        if bottom - top >= 4:
            return OpenCodeRegion(top, bottom, left, left + len(stripped))
    return None


def _foreground_for_substring(
    raw_line: str, substring: str
) -> tuple[int, ...] | None:
    styled = _visible_with_style(raw_line)
    visible = "".join(char for char, _dim, _foreground in styled)
    start = visible.find(substring)
    if start < 0:
        return None
    foregrounds = {
        foreground
        for char, _dim, foreground in styled[start : start + len(substring)]
        if not char.isspace()
    }
    if len(foregrounds) != 1:
        return None
    [foreground] = foregrounds
    return foreground


def _opencode_composer(
    lines: list[str],
    cursor_x: int | None,
    cursor_y: int | None,
) -> Composer | None:
    region = _opencode_region(lines)
    if region is None or cursor_x is None or cursor_y is None:
        return None
    input_left = region.left + 3
    input_right = region.right - 2
    input_top = region.top + 1
    input_bottom = region.bottom - 1
    if not (
        input_left <= cursor_x <= input_right
        and input_top <= cursor_y < input_bottom
    ):
        return None

    text_lines: list[str] = []
    has_dim = False
    has_non_dim = False
    content_foregrounds: set[tuple[int, ...] | None] = set()
    for index in range(input_top, input_bottom):
        styled = _visible_with_style(lines[index])[input_left:input_right]
        text, row_dim, row_non_dim = _content(
            [(char, dim) for char, dim, _foreground in styled]
        )
        text_lines.append(text.rstrip(" "))
        has_dim = has_dim or row_dim
        has_non_dim = has_non_dim or row_non_dim
        content_foregrounds.update(
            foreground
            for char, _dim, foreground in styled
            if not char.isspace()
        )
    while text_lines and not text_lines[-1]:
        text_lines.pop()
    text = "\n".join(text_lines)

    hint_line = lines[region.bottom + 1] if region.bottom + 1 < len(lines) else ""
    if OPENCODE_NORMAL_HINT_RE.search(_visible(hint_line)) is None:
        return None
    muted_foreground = _foreground_for_substring(hint_line, "commands")
    if (
        text in OPENCODE_HOME_PLACEHOLDERS
        and cursor_x == input_left
        and cursor_y == input_top
        and muted_foreground is not None
        and content_foregrounds == {muted_foreground}
    ):
        return Composer("opencode", text, True, False)
    return Composer("opencode", text, has_dim, has_non_dim)


def _opencode_dialog(
    lines: list[str], cursor_x: int | None, cursor_y: int | None
) -> bool:
    region = _opencode_region(lines)
    if region is None or cursor_x is None or cursor_y is None:
        return False
    return _opencode_composer(lines, cursor_x, cursor_y) is None


def _composer(
    lines: list[str],
    pane_width: int | None,
    cursor_x: int | None = None,
    cursor_y: int | None = None,
) -> Composer | None:
    return (
        _claude_composer(lines, pane_width, cursor_y)
        or _agy_composer(lines, pane_width)
        or _codex_composer(lines, pane_width)
        or _opencode_composer(lines, cursor_x, cursor_y)
    )


def _native_paste_placeholder_pattern(composer: Composer) -> re.Pattern[str]:
    if composer.client in ("claude", "agy"):
        return CLAUDE_PASTE_PLACEHOLDER_RE
    if composer.client == "opencode":
        return OPENCODE_PASTE_PLACEHOLDER_RE
    return CODEX_PASTE_PLACEHOLDER_RE


def _contains_native_paste_placeholder(composer: Composer) -> bool:
    return _native_paste_placeholder_pattern(composer).search(composer.text) is not None


def classify_capture(
    raw: str,
    pane_width: int | None = None,
    cursor_x: int | None = None,
    cursor_y: int | None = None,
) -> str:
    """Classify an ANSI-preserving capture without exposing its contents."""
    lines = raw.splitlines()
    if not lines:
        return UNKNOWN
    if _is_dialog(lines):
        return DIALOG
    if _opencode_dialog(lines, cursor_x, cursor_y):
        return DIALOG
    composer = _composer(lines, pane_width, cursor_x, cursor_y)
    if composer is None:
        return UNKNOWN
    if not composer.text.strip():
        return CLEAR
    if _contains_native_paste_placeholder(composer):
        return OCCUPIED
    if composer.has_dim_text and not composer.has_non_dim_text:
        return CLEAR
    return OCCUPIED


def _tmux(
    *arguments: str, input_text: str | None = None
) -> subprocess.CompletedProcess[str]:
    command = ["tmux", *arguments]
    try:
        return subprocess.run(
            command,
            check=False,
            input=input_text,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
    except OSError as error:
        return subprocess.CompletedProcess(command, 127, "", str(error))


def _server_hint() -> str:
    tmux_environment = os.environ.get("TMUX", "")
    return tmux_environment.split(",", 1)[0] or "default"


def resolve_target(target: str) -> tuple[PaneIdentity | None, str, str]:
    server = _tmux("list-sessions", "-F", "#{pid}\t#{socket_path}")
    if server.returncode != 0:
        return None, "server", server.stderr.strip() or "tmux server probe failed"

    panes = _tmux(
        "list-panes",
        "-a",
        "-F",
        "#{session_name}\t#{window_name}\t#{window_index}\t#{pane_index}\t"
        "#{pane_id}\t#{pane_pid}\t#{pane_width}\t#{socket_path}\t#{pid}\t"
        "#{window_panes}",
    )
    if panes.returncode != 0:
        return None, "target", panes.stderr.strip() or "tmux pane enumeration failed"

    matches: list[PaneIdentity] = []
    for line in panes.stdout.splitlines():
        fields = line.split("\t")
        if len(fields) != 10:
            return None, "target", "tmux pane enumeration returned an invalid identity"
        (
            session_name,
            window_name,
            window_index,
            pane_index,
            pane_id,
            pane_pid,
            pane_width_text,
            socket_path,
            server_pid,
            window_panes_text,
        ) = fields
        try:
            pane_width = int(pane_width_text)
            window_panes = int(window_panes_text)
        except ValueError:
            return None, "target", "tmux pane enumeration returned invalid numbers"
        candidates = {
            pane_id,
            f"{session_name}:{window_name}.{pane_index}",
            f"{session_name}:{window_index}.{pane_index}",
        }
        if window_panes == 1:
            candidates.update(
                {
                    f"{session_name}:{window_name}",
                    f"{session_name}:{window_index}",
                }
            )
        if target in candidates:
            matches.append(
                PaneIdentity(
                    pane_id,
                    pane_pid,
                    pane_width,
                    socket_path,
                    server_pid,
                    target,
                )
            )

    if not matches:
        return None, "target", "no pane has that exact address"
    if len(matches) != 1:
        return None, "target", "the exact address is ambiguous"
    return matches[0], "", ""


def capture_target(pane: PaneIdentity) -> CaptureResult:
    capture = _tmux("capture-pane", "-p", "-e", "-J", "-t", pane.pane_id)
    if capture.returncode != 0:
        return CaptureResult(
            UNKNOWN,
            "target",
            capture.stderr.strip() or "resolved pane vanished before capture",
            None,
        )
    lines = capture.stdout.splitlines()
    cursor_x = None
    cursor_y = None
    claude_region = _claude_region(lines, pane.pane_width)
    if _opencode_region(lines) is not None or (
        claude_region is not None and claude_region.trailing_panel
    ):
        cursor = _tmux(
            "display-message",
            "-p",
            "-t",
            pane.pane_id,
            "#{cursor_x}\t#{cursor_y}",
        )
        if cursor.returncode != 0:
            return CaptureResult(
                UNKNOWN,
                "target",
                cursor.stderr.strip() or "resolved pane vanished before cursor query",
                None,
            )
        fields = cursor.stdout.strip().split("\t")
        if len(fields) != 2:
            return CaptureResult(UNKNOWN, "layout", "invalid cursor position", None)
        try:
            cursor_x, cursor_y = (int(field) for field in fields)
        except ValueError:
            return CaptureResult(UNKNOWN, "layout", "invalid cursor position", None)
    state = classify_capture(capture.stdout, pane.pane_width, cursor_x, cursor_y)
    if state == UNKNOWN:
        return CaptureResult(UNKNOWN, "layout", "pane shape is not recognized", None)
    return CaptureResult(
        state,
        "",
        "",
        _composer(lines, pane.pane_width, cursor_x, cursor_y),
    )


def _paste_processed(result: CaptureResult, before: Composer | None) -> bool:
    composer = result.composer
    if composer is None or not composer.text:
        return False
    if result.state == OCCUPIED:
        return True
    return composer != before and _is_native_paste_placeholder(composer)


def _is_native_paste_placeholder(composer: Composer) -> bool:
    return _native_paste_placeholder_pattern(composer).fullmatch(composer.text) is not None


def _submit_cleared(result: CaptureResult, processed: CaptureResult) -> bool:
    composer = result.composer
    return (
        result.state == CLEAR
        and composer is not None
        and composer != processed.composer
        and not _is_native_paste_placeholder(composer)
    )


def _wait_for_processed_paste(
    pane: PaneIdentity,
    before: Composer | None,
    *,
    sleep=time.sleep,
) -> CaptureResult:
    latest = CaptureResult(UNKNOWN, "layout", "verification did not run", None)
    for delay in VERIFY_DELAYS_SECONDS:
        sleep(delay)
        latest = capture_target(pane)
        if _paste_processed(latest, before):
            return latest
    return latest


def _wait_for_clear(
    pane: PaneIdentity,
    processed: CaptureResult,
    *,
    sleep=time.sleep,
) -> CaptureResult:
    latest = CaptureResult(UNKNOWN, "layout", "verification did not run", None)
    for delay in VERIFY_DELAYS_SECONDS:
        sleep(delay)
        latest = capture_target(pane)
        if _submit_cleared(latest, processed):
            return latest
    return latest


def _validate_message(message: str) -> None:
    if not message.strip():
        raise UsageError("message must contain non-whitespace text")
    if not any(
        not char.isspace() and unicodedata.category(char) != "Cf"
        for char in message
    ):
        raise UsageError("message must contain visible text")
    if any(char != "\n" and unicodedata.category(char) == "Cc" for char in message):
        raise UsageError("message contains a control character other than LF")


def _emit_unknown(
    kind: str,
    target: str,
    detail: str,
    socket_path: str | None = None,
) -> int:
    _begin_outcome()
    socket = socket_path or _server_hint()
    explanations = {
        "server": "tmux server or socket could not be reached",
        "target": "tmux answered, but the target pane could not be resolved",
        "layout": "pane shape is not recognized",
        "buffer": "tmux could not prepare the message buffer",
        "interrupted": "the sender was interrupted before paste was issued",
        "internal": "the sender failed before paste was issued",
    }
    explanation = explanations.get(kind, "the sender could not proceed safely")
    suffix = f"; detail: {detail}" if detail else ""
    print(
        f"{UNKNOWN} {kind}: {explanation}; nothing sent "
        f"(target {target}; socket {socket}){suffix}",
        file=sys.stderr,
    )
    return _emit_token(f"{UNKNOWN} {kind}", EXIT_UNKNOWN)


def _emit_unverified(
    stage: str,
    pane: PaneIdentity | None,
    target: str,
    detail: str = "",
) -> int:
    _begin_outcome()
    suffix = f"; detail: {detail}" if detail else ""
    if pane is None:
        identity = f"target {target}; socket {_server_hint()}"
    else:
        identity = f"target {target}; pane {pane.pane_id}; socket {pane.socket_path}"
    print(
        f"{DELIVERY_UNVERIFIED} {stage}: delivery state is uncertain; do not retry "
        f"automatically ({identity}){suffix}",
        file=sys.stderr,
    )
    return _emit_token(
        f"{DELIVERY_UNVERIFIED} {stage}", EXIT_DELIVERY_UNVERIFIED
    )


def _emit_token(token: str, exit_code: int) -> int:
    _begin_outcome()
    print(token, flush=True)
    return exit_code


def _begin_outcome() -> None:
    global _OUTCOME_DECIDED
    _OUTCOME_DECIDED = True


def send_message(
    target: str,
    message_file: Path | None = None,
    *,
    read_stdin: bool = False,
    shell_safe_text: str | None = None,
    stdin: BinaryIO | None = None,
) -> int:
    global _OUTCOME_DECIDED
    _OUTCOME_DECIDED = False
    pane: PaneIdentity | None = None
    buffer_name: str | None = None
    paste_issued = False
    enter_issued = False
    try:
        source_count = sum(
            (message_file is not None, read_stdin, shell_safe_text is not None)
        )
        if source_count != 1:
            raise UsageError("choose exactly one message source")
        try:
            if read_stdin:
                input_stream = stdin if stdin is not None else sys.stdin.buffer
                message_bytes = input_stream.read()
                message = message_bytes.decode("utf-8")
            elif shell_safe_text is not None:
                message = shell_safe_text
            else:
                assert message_file is not None
                if not message_file.is_file():
                    raise UsageError(
                        f"message file is not a regular file: {message_file}"
                    )
                message = message_file.read_bytes().decode("utf-8")
        except UsageError:
            raise
        except (OSError, UnicodeError) as error:
            raise UsageError(
                f"could not read UTF-8 message source: {error}"
            ) from error

        _validate_message(message)

        pane, failure_class, detail = resolve_target(target)
        if pane is None:
            return _emit_unknown(failure_class, target, detail)

        initial = capture_target(pane)
        if initial.state == OCCUPIED:
            _begin_outcome()
            print(
                f"{OCCUPIED}: target composer contains unsubmitted text; nothing sent. "
                "Messages are not assumed idempotent: do not directly inspect "
                "and then retry an ordinary message "
                f"(target {target}; pane {pane.pane_id})",
                file=sys.stderr,
            )
            return _emit_token(OCCUPIED, EXIT_OCCUPIED)
        if initial.state == DIALOG:
            _begin_outcome()
            print(
                f"{DIALOG}: target pane is showing a dialog; nothing sent "
                f"(target {target}; pane {pane.pane_id})",
                file=sys.stderr,
            )
            return _emit_token(DIALOG, EXIT_DIALOG)
        if initial.state == UNKNOWN:
            return _emit_unknown(
                initial.detail_class or "layout",
                target,
                initial.detail,
                pane.socket_path,
            )

        buffer_name = f"tmux-message-{os.getpid()}-{uuid.uuid4().hex}"
        load = _tmux("load-buffer", "-b", buffer_name, "-", input_text=message)
        if load.returncode != 0:
            return _emit_unknown("buffer", target, load.stderr.strip(), pane.socket_path)

        paste_issued = True
        paste = _tmux(
            "paste-buffer",
            "-p",
            "-r",
            "-d",
            "-b",
            buffer_name,
            "-t",
            pane.pane_id,
        )
        if paste.returncode != 0:
            _tmux("delete-buffer", "-b", buffer_name)
            buffer_name = None
            return _emit_unverified("paste-failed", pane, target, paste.stderr.strip())
        buffer_name = None

        observed = _wait_for_processed_paste(pane, initial.composer)
        if not _paste_processed(observed, initial.composer):
            return _emit_unverified(
                "paste-not-observed", pane, target, observed.detail
            )

        enter_issued = True
        submit = _tmux("send-keys", "-t", pane.pane_id, "Enter")
        if submit.returncode != 0:
            return _emit_unverified("enter-failed", pane, target, submit.stderr.strip())

        cleared = _wait_for_clear(pane, observed)
        if not _submit_cleared(cleared, observed):
            return _emit_unverified("not-cleared", pane, target, cleared.detail)
        return _emit_token(SENT, 0)
    except UsageError:
        raise
    except (KeyboardInterrupt, SignalInterruption) as error:
        _begin_outcome()
        if buffer_name is not None:
            _tmux("delete-buffer", "-b", buffer_name)
        if paste_issued:
            stage = "interrupted-after-enter" if enter_issued else "interrupted-before-enter"
            return _emit_unverified(stage, pane, target, type(error).__name__)
        return _emit_unknown("interrupted", target, type(error).__name__)
    except Exception as error:
        _begin_outcome()
        if buffer_name is not None:
            _tmux("delete-buffer", "-b", buffer_name)
        if paste_issued:
            return _emit_unverified("internal-error", pane, target, type(error).__name__)
        return _emit_unknown("internal", target, type(error).__name__)


def _parser() -> Parser:
    parser = Parser(
        description="Send one non-idempotent message only through a verified clear composer.",
        allow_abbrev=False,
    )
    parser.add_argument("target", help="tmux target, such as session:window.pane")
    sources = parser.add_mutually_exclusive_group(required=True)
    sources.add_argument("--file", type=Path, help="read exact UTF-8 from a file")
    sources.add_argument("--stdin", action="store_true", help="read exact UTF-8 from stdin")
    sources.add_argument(
        "--shell-safe-text",
        help="use a non-sensitive message the caller has judged shell-safe",
    )
    return parser


def _raise_signal(signal_number: int, _frame: object) -> None:
    if _OUTCOME_DECIDED:
        return
    raise SignalInterruption(signal_number)


def main(argv: list[str] | None = None) -> int:
    previous_handlers: dict[signal.Signals, object] = {}
    try:
        args = _parser().parse_args(argv)
        for signal_number in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            previous_handlers[signal_number] = signal.getsignal(signal_number)
            signal.signal(signal_number, _raise_signal)
        return send_message(
            args.target,
            args.file,
            read_stdin=args.stdin,
            shell_safe_text=args.shell_safe_text,
        )
    except UsageError as error:
        print(f"usage error: {error}", file=sys.stderr)
        return EXIT_USAGE
    finally:
        for signal_number, handler in previous_handlers.items():
            signal.signal(signal_number, handler)


if __name__ == "__main__":
    raise SystemExit(main())
