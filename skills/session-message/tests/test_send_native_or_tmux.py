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


def tmux_child(stdout: str, exit_code: int, *, before: str = "") -> list[str]:
    """A real child process standing in for a tmux sender with a fixed result."""
    code = f"import os, signal, sys\n{before}\nsys.stdout.write({stdout!r})\nsys.exit({exit_code})"
    return [sys.executable, "-c", code]


def run_route(tmux_argv, queue_outcome=None, thread=THREAD):
    output = io.StringIO()
    with (
        mock.patch.object(sender, "try_codex_queue", return_value=queue_outcome) as queue,
        mock.patch("sys.stdout", output),
        mock.patch("sys.stderr", io.StringIO()),
    ):
        result = sender.route(tmux_argv, thread, MESSAGE)
    return result, output.getvalue(), queue


class TmuxFirstRouteTests(unittest.TestCase):
    def test_tmux_submit_is_final_and_never_queues(self) -> None:
        result, output, queue = run_route(tmux_child("SENT\n", 0), sender.QueueOutcome.ACCEPTED)
        self.assertEqual((result, output), (0, "SENT\n"))
        queue.assert_not_called()

    def test_typed_nothing_refusals_fall_back_to_codex_queue(self) -> None:
        for token, exit_code in (
            ("OCCUPIED", 1),
            ("DIALOG", 2),
            ("UNKNOWN layout", 3),
            ("UNKNOWN target", 3),
        ):
            with self.subTest(token=token):
                result, output, queue = run_route(tmux_child(f"{token}\n", exit_code), sender.QueueOutcome.ACCEPTED)
                self.assertEqual((result, output), (0, "QUEUED\n"))
                queue.assert_called_once_with(THREAD, MESSAGE)

    def test_uncertain_queue_after_refusal_reports_queue_uncertainty(self) -> None:
        result, output, _queue = run_route(tmux_child("OCCUPIED\n", 1), sender.QueueOutcome.UNVERIFIED)
        self.assertEqual((result, output), (4, "DELIVERY_UNVERIFIED native-queue\n"))

    def test_unavailable_queue_after_refusal_reemits_the_tmux_refusal(self) -> None:
        result, output, _queue = run_route(tmux_child("OCCUPIED\n", 1), sender.QueueOutcome.UNAVAILABLE)
        self.assertEqual((result, output), (1, "OCCUPIED\n"))

    def test_refusal_without_native_address_reemits_the_tmux_refusal(self) -> None:
        result, output, queue = run_route(tmux_child("DIALOG\n", 2), thread=None)
        self.assertEqual((result, output), (2, "DIALOG\n"))
        queue.assert_not_called()

    def test_results_that_may_have_typed_never_queue(self) -> None:
        unrecognized = (4, "DELIVERY_UNVERIFIED tmux-result-unrecognized\n")
        for name, argv, expected in (
            ("paste uncertain", tmux_child("DELIVERY_UNVERIFIED paste-failed\n", 4),
             (4, "DELIVERY_UNVERIFIED paste-failed\n")),
            ("no token", tmux_child("", 0), unrecognized),
            ("two tokens", tmux_child("OCCUPIED\nSENT\n", 1), unrecognized),
            ("status disagrees", tmux_child("OCCUPIED\n", 0), unrecognized),
            ("bare UNKNOWN", tmux_child("UNKNOWN \n", 3), unrecognized),
            ("interrupted", tmux_child("UNKNOWN interrupted\n", 3), (3, "UNKNOWN interrupted\n")),
            ("killed", tmux_child("", 0, before="os.kill(os.getpid(), signal.SIGKILL)"), unrecognized),
            ("invalid request", tmux_child("", 64), (64, "")),
        ):
            with self.subTest(name):
                result, output, queue = run_route(argv, sender.QueueOutcome.ACCEPTED)
                self.assertEqual((result, output), expected)
                queue.assert_not_called()

    def test_signal_during_tmux_attempt_forbids_the_fallback(self) -> None:
        argv = tmux_child(
            "OCCUPIED\n", 1,
            before="os.kill(os.getppid(), signal.SIGINT)\nimport time\ntime.sleep(0.2)",
        )
        result, output, queue = run_route(argv, sender.QueueOutcome.ACCEPTED)
        # Not OCCUPIED: that would invite tmux-message's retry schedule after a stop request.
        self.assertEqual((result, output), (3, "UNKNOWN interrupted\n"))
        queue.assert_not_called()

    def test_tmux_sender_that_cannot_start_falls_back_to_the_queue(self) -> None:
        result, output, queue = run_route(["/nonexistent/tmux-sender"], sender.QueueOutcome.ACCEPTED)
        self.assertEqual((result, output), (0, "QUEUED\n"))
        queue.assert_called_once_with(THREAD, MESSAGE)

    def test_without_a_pane_the_queue_is_the_route(self) -> None:
        result, output, queue = run_route(None, sender.QueueOutcome.ACCEPTED)
        self.assertEqual((result, output), (0, "QUEUED\n"))
        queue.assert_called_once_with(THREAD, MESSAGE)

    def test_no_pane_and_no_queue_reports_no_route(self) -> None:
        result, output, _queue = run_route(None, sender.QueueOutcome.UNAVAILABLE)
        self.assertEqual((result, output), (3, "UNAVAILABLE no-reachable-route\n"))

    def test_main_runs_the_guarded_tmux_sender_with_exact_text(self) -> None:
        with mock.patch.object(sender, "route", return_value=0) as route:
            self.assertEqual(sender.main(arguments()), 0)
        route.assert_called_once_with(
            [sys.executable, str(TMUX_SENDER), "0:2.0", "--shell-safe-text", MESSAGE],
            THREAD,
            MESSAGE,
        )

    def test_invalid_thread_is_refused_before_tmux(self) -> None:
        with (
            mock.patch.object(sender, "run_tmux_attempt") as tmux,
            mock.patch("sys.stderr", io.StringIO()),
        ):
            result = sender.main([*arguments(), "--codex-thread", "bad\x1bthread"])
        self.assertEqual(result, 64)
        tmux.assert_not_called()

    def test_control_character_is_refused_before_any_attempt(self) -> None:
        with (
            mock.patch.object(sender, "run_tmux_attempt") as tmux,
            mock.patch.object(sender, "try_codex_queue") as queue,
            mock.patch("sys.stderr", io.StringIO()),
        ):
            result = sender.main([*arguments(), "--shell-safe-text", "unsafe\x1btext"])
        self.assertEqual(result, 64)
        tmux.assert_not_called()
        queue.assert_not_called()


class CodexQueueTests(unittest.TestCase):
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

    def test_process_start_failure_is_unavailable(self) -> None:
        with (
            mock.patch.object(sender.shutil, "which", return_value="/usr/bin/codex"),
            mock.patch.object(sender.subprocess, "Popen", side_effect=FileNotFoundError),
        ):
            self.assertIs(sender.try_codex_queue(THREAD, MESSAGE), sender.QueueOutcome.UNAVAILABLE)


if __name__ == "__main__":
    unittest.main()
