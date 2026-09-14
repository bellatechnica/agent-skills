#!/usr/bin/env python3
"""Classify a tmux agent composer and send only when it is clear."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid


CLEAR = "CLEAR"
OCCUPIED = "OCCUPIED"
DIALOG = "DIALOG"
UNKNOWN = "UNKNOWN"
SENT = "SENT"
DELIVERY_UNVERIFIED = "DELIVERY_UNVERIFIED"

EXIT_BY_STATE = {CLEAR: 0, OCCUPIED: 1, DIALOG: 2, UNKNOWN: 3}
EXIT_DELIVERY_FAILED = 4
EXIT_USAGE = 64

VERIFY_WINDOW_SECONDS = 3.15
INITIAL_VERIFY_DELAY_SECONDS = 0.05

PROMPTS = ("❯", "›")
KNOWN_EMPTY_PLACEHOLDERS = (
    re.compile(r'^Ask Codex to do anything$'),
    re.compile(r'^Try ".*\.\.\."$'),
    re.compile(r'^Press up to edit queued messages$'),
    re.compile(r'^Use /skills to list available skills$'),
)

CSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
OSC_RE = re.compile(r"\x1b\].*?(?:\x07|\x1b\\)")
SGR_RE = re.compile(r"\x1b\[([0-9;]*)m")


def _visible(raw: str) -> str:
    return CSI_RE.sub("", OSC_RE.sub("", raw))


def _visible_with_dim(raw: str) -> list[tuple[str, bool]]:
    """Return visible characters paired with their SGR-dim state."""
    result: list[tuple[str, bool]] = []
    dim = False
    position = 0
    for match in re.finditer(r"\x1b\].*?(?:\x07|\x1b\\)|\x1b\[[0-?]*[ -/]*[@-~]", raw):
        result.extend((char, dim) for char in raw[position : match.start()])
        sequence = match.group()
        sgr = SGR_RE.fullmatch(sequence)
        if sgr:
            params = [int(value) if value else 0 for value in sgr.group(1).split(";")]
            index = 0
            while index < len(params):
                code = params[index]
                if code in (38, 48, 58) and index + 1 < len(params):
                    color_mode = params[index + 1]
                    if color_mode == 5:
                        index += 3
                        continue
                    if color_mode == 2:
                        index += 5
                        continue
                if code == 0:
                    dim = False
                elif code == 2:
                    dim = True
                elif code == 22:
                    dim = False
                index += 1
        position = match.end()
    result.extend((char, dim) for char in raw[position:])
    return result


def _is_dialog(lines: list[str]) -> bool:
    nonblank = [_visible(line).strip() for line in lines if _visible(line).strip()]
    footer = nonblank[-4:]
    for line in footer:
        lowered = line.casefold()
        if re.match(r"^enter to (confirm|select)\b", lowered):
            return True
        if re.match(r"^press enter to continue\b", lowered):
            return True
        if "tab/arrow keys to navigate" in lowered and "esc to cancel" in lowered:
            return True
        if "shift+tab use plan mode" in lowered and "esc dismiss" in lowered:
            return True
    return False


def _is_horizontal_border(raw_line: str) -> bool:
    return _visible(raw_line).strip().startswith("────────")


def _is_claude_composer(lines: list[str], prompt_index: int) -> bool:
    previous = prompt_index - 1
    while previous >= 0 and not _visible(lines[previous]).strip():
        previous -= 1
    if previous < 0 or not _is_horizontal_border(lines[previous]):
        return False
    return any(_is_horizontal_border(line) for line in lines[prompt_index + 1 :])


def _prompt_candidate(lines: list[str]) -> tuple[int, str] | None:
    for index in range(len(lines) - 1, -1, -1):
        visible = _visible(lines[index])
        left_trimmed = visible.lstrip(" ")
        indentation = len(visible) - len(left_trimmed)
        if indentation > 2 or not left_trimmed.startswith(PROMPTS):
            continue
        if left_trimmed.startswith("❯") and not _is_claude_composer(lines, index):
            continue
        if indentation <= 2:
            return index, lines[index]
    return None


def _active_without_composer(lines: list[str]) -> bool:
    tail = [_visible(line).strip().casefold() for line in lines if _visible(line).strip()][-6:]
    return any(
        (line.startswith(("⏵", "⏸")) and "esc to interrupt" in line)
        or (line.startswith("• working") and "esc to interrupt" in line)
        for line in tail
    )


def _remainder_after_prompt(raw_line: str) -> tuple[str, list[tuple[str, bool]]]:
    annotated = _visible_with_dim(raw_line)
    for index, (char, _) in enumerate(annotated):
        if char in PROMPTS:
            remainder = annotated[index + 1 :]
            return "".join(char for char, _ in remainder).strip(), remainder
    return "", []


def _exact_remainder_after_prompt(raw_line: str) -> str | None:
    annotated = _visible_with_dim(raw_line)
    for index, (char, _) in enumerate(annotated):
        if char not in PROMPTS:
            continue
        remainder = "".join(value for value, _ in annotated[index + 1 :])
        if remainder.startswith((" ", "\u00a0")):
            remainder = remainder[1:]
        return remainder
    return None


def _known_empty_placeholder(text: str) -> bool:
    return any(pattern.fullmatch(text) for pattern in KNOWN_EMPTY_PLACEHOLDERS)


def classify_capture(raw: str) -> str:
    """Classify an ANSI-preserving ``tmux capture-pane -pe`` result."""
    lines = raw.splitlines()
    if not lines:
        return UNKNOWN
    if _is_dialog(lines):
        return DIALOG

    candidate = _prompt_candidate(lines)
    if candidate is None:
        if _active_without_composer(lines):
            return CLEAR
        return UNKNOWN
    prompt_index, prompt_line = candidate
    remainder, annotated = _remainder_after_prompt(prompt_line)

    if remainder:
        nonspace = [(char, dim) for char, dim in annotated if not char.isspace()]
        if nonspace and all(dim for _, dim in nonspace):
            return CLEAR
        if _known_empty_placeholder(remainder):
            return CLEAR
        return OCCUPIED

    # A leading newline can leave the prompt row empty while draft text occupies
    # a following row. Stop at the composer's lower border; anything visible
    # before it is user input and therefore occupied.
    for line in lines[prompt_index + 1 :]:
        visible = _visible(line).strip()
        if not visible:
            continue
        if set(visible) <= {"─", "━", "─", " ", "-"}:
            break
        if re.match(r"^(gpt-|⏵|⏸|\? for shortcuts)", visible, re.IGNORECASE):
            break
        return OCCUPIED
    return CLEAR


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
        )
    except OSError as error:
        return subprocess.CompletedProcess(command, 127, "", str(error))


def _capture_target(target: str) -> tuple[str, str, str]:
    capture = _tmux("capture-pane", "-p", "-e", "-J", "-t", target)
    if capture.returncode != 0:
        detail = capture.stderr.strip() or "tmux capture-pane failed"
        return UNKNOWN, detail, ""
    return classify_capture(capture.stdout), "", capture.stdout


def classify_target(target: str) -> tuple[str, str]:
    state, detail, _ = _capture_target(target)
    return state, detail


def _wait_for_clear(
    target: str,
    *,
    clock=time.monotonic,
    sleep=time.sleep,
) -> tuple[str, str, str]:
    deadline = clock() + VERIFY_WINDOW_SECONDS
    delay = INITIAL_VERIFY_DELAY_SECONDS
    result = (UNKNOWN, "verification did not run", "")
    while True:
        remaining = deadline - clock()
        if remaining <= 0:
            return result
        sleep(min(delay, remaining))
        result = _capture_target(target)
        if result[0] == CLEAR:
            return result
        delay *= 2


def _composer_text(raw: str) -> str | None:
    lines = raw.splitlines()
    candidate = _prompt_candidate(lines)
    if candidate is None:
        return None
    prompt_index, prompt_line = candidate
    first_line = _exact_remainder_after_prompt(prompt_line)
    if first_line is None:
        return None
    prompt_glyph = _visible(prompt_line).lstrip(" ")[0]

    if prompt_glyph == "❯":
        content = [first_line]
        for line in lines[prompt_index + 1 :]:
            if _is_horizontal_border(line):
                return "\n".join(content)
            content.append(_visible(line))
        return None

    # Codex leaves one blank layout row between the composer and its
    # model/directory footer. Choose the last visible row after the prompt as
    # that footer so prompt-like text inside the draft cannot terminate it.
    following = lines[prompt_index + 1 :]
    footer_index = None
    for index in range(len(following) - 1, -1, -1):
        if _visible(following[index]).strip():
            footer_index = index
            break
    if footer_index is None or " · " not in _visible(following[footer_index]):
        return None
    content = [first_line] + [_visible(line) for line in following[:footer_index]]
    if not content or content[-1].strip() != "":
        return None
    content.pop()
    return "\n".join(content)


def send_message(target: str, message_file: Path) -> int:
    if not message_file.is_file():
        print(f"message file is not a regular file: {message_file}", file=sys.stderr)
        return EXIT_USAGE

    try:
        message = message_file.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        print(f"could not read UTF-8 message file {message_file}: {error}", file=sys.stderr)
        return EXIT_USAGE

    state, detail = classify_target(target)
    if state != CLEAR:
        print(state)
        if state == OCCUPIED:
            explanation = "target composer contains unsubmitted text"
        elif state == DIALOG:
            explanation = "target pane is showing a dialog"
        else:
            explanation = "target pane state could not be recognized"
        suffix = f"; tmux reported: {detail}" if detail else ""
        print(
            f"{state}: {explanation}; nothing sent (target {target}){suffix}",
            file=sys.stderr,
        )
        return EXIT_BY_STATE[state]

    buffer_name = f"tmux-message-{os.getpid()}-{uuid.uuid4().hex}"
    load = _tmux("load-buffer", "-b", buffer_name, "-", input_text=message)
    if load.returncode != 0:
        print(UNKNOWN)
        print(
            f"{UNKNOWN}: message buffer could not be prepared; nothing sent "
            f"(target {target}); tmux reported: {load.stderr.strip()}",
            file=sys.stderr,
        )
        return EXIT_BY_STATE[UNKNOWN]

    paste = _tmux("paste-buffer", "-p", "-r", "-d", "-b", buffer_name, "-t", target)
    if paste.returncode != 0:
        _tmux("delete-buffer", "-b", buffer_name)
        print(DELIVERY_UNVERIFIED)
        print(
            f"{DELIVERY_UNVERIFIED}: paste command failed; do not retry automatically "
            f"(target {target}); tmux reported: {paste.stderr.strip()}",
            file=sys.stderr,
        )
        return EXIT_DELIVERY_FAILED

    time.sleep(0.05)
    submit = _tmux("send-keys", "-t", target, "Enter")
    if submit.returncode != 0:
        print(DELIVERY_UNVERIFIED)
        print(
            f"{DELIVERY_UNVERIFIED}: message was pasted but Enter failed; do not retry "
            f"automatically (target {target}); tmux reported: {submit.stderr.strip()}",
            file=sys.stderr,
        )
        return EXIT_DELIVERY_FAILED

    post_state, post_detail, post_capture = _wait_for_clear(target)
    if post_state == OCCUPIED and _composer_text(post_capture) == message:
        submit_again = _tmux("send-keys", "-t", target, "Enter")
        if submit_again.returncode != 0:
            print(DELIVERY_UNVERIFIED)
            print(
                f"{DELIVERY_UNVERIFIED}: the exact pasted message remained, but the "
                f"single recovery Enter failed; do not retry automatically (target "
                f"{target}); tmux reported: {submit_again.stderr.strip()}",
                file=sys.stderr,
            )
            return EXIT_DELIVERY_FAILED
        post_state, post_detail, _ = _wait_for_clear(target)
    if post_state != CLEAR:
        print(DELIVERY_UNVERIFIED)
        suffix = f"; tmux reported: {post_detail}" if post_detail else ""
        print(
            f"{DELIVERY_UNVERIFIED}: message was pasted and Enter was sent, but "
            f"post-send pane state is {post_state}; do not retry automatically "
            f"(target {target}){suffix}",
            file=sys.stderr,
        )
        return EXIT_DELIVERY_FAILED
    print(SENT)
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Send a message to a tmux agent composer only when it is clear."
    )
    parser.add_argument("target", help="tmux target, such as session:window.pane")
    parser.add_argument("message_file", type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    return send_message(args.target, args.message_file)


if __name__ == "__main__":
    raise SystemExit(main())
