#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


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

    def test_does_not_reconstruct_codex_composer(self) -> None:
        self.assertIsNone(tmux_send._composer_text("› exact-looking text\nstatus\n"))


if __name__ == "__main__":
    unittest.main()
