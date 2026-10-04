#!/usr/bin/env python3
"""Queue safe text for Codex, or run the guarded tmux sender when unavailable."""

from __future__ import annotations

import argparse
from enum import Enum
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys


EXIT_UNAVAILABLE = 3
EXIT_UNVERIFIED = 4
EXIT_USAGE = 64


class QueueOutcome(Enum):
    ACCEPTED = "accepted"
    UNAVAILABLE = "unavailable"
    UNVERIFIED = "unverified"


class UsageError(Exception):
    """The request is invalid before a native or tmux attempt."""


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise UsageError(message)

    def exit(self, status: int = 0, message: str | None = None) -> None:
        raise UsageError(message.strip() if message else "help requested")


def try_codex_queue(thread: str, message: str) -> QueueOutcome:
    """Return unavailable only when no Codex queue process could start."""
    if not thread.strip() or any(ord(character) < 32 or ord(character) == 127 for character in thread):
        raise UsageError("Codex thread address must be nonempty and contain no controls")
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
            description="Send reviewed non-sensitive text through Codex queue or guarded tmux.",
            allow_abbrev=False,
        )
        parser.add_argument("--tmux-sender", required=True, type=Path)
        parser.add_argument("--tmux-target")
        parser.add_argument("--codex-thread")
        parser.add_argument("--shell-safe-text", required=True)
        args = parser.parse_args(argv)
        _validate_with_tmux_sender(args.tmux_sender, args.shell_safe_text)
        if args.codex_thread is not None:
            outcome = try_codex_queue(args.codex_thread, args.shell_safe_text)
            if outcome is QueueOutcome.ACCEPTED:
                print("QUEUED", flush=True)
                return 0
            if outcome is QueueOutcome.UNVERIFIED:
                print("DELIVERY_UNVERIFIED native-queue", flush=True)
                return EXIT_UNVERIFIED
        if args.tmux_target is None:
            print("UNAVAILABLE no-reachable-route", flush=True)
            return EXIT_UNAVAILABLE
        os.execv(
            sys.executable,
            [
                sys.executable,
                str(args.tmux_sender),
                args.tmux_target,
                "--shell-safe-text",
                args.shell_safe_text,
            ],
        )
        raise RuntimeError("tmux sender exec unexpectedly returned")
    except OSError as error:
        print(f"UNAVAILABLE tmux-sender-start-failed: {error}", file=sys.stderr)
        return EXIT_UNAVAILABLE
    except (UsageError, ValueError) as error:
        print(f"session message error: {error}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    raise SystemExit(main())
