#!/usr/bin/env python3

from __future__ import annotations

import contextlib
import importlib.util
import io
from pathlib import Path
import unittest
from unittest import mock


SCRIPT = Path(__file__).parents[1] / "scripts" / "tmux_send.py"
SPEC = importlib.util.spec_from_file_location("tmux_send", SCRIPT)
assert SPEC and SPEC.loader
tmux_send = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tmux_send)


class ClassifyCaptureTests(unittest.TestCase):
    def test_codex_bare_prompt_is_clear(self) -> None:
        self.assertEqual(tmux_send.classify_capture("\n\x1b[1m›\x1b[0m \n\n  gpt-5.6-sol high · /tmp\n"), "CLEAR")

    def test_codex_dim_suggestion_is_clear(self) -> None:
        self.assertEqual(tmux_send.classify_capture("\x1b[1m›\x1b[0m \x1b[2mAsk Codex to do anything\x1b[0m\n"), "CLEAR")

    def test_truecolor_selector_does_not_make_typed_text_dim(self) -> None:
        capture = "› \x1b[38;2;10;20;30mtyped draft\x1b[0m\n"
        self.assertEqual(tmux_send.classify_capture(capture), "OCCUPIED")

    def test_truecolor_components_do_not_reset_real_dim(self) -> None:
        capture = "› \x1b[2;38;2;0;0;0mreplaceable suggestion\x1b[0m\n"
        self.assertEqual(tmux_send.classify_capture(capture), "CLEAR")

    def test_sgr_22_ends_dim_before_typed_text(self) -> None:
        capture = "› \x1b[2msuggestion\x1b[22m typed draft\n"
        self.assertEqual(tmux_send.classify_capture(capture), "OCCUPIED")

    def test_claude_plain_startup_placeholder_is_clear(self) -> None:
        self.assertEqual(tmux_send.classify_capture("────────\n❯\u00a0Try \"create a util logging.py that...\"\n────────\n"), "CLEAR")

    def test_claude_submitted_transcript_prompt_is_not_a_composer(self) -> None:
        capture = "❯ submitted request\n· Schlepping… (1s)\n⏸ manual mode on · esc to interrupt\n"
        self.assertEqual(tmux_send.classify_capture(capture), "CLEAR")

    def test_claude_transcript_prompt_without_active_turn_is_unknown(self) -> None:
        self.assertEqual(tmux_send.classify_capture("❯ submitted request\nassistant response\n"), "UNKNOWN")

    def test_transcript_words_do_not_fake_active_turn(self) -> None:
        capture = "❯ submitted request\nThe footer once said esc to interrupt.\n"
        self.assertEqual(tmux_send.classify_capture(capture), "UNKNOWN")

    def test_plain_draft_is_occupied(self) -> None:
        self.assertEqual(tmux_send.classify_capture("────────\n❯ actual draft\n────────\n"), "OCCUPIED")

    def test_prompt_glyph_inside_draft_is_occupied(self) -> None:
        self.assertEqual(tmux_send.classify_capture("────────\n› do not send to ❯ this text\n"), "OCCUPIED")

    def test_multiline_draft_is_occupied(self) -> None:
        self.assertEqual(tmux_send.classify_capture("────────\n❯ first line\n  second line\n────────\n"), "OCCUPIED")

    def test_leading_newline_draft_is_occupied(self) -> None:
        self.assertEqual(tmux_send.classify_capture("────────\n❯ \n  second line\n────────\n"), "OCCUPIED")

    def test_dialog_footer_is_dialog(self) -> None:
        capture = "❯ No, exit\n  Yes, I trust this folder\nEnter to confirm · Esc to cancel\n"
        self.assertEqual(tmux_send.classify_capture(capture), "DIALOG")

    def test_passive_toast_above_composer_is_clear(self) -> None:
        capture = "How is Claude doing? 1: Bad 2: Fine 3: Good 0: Dismiss\n────────\n❯ \n────────\n⏵ auto mode on\n"
        self.assertEqual(tmux_send.classify_capture(capture), "CLEAR")

    def test_dialog_words_in_transcript_do_not_override_composer(self) -> None:
        capture = "User quoted: Enter to confirm · Esc to cancel\n" + ("old line\n" * 5) + "────────\n❯ draft\n────────\n"
        self.assertEqual(tmux_send.classify_capture(capture), "OCCUPIED")

    def test_unrecognised_capture_is_unknown(self) -> None:
        self.assertEqual(tmux_send.classify_capture("shell output only\n$ "), "UNKNOWN")

    def test_reconstructs_exact_claude_composer_text(self) -> None:
        capture = "──────── title ─\n❯\u00a0first line\nsecond line\n\n────────\nfooter\n"
        self.assertEqual(tmux_send._composer_text(capture), "first line\nsecond line\n")

    def test_reconstructs_exact_codex_composer_text(self) -> None:
        capture = "› first line\nsecond line\n\n   \n  gpt-5.6-sol high · /tmp\n\n"
        self.assertEqual(tmux_send._composer_text(capture), "first line\nsecond line\n")

    def test_codex_exact_text_can_contain_claude_prompt_glyph(self) -> None:
        capture = "› draft ends with literal prompt glyph ❯\n\n  gpt-5.6-sol high · /tmp\n"
        expected = "draft ends with literal prompt glyph ❯"
        self.assertEqual(tmux_send._composer_text(capture), expected)

    def test_exact_composer_comparison_preserves_message_spaces(self) -> None:
        capture = "──────── title ─\n❯\u00a0  spaced message  \n────────\nfooter\n"
        self.assertEqual(tmux_send._composer_text(capture), "  spaced message  ")

    def test_does_not_reconstruct_codex_composer(self) -> None:
        self.assertIsNone(tmux_send._composer_text("› exact-looking text\nstatus\n"))

    def test_verification_uses_exponential_backoff_with_three_second_ceiling(self) -> None:
        now = 0.0
        delays = []

        def clock() -> float:
            return now

        def sleep(delay: float) -> None:
            nonlocal now
            delays.append(delay)
            now += delay

        captures = [
            ("OCCUPIED", "", "draft") for _ in range(5)
        ] + [("CLEAR", "", "clear")]
        with mock.patch.object(tmux_send, "_capture_target", side_effect=captures):
            result = tmux_send._wait_for_clear("scratch:agent.0", clock=clock, sleep=sleep)

        self.assertEqual(result, ("CLEAR", "", "clear"))
        expected = [0.05, 0.1, 0.2, 0.4, 0.8, 1.6]
        self.assertEqual(len(delays), len(expected))
        for actual, predicted in zip(delays, expected):
            self.assertAlmostEqual(actual, predicted)
        self.assertAlmostEqual(sum(delays), 3.15)


class OutputContractTests(unittest.TestCase):
    @staticmethod
    def _message_path() -> mock.Mock:
        path = mock.Mock(spec=Path)
        path.is_file.return_value = True
        path.read_text.return_value = "test message\n"
        path.resolve.return_value = Path("/tmp/test-message.txt")
        return path

    def test_pre_send_refusals_name_state_and_confirm_nothing_sent(self) -> None:
        cases = {
            "OCCUPIED": "composer contains unsubmitted text",
            "DIALOG": "pane is showing a dialog",
            "UNKNOWN": "pane state could not be recognized",
        }
        for state, explanation in cases.items():
            with self.subTest(state=state):
                stdout = io.StringIO()
                stderr = io.StringIO()
                with (
                    mock.patch.object(tmux_send, "classify_target", return_value=(state, "")),
                    contextlib.redirect_stdout(stdout),
                    contextlib.redirect_stderr(stderr),
                ):
                    result = tmux_send.send_message("scratch:agent.0", self._message_path())

                self.assertEqual(result, tmux_send.EXIT_BY_STATE[state])
                self.assertEqual(stdout.getvalue(), f"{state}\n")
                self.assertIn(explanation, stderr.getvalue())
                self.assertIn("nothing sent", stderr.getvalue())

    def test_verified_send_prints_sent(self) -> None:
        completed = mock.Mock(returncode=0, stderr="")
        stdout = io.StringIO()
        message_path = self._message_path()
        with (
            mock.patch.object(tmux_send, "classify_target", return_value=("CLEAR", "")),
            mock.patch.object(tmux_send, "_tmux", return_value=completed) as tmux_call,
            mock.patch.object(tmux_send, "_wait_for_clear", return_value=("CLEAR", "", "")),
            contextlib.redirect_stdout(stdout),
        ):
            result = tmux_send.send_message("scratch:agent.0", message_path)

        self.assertEqual(result, 0)
        self.assertEqual(stdout.getvalue(), "SENT\n")
        message_path.read_text.assert_called_once_with(encoding="utf-8")
        load_call = tmux_call.call_args_list[0]
        self.assertEqual(load_call.args[:4], ("load-buffer", "-b", load_call.args[2], "-"))
        self.assertEqual(load_call.kwargs, {"input_text": "test message\n"})

    def test_missing_tmux_executable_becomes_failed_command(self) -> None:
        with mock.patch.object(
            tmux_send.subprocess, "run", side_effect=FileNotFoundError("tmux missing")
        ):
            result = tmux_send._tmux("capture-pane")

        self.assertEqual(result.returncode, 127)
        self.assertEqual(result.stdout, "")
        self.assertIn("tmux missing", result.stderr)

    def test_post_send_failure_never_prints_captured_content(self) -> None:
        completed = mock.Mock(returncode=0, stderr="")
        stdout = io.StringIO()
        stderr = io.StringIO()
        secret_capture = "pane transcript that must stay private"
        with (
            mock.patch.object(tmux_send, "classify_target", return_value=("CLEAR", "")),
            mock.patch.object(tmux_send, "_tmux", return_value=completed),
            mock.patch.object(
                tmux_send,
                "_wait_for_clear",
                return_value=("OCCUPIED", "", secret_capture),
            ),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            result = tmux_send.send_message("scratch:agent.0", self._message_path())

        self.assertEqual(result, tmux_send.EXIT_DELIVERY_FAILED)
        self.assertEqual(stdout.getvalue(), "DELIVERY_UNVERIFIED\n")
        self.assertIn("message was pasted and Enter was sent", stderr.getvalue())
        self.assertNotIn(secret_capture, stdout.getvalue())
        self.assertNotIn(secret_capture, stderr.getvalue())

    def test_exact_stranded_message_gets_one_recovery_enter(self) -> None:
        completed = mock.Mock(returncode=0, stderr="")
        stranded = "──────── title ─\n❯\u00a0test message\n\n────────\nfooter\n"
        stdout = io.StringIO()
        with (
            mock.patch.object(tmux_send, "classify_target", return_value=("CLEAR", "")),
            mock.patch.object(tmux_send, "_tmux", return_value=completed) as tmux_call,
            mock.patch.object(
                tmux_send,
                "_wait_for_clear",
                side_effect=[("OCCUPIED", "", stranded), ("CLEAR", "", "")],
            ),
            contextlib.redirect_stdout(stdout),
        ):
            result = tmux_send.send_message("scratch:agent.0", self._message_path())

        send_key_calls = [
            call for call in tmux_call.call_args_list if call.args[0] == "send-keys"
        ]
        self.assertEqual(result, 0)
        self.assertEqual(stdout.getvalue(), "SENT\n")
        self.assertEqual(len(send_key_calls), 2)

    def test_mixed_stranded_message_gets_no_recovery_enter(self) -> None:
        completed = mock.Mock(returncode=0, stderr="")
        mixed = "──────── title ─\n❯\u00a0someone else's text + test message\n────────\nfooter\n"
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            mock.patch.object(tmux_send, "classify_target", return_value=("CLEAR", "")),
            mock.patch.object(tmux_send, "_tmux", return_value=completed) as tmux_call,
            mock.patch.object(
                tmux_send,
                "_wait_for_clear",
                return_value=("OCCUPIED", "", mixed),
            ),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            result = tmux_send.send_message("scratch:agent.0", self._message_path())

        send_key_calls = [
            call for call in tmux_call.call_args_list if call.args[0] == "send-keys"
        ]
        self.assertEqual(result, tmux_send.EXIT_DELIVERY_FAILED)
        self.assertEqual(stdout.getvalue(), "DELIVERY_UNVERIFIED\n")
        self.assertEqual(len(send_key_calls), 1)


if __name__ == "__main__":
    unittest.main()
