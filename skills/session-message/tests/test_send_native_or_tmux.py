from __future__ import annotations

import importlib.util
import io
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest import mock


SKILLS = Path(__file__).parents[2]
SCRIPT = SKILLS / "session-message" / "scripts" / "send_native_or_tmux.py"
TMUX_SENDER = SKILLS / "tmux-message" / "scripts" / "tmux_send.py"
SPEC = importlib.util.spec_from_file_location("send_native_or_tmux", SCRIPT)
assert SPEC and SPEC.loader
sender = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = sender
SPEC.loader.exec_module(sender)

THREAD = "codex-recipient"
MESSAGE = "From 0:1.0 (reviewer):\nThe review is complete."


def arguments(*, tmux_target: str | None = "0:2.0") -> list[str]:
    result = [
        "--tmux-sender", str(TMUX_SENDER),
        "--codex-thread", THREAD,
        "--shell-safe-text", MESSAGE,
    ]
    if tmux_target is not None:
        result.extend(("--tmux-target", tmux_target))
    return result


class NativeOrTmuxTests(unittest.TestCase):
    def test_positive_queue_acceptance_prevents_tmux(self) -> None:
        output = io.StringIO()
        with (
            mock.patch.object(sender, "try_codex_queue", return_value=sender.QueueOutcome.ACCEPTED),
            mock.patch.object(sender.os, "execv") as tmux,
            mock.patch("sys.stdout", output),
        ):
            result = sender.main(arguments())
        self.assertEqual((result, output.getvalue()), (0, "QUEUED\n"))
        tmux.assert_not_called()

    def test_prestart_unavailability_execs_guarded_tmux_with_exact_text(self) -> None:
        class Replaced(Exception):
            pass

        with (
            mock.patch.object(sender, "try_codex_queue", return_value=sender.QueueOutcome.UNAVAILABLE),
            mock.patch.object(sender.os, "execv", side_effect=Replaced) as tmux,
        ):
            with self.assertRaises(Replaced):
                sender.main(arguments())
        tmux.assert_called_once_with(
            sys.executable,
            [sys.executable, str(TMUX_SENDER), "0:2.0", "--shell-safe-text", MESSAGE],
        )

    def test_uncertain_queue_result_never_uses_tmux(self) -> None:
        output = io.StringIO()
        with (
            mock.patch.object(sender, "try_codex_queue", return_value=sender.QueueOutcome.UNVERIFIED),
            mock.patch.object(sender.os, "execv") as tmux,
            mock.patch("sys.stdout", output),
        ):
            result = sender.main(arguments())
        self.assertEqual((result, output.getvalue()), (4, "DELIVERY_UNVERIFIED native-queue\n"))
        tmux.assert_not_called()

    def test_missing_tmux_target_reports_no_route_after_queue_unavailable(self) -> None:
        output = io.StringIO()
        with (
            mock.patch.object(sender, "try_codex_queue", return_value=sender.QueueOutcome.UNAVAILABLE),
            mock.patch.object(sender.os, "execv") as tmux,
            mock.patch("sys.stdout", output),
        ):
            result = sender.main(arguments(tmux_target=None))
        self.assertEqual((result, output.getvalue()), (3, "UNAVAILABLE no-reachable-route\n"))
        tmux.assert_not_called()

    def test_queue_acceptance_requires_positive_client_output(self) -> None:
        for returncode, stdout, expected in (
            (0, "Queued message 123\n", sender.QueueOutcome.ACCEPTED),
            (0, "", sender.QueueOutcome.UNVERIFIED),
            (1, "Queued message 123\n", sender.QueueOutcome.UNVERIFIED),
        ):
            with self.subTest(returncode=returncode, stdout=stdout):
                process = SimpleNamespace(
                    returncode=returncode,
                    communicate=mock.Mock(return_value=(stdout, "")),
                )
                with (
                    mock.patch.object(sender.shutil, "which", return_value="/usr/bin/codex"),
                    mock.patch.object(sender.subprocess, "Popen", return_value=process) as launch,
                ):
                    result = sender.try_codex_queue(THREAD, MESSAGE)
                self.assertIs(result, expected)
                launch.assert_called_once_with(
                    ["/usr/bin/codex", "queue", "--thread", THREAD, "--message", MESSAGE],
                    stdout=sender.subprocess.PIPE,
                    stderr=sender.subprocess.PIPE,
                    text=True,
                )

    def test_process_start_failure_allows_tmux_fallback(self) -> None:
        with (
            mock.patch.object(sender.shutil, "which", return_value="/usr/bin/codex"),
            mock.patch.object(sender.subprocess, "Popen", side_effect=FileNotFoundError),
        ):
            self.assertIs(sender.try_codex_queue(THREAD, MESSAGE), sender.QueueOutcome.UNAVAILABLE)

    def test_control_character_is_refused_before_native_attempt(self) -> None:
        with mock.patch.object(sender, "try_codex_queue") as queue, mock.patch("sys.stderr", io.StringIO()):
            result = sender.main([*arguments(), "--shell-safe-text", "unsafe\x1btext"])
        self.assertEqual(result, 64)
        queue.assert_not_called()


if __name__ == "__main__":
    unittest.main()
