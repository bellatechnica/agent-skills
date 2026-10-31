#!/usr/bin/env python3
"""Deliver safe text through guarded tmux first, and Codex queue as the fallback.

Tmux goes first because it reaches a busy recipient's running turn, while
`codex queue` holds the message until that turn ends. The queue is tried only
when no pane is reachable or the tmux attempt reports that it typed nothing.
The Relay wake helper calls `route` with its own tmux attempt, so the order
lives only here.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from enum import Enum
import importlib.util
from pathlib import Path
import shutil
import signal
import subprocess
import sys


EXIT_UNAVAILABLE = 3
EXIT_UNVERIFIED = 4
EXIT_USAGE = 64


class QueueOutcome(Enum):
    ACCEPTED = "accepted"
    UNAVAILABLE = "unavailable"
    UNVERIFIED = "unverified"


@dataclass(frozen=True)
class TmuxResult:
    """One tmux attempt's verified result line and exit status."""

    token: str | None
    exit_code: int
    typed_nothing: bool


# Tmux results that the tmux-message contract defines as "nothing sent", keyed
# by exit status. Only these may be followed by a native attempt.
_TYPED_NOTHING_EXITS = {1: "OCCUPIED", 2: "DIALOG", 3: "UNKNOWN "}
_UNRECOGNIZED = "DELIVERY_UNVERIFIED tmux-result-unrecognized"


class UsageError(Exception):
    """The request is invalid before a native or tmux attempt."""


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise UsageError(message)

    def exit(self, status: int = 0, message: str | None = None) -> None:
        raise UsageError(message.strip() if message else "help requested")


def _validate_thread(thread: str) -> None:
    if not thread.strip() or any(ord(character) < 32 or ord(character) == 127 for character in thread):
        raise UsageError("Codex thread address must be nonempty and contain no controls")


def try_codex_queue(thread: str, message: str) -> QueueOutcome:
    """Return unavailable only when no Codex queue process could start."""
    _validate_thread(thread)
    executable = shutil.which("codex")
    if executable is None:
        return QueueOutcome.UNAVAILABLE
    try:
        process = subprocess.Popen(
            [executable, "queue", "--thread", thread, "--message", message],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except OSError:
        return QueueOutcome.UNAVAILABLE
    try:
        stdout, _stderr = process.communicate()
    except (OSError, KeyboardInterrupt):
        return QueueOutcome.UNVERIFIED
    if process.returncode == 0 and any(
        line.startswith("Queued message ") and line != "Queued message "
        for line in stdout.splitlines()
    ):
        return QueueOutcome.ACCEPTED
    return QueueOutcome.UNVERIFIED


def classify_tmux_result(stdout: str, exit_code: int) -> TmuxResult:
    """Apply the tmux-message result contract: one token, agreeing with the status."""
    lines = [line for line in stdout.splitlines() if line]
    if exit_code == EXIT_USAGE and not lines:
        return TmuxResult(None, EXIT_USAGE, typed_nothing=False)
    if len(lines) != 1:
        return TmuxResult(_UNRECOGNIZED, EXIT_UNVERIFIED, typed_nothing=False)
    [token] = lines
    if exit_code == 0 and token == "SENT":
        return TmuxResult(token, 0, typed_nothing=False)
    if exit_code == EXIT_UNVERIFIED and token.startswith("DELIVERY_UNVERIFIED "):
        return TmuxResult(token, exit_code, typed_nothing=False)
    if _is_refusal(token, exit_code):
        # An interrupt is a request to stop, so it is reported rather than followed.
        return TmuxResult(token, exit_code, typed_nothing=token != "UNKNOWN interrupted")
    return TmuxResult(_UNRECOGNIZED, EXIT_UNVERIFIED, typed_nothing=False)


def _is_refusal(token: str, exit_code: int) -> bool:
    expected = _TYPED_NOTHING_EXITS.get(exit_code)
    if expected is None:
        return False
    if expected.endswith(" "):  # "UNKNOWN <class>" must name its class
        return token.startswith(expected) and bool(token[len(expected):].strip())
    return token == expected


def run_tmux_attempt(argv: list[str]) -> TmuxResult:
    """Run one tmux sender child, capturing its result line; stderr passes through.

    The child decides its own outcome on SIGINT, SIGTERM or SIGHUP, so this
    process waits for it, and a signal received meanwhile forbids a fallback.
    """
    managed = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
    received: list[int] = []
    previous = {number: signal.getsignal(number) for number in managed}
    for number in managed:
        signal.signal(number, lambda number, _frame: received.append(number))
    try:
        try:
            process = subprocess.Popen(argv, stdout=subprocess.PIPE, text=True)
        except OSError as error:
            print(f"tmux sender could not start: {error}", file=sys.stderr)
            return TmuxResult("UNKNOWN internal", 3, typed_nothing=not received)
        stdout, _stderr = process.communicate()
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)
    if process.returncode < 0:
        return TmuxResult(_UNRECOGNIZED, EXIT_UNVERIFIED, typed_nothing=False)
    result = classify_tmux_result(stdout, process.returncode)
    if received and result.typed_nothing:
        return TmuxResult(result.token, result.exit_code, typed_nothing=False)
    return result


def _emit(token: str | None, exit_code: int) -> int:
    if token is not None:
        print(token, flush=True)
    return exit_code


def route(tmux_argv: list[str] | None, codex_thread: str | None, native_text: str) -> int:
    """Try tmux, then Codex queue only after a typed-nothing refusal; print one token."""
    if codex_thread is not None:
        _validate_thread(codex_thread)
    refusal: TmuxResult | None = None
    if tmux_argv is not None:
        result = run_tmux_attempt(tmux_argv)
        if not result.typed_nothing:
            return _emit(result.token, result.exit_code)
        refusal = result
        if codex_thread is not None:
            print(f"tmux typed nothing ({result.token}); trying Codex queue", file=sys.stderr)
    if codex_thread is not None:
        outcome = try_codex_queue(codex_thread, native_text)
        if outcome is QueueOutcome.ACCEPTED:
            return _emit("QUEUED", 0)
        if outcome is QueueOutcome.UNVERIFIED:
            return _emit("DELIVERY_UNVERIFIED native-queue", EXIT_UNVERIFIED)
    if refusal is not None:
        # The caller follows tmux-message's schedule for this refusal.
        return _emit(refusal.token, refusal.exit_code)
    return _emit("UNAVAILABLE no-reachable-route", EXIT_UNAVAILABLE)


def _validate_with_tmux_sender(tmux_sender: Path, message: str) -> None:
    if not tmux_sender.is_file():
        raise UsageError(f"tmux sender is not a regular file: {tmux_sender}")
    spec = importlib.util.spec_from_file_location("tmux_send_for_native_route", tmux_sender)
    if spec is None or spec.loader is None:
        raise UsageError(f"could not load tmux sender: {tmux_sender}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        module._validate_message(message)
    except Exception as error:
        raise UsageError(f"message validation failed: {error}") from error
    finally:
        sys.modules.pop(spec.name, None)


def main(argv: list[str] | None = None) -> int:
    try:
        parser = Parser(
            description="Send reviewed non-sensitive text through guarded tmux, or Codex queue as the fallback.",
            allow_abbrev=False,
        )
        parser.add_argument("--tmux-sender", required=True, type=Path)
        parser.add_argument("--tmux-target")
        parser.add_argument("--codex-thread")
        parser.add_argument("--shell-safe-text", required=True)
        args = parser.parse_args(argv)
        _validate_with_tmux_sender(args.tmux_sender, args.shell_safe_text)
        tmux_argv = None
        if args.tmux_target is not None:
            tmux_argv = [
                sys.executable,
                str(args.tmux_sender),
                args.tmux_target,
                "--shell-safe-text",
                args.shell_safe_text,
            ]
        return route(tmux_argv, args.codex_thread, args.shell_safe_text)
    except (UsageError, ValueError) as error:
        print(f"session message error: {error}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    raise SystemExit(main())
