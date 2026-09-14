#!/usr/bin/env python3

from __future__ import annotations

import contextlib
import importlib.util
import io
from pathlib import Path
import signal
import sys
import unittest
from unittest import mock


SCRIPT = Path(__file__).parents[1] / "scripts" / "tmux_send.py"
SPEC = importlib.util.spec_from_file_location("tmux_send", SCRIPT)
assert SPEC and SPEC.loader
tmux_send = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = tmux_send
SPEC.loader.exec_module(tmux_send)

WIDTH = 40
BORDER = "─" * WIDTH


def claude_capture(first: str = "", *continuations: str) -> str:
    rows = [BORDER, f"❯\u00a0{first}"]
    rows.extend(f"  {row}" for row in continuations)
    rows.extend([BORDER, "  ⏵⏵ auto mode on"])
    return "\n".join(rows) + "\n"


def codex_capture(first: str = "", *continuations: str) -> str:
    rows = [f"› {first}"]
    rows.extend(f"  {row}" for row in continuations)
    rows.extend(["", "  gpt-5.6-sol high · /tmp"])
    return "\n".join(rows) + "\n"


def codex_editing_footer_capture(first: str = "draft") -> str:
    footer_width = WIDTH - 2
    footer = "  status".ljust(footer_width, "·")
    return f"› {first}\n\n\x1b[2m{footer}\x1b[0m\n"


def pane() -> object:
    return tmux_send.PaneIdentity("%7", "777", WIDTH, "/tmp/tmux.sock", "123", "s:w.0")


def result(state: str, composer: object | None = None) -> object:
    return tmux_send.CaptureResult(state, "", "", composer)


def owned(text: str = "message\n") -> object:
    return result(
        tmux_send.OCCUPIED,
        tmux_send.Composer("codex", text, False, True),
    )


def cleared(client: str = "codex") -> object:
    return result(
        tmux_send.CLEAR,
        tmux_send.Composer(client, "", False, False),
    )


class ClassifyCaptureTests(unittest.TestCase):
    def test_codex_bare_prompt_is_clear(self) -> None:
        self.assertEqual(tmux_send.classify_capture(codex_capture(), WIDTH), "CLEAR")

    def test_codex_dim_suggestion_is_clear(self) -> None:
        capture = codex_capture("\x1b[2mAsk Codex to do anything\x1b[0m")
        self.assertEqual(tmux_send.classify_capture(capture, WIDTH), "CLEAR")

    def test_dim_native_paste_placeholders_are_occupied(self) -> None:
        captures = (
            codex_capture("\x1b[2m[Pasted Content 1834 chars]\x1b[0m"),
            claude_capture("\x1b[2m[Pasted text #1 +20 lines]\x1b[0m"),
        )
        for capture in captures:
            with self.subTest(client=capture[0]):
                self.assertEqual(
                    tmux_send.classify_capture(capture, WIDTH), "OCCUPIED"
                )

    def test_dim_placeholder_with_other_text_is_occupied(self) -> None:
        captures = (
            codex_capture(
                "\x1b[2m[Pasted Content 1834 chars] #2 appended\x1b[0m"
            ),
            claude_capture(
                "\x1b[2mprefix [Pasted text #1 +20 lines] suffix\x1b[0m"
            ),
        )
        for capture in captures:
            with self.subTest(client=capture[0]):
                self.assertEqual(
                    tmux_send.classify_capture(capture, WIDTH), "OCCUPIED"
                )

    def test_codex_full_width_dim_editing_footer_recognizes_draft(self) -> None:
        capture = codex_editing_footer_capture("queued wake")
        self.assertEqual(tmux_send.classify_capture(capture, WIDTH), "OCCUPIED")

    def test_codex_short_dim_row_is_not_an_editing_footer(self) -> None:
        capture = "› queued wake\n\n\x1b[2m  short status\x1b[0m\n"
        self.assertEqual(tmux_send.classify_capture(capture, WIDTH), "UNKNOWN")

    def test_codex_full_width_plain_row_is_not_an_editing_footer(self) -> None:
        footer = "  status".ljust(WIDTH - 2, "·")
        capture = f"› queued wake\n\n{footer}\n"
        self.assertEqual(tmux_send.classify_capture(capture, WIDTH), "UNKNOWN")

    def test_codex_footer_must_be_bottommost_nonblank_row(self) -> None:
        capture = codex_capture("queued wake") + "active output\n"
        self.assertEqual(tmux_send.classify_capture(capture, WIDTH), "UNKNOWN")

    def test_claude_bare_prompt_is_clear(self) -> None:
        self.assertEqual(tmux_send.classify_capture(claude_capture(), WIDTH), "CLEAR")

    def test_plain_placeholder_is_occupied(self) -> None:
        capture = claude_capture('Try "rm -rf build..."')
        self.assertEqual(tmux_send.classify_capture(capture, WIDTH), "OCCUPIED")

    def test_truecolor_selector_does_not_make_typed_text_dim(self) -> None:
        capture = codex_capture("\x1b[38;2;10;20;30mtyped draft\x1b[0m")
        self.assertEqual(tmux_send.classify_capture(capture, WIDTH), "OCCUPIED")

    def test_truecolor_components_do_not_reset_real_dim(self) -> None:
        capture = codex_capture("\x1b[2;38;2;0;0;0mreplaceable suggestion\x1b[0m")
        self.assertEqual(tmux_send.classify_capture(capture, WIDTH), "CLEAR")

    def test_sgr_22_ends_dim_before_typed_text(self) -> None:
        capture = codex_capture("\x1b[2msuggestion\x1b[22m typed draft")
        self.assertEqual(tmux_send.classify_capture(capture, WIDTH), "OCCUPIED")

    def test_typed_prefix_plus_dim_ghost_is_occupied(self) -> None:
        capture = codex_capture("typed \x1b[2mghost\x1b[0m")
        self.assertEqual(tmux_send.classify_capture(capture, WIDTH), "OCCUPIED")
        composer = tmux_send._composer(capture.splitlines(), WIDTH)
        self.assertIsNotNone(composer)
        self.assertTrue(composer.has_dim_text)

    def test_multiline_codex_draft_is_occupied(self) -> None:
        self.assertEqual(
            tmux_send.classify_capture(codex_capture("first", "second"), WIDTH),
            "OCCUPIED",
        )

    def test_multiline_claude_draft_is_occupied(self) -> None:
        self.assertEqual(
            tmux_send.classify_capture(claude_capture("first", "second"), WIDTH),
            "OCCUPIED",
        )

    def test_codex_leading_newline_gpt_row_is_occupied(self) -> None:
        self.assertEqual(
            tmux_send.classify_capture(codex_capture("", "gpt-quoted"), WIDTH),
            "OCCUPIED",
        )

    def test_markdown_rule_after_leading_newline_is_occupied_for_both(self) -> None:
        for capture in (codex_capture("", "---"), claude_capture("", "---")):
            with self.subTest(capture=capture[:1]):
                self.assertEqual(tmux_send.classify_capture(capture, WIDTH), "OCCUPIED")

    def test_quoted_codex_prompt_is_part_of_real_draft(self) -> None:
        capture = codex_capture("notes about this:", "› message")
        composer = tmux_send._composer(capture.splitlines(), WIDTH)
        self.assertEqual(composer.text, "notes about this:\n› message")

    def test_quoted_claude_composer_is_part_of_real_draft(self) -> None:
        capture = claude_capture("notes", BORDER, "❯ message")
        composer = tmux_send._composer(capture.splitlines(), WIDTH)
        self.assertEqual(composer.text, f"notes\n{BORDER}\n❯ message")

    def test_prompt_glyph_inside_first_line_is_occupied(self) -> None:
        self.assertEqual(
            tmux_send.classify_capture(codex_capture("do not send to ❯ this"), WIDTH),
            "OCCUPIED",
        )

    def test_unindented_continuation_makes_layout_unknown(self) -> None:
        capture = f"› first\nsecond\n\n  gpt-5.6-sol high · /tmp\n"
        self.assertEqual(tmux_send.classify_capture(capture, WIDTH), "UNKNOWN")

    def test_active_footer_without_composer_is_unknown(self) -> None:
        capture = "❯ submitted request\n• Working (1s • esc to interrupt)\n"
        self.assertEqual(tmux_send.classify_capture(capture, WIDTH), "UNKNOWN")

    def test_historical_claude_composer_before_active_output_is_unknown(self) -> None:
        capture = claude_capture() + "• Working (1s • esc to interrupt)\n"
        self.assertEqual(tmux_send.classify_capture(capture, WIDTH), "UNKNOWN")

    def test_passive_toast_above_clear_composer_is_clear(self) -> None:
        capture = "How is Claude doing? 1: Bad 2: Fine 3: Good\n" + claude_capture()
        self.assertEqual(tmux_send.classify_capture(capture, WIDTH), "CLEAR")

    def test_dialog_footer_variants_are_dialog(self) -> None:
        footers = (
            "Enter to confirm · Esc to cancel",
            "↑/↓ to navigate · Enter to select · Esc to close",
            "Space to toggle, Enter to confirm",
            "Enter to submit; Esc to cancel",
            "Press Enter to select • Ctrl+C to exit",
            "Type a name and press Enter",
        )
        for footer in footers:
            with self.subTest(footer=footer):
                self.assertEqual(tmux_send.classify_capture(f"option\n{footer}\n", WIDTH), "DIALOG")

    def test_dialog_words_outside_footer_do_not_override_composer(self) -> None:
        capture = "Enter to confirm · Esc to cancel\n" + ("old\n" * 6) + claude_capture("draft")
        self.assertEqual(tmux_send.classify_capture(capture, WIDTH), "OCCUPIED")

    def test_unrecognized_shell_is_unknown(self) -> None:
        self.assertEqual(tmux_send.classify_capture("shell output\n$ \n", WIDTH), "UNKNOWN")

    def test_exact_multiline_and_trailing_lf_are_reconstructed(self) -> None:
        for capture in (
            codex_capture("first", "second", ""),
            claude_capture("first", "second", ""),
        ):
            with self.subTest(client=capture[0]):
                composer = tmux_send._composer(capture.splitlines(), WIDTH)
                self.assertEqual(composer.text, "first\nsecond\n")
                self.assertFalse(composer.has_dim_text)

    def test_claude_display_padding_is_not_message_text(self) -> None:
        content = "message"
        padding = " " * (WIDTH - len("❯\u00a0") - len(content))
        capture = "\n".join(
            [BORDER, f"❯\u00a0{content}{padding}", BORDER, "  ⏵⏵ auto mode on"]
        )
        composer = tmux_send._composer(capture.splitlines(), WIDTH)
        self.assertEqual(composer.text, content)


class ResolveTargetTests(unittest.TestCase):
    @staticmethod
    def pane_row(
        *,
        session: str = "s",
        window_name: str = "work",
        window_index: str = "1",
        pane_index: str = "0",
        pane_id: str = "%9",
        window_panes: str = "1",
    ) -> str:
        return (
            f"{session}\t{window_name}\t{window_index}\t{pane_index}\t{pane_id}\t"
            f"999\t120\t/tmp/sock\t123\t{window_panes}\n"
        )

    def test_server_failure_is_classified(self) -> None:
        failed = mock.Mock(returncode=1, stderr="no server", stdout="")
        with mock.patch.object(tmux_send, "_tmux", return_value=failed):
            identity, kind, detail = tmux_send.resolve_target("s:w.0")
        self.assertIsNone(identity)
        self.assertEqual(kind, "server")
        self.assertEqual(detail, "no server")

    def test_target_failure_is_classified_after_server_answers(self) -> None:
        okay = mock.Mock(returncode=0, stderr="", stdout="123\t/tmp/sock\n")
        panes = mock.Mock(returncode=0, stderr="", stdout=self.pane_row())
        with mock.patch.object(tmux_send, "_tmux", side_effect=[okay, panes]):
            identity, kind, detail = tmux_send.resolve_target("s:missing.0")
        self.assertIsNone(identity)
        self.assertEqual(kind, "target")
        self.assertEqual(detail, "no pane has that exact address")

    def test_target_is_pinned_to_pane_id(self) -> None:
        server = mock.Mock(returncode=0, stderr="", stdout="123\t/tmp/sock\n")
        panes = mock.Mock(returncode=0, stderr="", stdout=self.pane_row())
        with mock.patch.object(tmux_send, "_tmux", side_effect=[server, panes]):
            resolved, kind, detail = tmux_send.resolve_target("s:work.0")
        self.assertEqual((kind, detail), ("", ""))
        self.assertEqual(resolved.pane_id, "%9")
        self.assertEqual(resolved.socket_path, "/tmp/sock")

    def test_unknown_window_name_does_not_fall_back_to_active_pane(self) -> None:
        server = mock.Mock(returncode=0, stderr="", stdout="123\t/tmp/sock\n")
        panes = mock.Mock(returncode=0, stderr="", stdout=self.pane_row())
        with mock.patch.object(tmux_send, "_tmux", side_effect=[server, panes]):
            resolved, kind, detail = tmux_send.resolve_target("s:not-there.0")
        self.assertIsNone(resolved)
        self.assertEqual((kind, detail), ("target", "no pane has that exact address"))

    def test_single_pane_window_may_omit_pane_index(self) -> None:
        server = mock.Mock(returncode=0, stderr="", stdout="123\t/tmp/sock\n")
        panes = mock.Mock(returncode=0, stderr="", stdout=self.pane_row())
        with mock.patch.object(tmux_send, "_tmux", side_effect=[server, panes]):
            resolved, kind, detail = tmux_send.resolve_target("s:work")
        self.assertEqual((kind, detail), ("", ""))
        self.assertEqual(resolved.pane_id, "%9")

    def test_multi_pane_window_requires_pane_index(self) -> None:
        server = mock.Mock(returncode=0, stderr="", stdout="123\t/tmp/sock\n")
        rows = self.pane_row(window_panes="2") + self.pane_row(
            pane_index="1", pane_id="%10", window_panes="2"
        )
        panes = mock.Mock(returncode=0, stderr="", stdout=rows)
        with mock.patch.object(tmux_send, "_tmux", side_effect=[server, panes]):
            resolved, kind, detail = tmux_send.resolve_target("s:work")
        self.assertIsNone(resolved)
        self.assertEqual((kind, detail), ("target", "no pane has that exact address"))

    def test_ambiguous_name_and_index_is_rejected(self) -> None:
        server = mock.Mock(returncode=0, stderr="", stdout="123\t/tmp/sock\n")
        rows = self.pane_row(window_name="2", window_index="1") + self.pane_row(
            window_name="other", window_index="2", pane_id="%10"
        )
        panes = mock.Mock(returncode=0, stderr="", stdout=rows)
        with mock.patch.object(tmux_send, "_tmux", side_effect=[server, panes]):
            resolved, kind, detail = tmux_send.resolve_target("s:2.0")
        self.assertIsNone(resolved)
        self.assertEqual((kind, detail), ("target", "the exact address is ambiguous"))


class VerificationTests(unittest.TestCase):
    def test_first_nonempty_composer_observation_proves_processing(self) -> None:
        sequence = [owned(), result("CLEAR"), owned(), owned()]
        delays = []
        with mock.patch.object(tmux_send, "capture_target", side_effect=sequence):
            actual = tmux_send._wait_for_processed_paste(
                pane(), None, sleep=delays.append
            )
        self.assertTrue(tmux_send._paste_processed(actual, None))
        self.assertEqual(delays, [0.05])

    def test_stale_clear_never_counts_as_processed_paste(self) -> None:
        delays = []
        with mock.patch.object(
            tmux_send,
            "capture_target",
            return_value=result("CLEAR"),
        ):
            actual = tmux_send._wait_for_processed_paste(
                pane(), None, sleep=delays.append
            )
        self.assertFalse(tmux_send._paste_processed(actual, None))
        self.assertEqual(delays, list(tmux_send.VERIFY_DELAYS_SECONDS))
        self.assertAlmostEqual(sum(delays), 3.15)

    def test_changed_dim_placeholder_proves_processing(self) -> None:
        before = tmux_send.Composer("codex", "Ask Codex", True, False)
        after = tmux_send.Composer("codex", "[Pasted Content 100 chars]", True, False)
        self.assertTrue(tmux_send._paste_processed(result("CLEAR", after), before))

    def test_changed_dim_suggestion_does_not_prove_processing(self) -> None:
        before = tmux_send.Composer("codex", "Ask Codex", True, False)
        after = tmux_send.Composer("codex", "Try another prompt", True, False)
        self.assertFalse(tmux_send._paste_processed(result("CLEAR", after), before))

    def test_native_placeholders_are_client_specific(self) -> None:
        placeholders = (
            tmux_send.Composer("codex", "[Pasted Content 100 chars]", True, False),
            tmux_send.Composer(
                "codex", "[Pasted Content 100 chars] #2", True, False
            ),
            tmux_send.Composer("claude", "[Pasted text #1 +2 lines]", True, False),
            tmux_send.Composer(
                "claude", "[...Truncated text #2 +7 lines...]", True, False
            ),
        )
        for composer in placeholders:
            with self.subTest(client=composer.client, text=composer.text):
                self.assertTrue(tmux_send._is_native_paste_placeholder(composer))

    def test_dim_placeholder_cannot_also_prove_submit_clear(self) -> None:
        placeholder = result(
            "CLEAR",
            tmux_send.Composer(
                "codex", "[Pasted Content 100 chars]", True, False
            ),
        )
        self.assertFalse(tmux_send._submit_cleared(placeholder, placeholder))

    def test_clear_wait_uses_exponential_schedule(self) -> None:
        processed = owned()
        sequence = [owned() for _ in range(5)] + [cleared()]
        delays = []
        with mock.patch.object(tmux_send, "capture_target", side_effect=sequence):
            actual = tmux_send._wait_for_clear(
                pane(), processed, sleep=delays.append
            )
        self.assertEqual(actual.state, "CLEAR")
        self.assertEqual(delays, list(tmux_send.VERIFY_DELAYS_SECONDS))


class OutputContractTests(unittest.TestCase):
    @staticmethod
    def message_path(text: str = "message\n") -> mock.Mock:
        path = mock.Mock(spec=Path)
        path.is_file.return_value = True
        path.read_bytes.return_value = text.encode("utf-8")
        return path

    @staticmethod
    def completed(returncode: int = 0, stderr: str = "") -> mock.Mock:
        return mock.Mock(returncode=returncode, stderr=stderr, stdout="")

    def invoke(
        self,
        *,
        initial: object,
        tmux_result: object | None = None,
        processed_result: object | None = None,
        clear_result: object | None = None,
    ) -> tuple[int, str, str, mock.Mock]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        tmux_result = tmux_result or self.completed()
        with (
            mock.patch.object(tmux_send, "resolve_target", return_value=(pane(), "", "")),
            mock.patch.object(tmux_send, "capture_target", return_value=initial),
            mock.patch.object(tmux_send, "_tmux", return_value=tmux_result) as tmux_call,
            mock.patch.object(
                tmux_send,
                "_wait_for_processed_paste",
                return_value=processed_result or owned(),
            ),
            mock.patch.object(
                tmux_send,
                "_wait_for_clear",
                return_value=clear_result or cleared(),
            ),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            code = tmux_send.send_message("s:w.0", self.message_path())
        return code, stdout.getvalue(), stderr.getvalue(), tmux_call

    def test_verified_positive_transition_prints_sent(self) -> None:
        code, stdout, stderr, tmux_call = self.invoke(initial=result("CLEAR"))
        self.assertEqual((code, stdout, stderr), (0, "SENT\n", ""))
        send_keys = [call for call in tmux_call.call_args_list if call.args[0] == "send-keys"]
        self.assertEqual(len(send_keys), 1)
        self.assertEqual(send_keys[0].args[-1], "Enter")
        self.assertEqual(send_keys[0].args[-2], "%7")

    def test_message_lf_bytes_are_not_translated(self) -> None:
        message = "first\nsecond\n"
        stdout = io.StringIO()
        okay = self.completed()
        with (
            mock.patch.object(tmux_send, "resolve_target", return_value=(pane(), "", "")),
            mock.patch.object(tmux_send, "capture_target", return_value=result("CLEAR")),
            mock.patch.object(
                tmux_send,
                "_wait_for_processed_paste",
                return_value=owned(message),
            ),
            mock.patch.object(tmux_send, "_wait_for_clear", return_value=cleared()),
            mock.patch.object(tmux_send, "_tmux", return_value=okay) as tmux_call,
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            code = tmux_send.send_message("s:w.0", self.message_path(message))
        load = [call for call in tmux_call.call_args_list if call.args[0] == "load-buffer"]
        self.assertEqual(code, 0)
        self.assertEqual(len(load), 1)
        self.assertEqual(load[0].kwargs["input_text"], message)

    def test_stdin_bytes_use_the_same_buffer_path(self) -> None:
        stdout = io.StringIO()
        okay = self.completed()
        message = "shell-safe wake"
        with (
            mock.patch.object(tmux_send, "resolve_target", return_value=(pane(), "", "")),
            mock.patch.object(tmux_send, "capture_target", return_value=result("CLEAR")),
            mock.patch.object(
                tmux_send,
                "_wait_for_processed_paste",
                return_value=owned(message),
            ),
            mock.patch.object(tmux_send, "_wait_for_clear", return_value=cleared()),
            mock.patch.object(tmux_send, "_tmux", return_value=okay) as tmux_call,
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            code = tmux_send.send_message(
                "s:w.0",
                read_stdin=True,
                stdin=io.BytesIO(message.encode("utf-8")),
            )
        load = [call for call in tmux_call.call_args_list if call.args[0] == "load-buffer"]
        self.assertEqual((code, stdout.getvalue()), (0, "SENT\n"))
        self.assertEqual(len(load), 1)
        self.assertEqual(load[0].kwargs["input_text"], message)

    def test_shell_safe_text_uses_the_same_buffer_path(self) -> None:
        stdout = io.StringIO()
        okay = self.completed()
        message = "simple status wake"
        with (
            mock.patch.object(tmux_send, "resolve_target", return_value=(pane(), "", "")),
            mock.patch.object(tmux_send, "capture_target", return_value=result("CLEAR")),
            mock.patch.object(
                tmux_send,
                "_wait_for_processed_paste",
                return_value=owned(message),
            ),
            mock.patch.object(tmux_send, "_wait_for_clear", return_value=cleared()),
            mock.patch.object(tmux_send, "_tmux", return_value=okay) as tmux_call,
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            code = tmux_send.send_message(
                "s:w.0",
                shell_safe_text=message,
            )
        load = [call for call in tmux_call.call_args_list if call.args[0] == "load-buffer"]
        self.assertEqual((code, stdout.getvalue()), (0, "SENT\n"))
        self.assertEqual(len(load), 1)
        self.assertEqual(load[0].kwargs["input_text"], message)

    def test_bracketed_paste_terminator_is_refused_before_tmux(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            mock.patch.object(tmux_send, "resolve_target") as resolve,
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            code = tmux_send.main(
                ["s:w.0", "--shell-safe-text", "A\x1b[201~B"]
            )
        self.assertEqual(code, 64)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("control character", stderr.getvalue())
        resolve.assert_not_called()

    def test_empty_and_whitespace_only_messages_are_refused_before_tmux(self) -> None:
        for message in ("", "  \n"):
            with self.subTest(message=repr(message)):
                with (
                    mock.patch.object(tmux_send, "resolve_target") as resolve,
                    contextlib.redirect_stdout(io.StringIO()),
                    contextlib.redirect_stderr(io.StringIO()),
                ):
                    code = tmux_send.main(
                        ["s:w.0", "--shell-safe-text", message]
                    )
                self.assertEqual(code, 64)
                resolve.assert_not_called()

    def test_format_only_message_is_refused_before_tmux(self) -> None:
        with (
            mock.patch.object(tmux_send, "resolve_target") as resolve,
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            code = tmux_send.main(
                ["s:w.0", "--shell-safe-text", "\u200b\u2060"]
            )
        self.assertEqual(code, 64)
        resolve.assert_not_called()

    def test_occupied_is_non_idempotent_refusal(self) -> None:
        code, stdout, stderr, tmux_call = self.invoke(initial=owned("draft"))
        self.assertEqual((code, stdout), (1, "OCCUPIED\n"))
        self.assertIn("not assumed idempotent", stderr)
        self.assertIn("nothing sent", stderr)
        self.assertEqual(tmux_call.call_count, 0)

    def test_dim_native_placeholder_refuses_before_buffer_load(self) -> None:
        raw = codex_capture("\x1b[2m[Pasted Content 1834 chars]\x1b[0m")
        composer = tmux_send._composer(raw.splitlines(), WIDTH)
        initial = result(tmux_send.classify_capture(raw, WIDTH), composer)
        code, stdout, _, tmux_call = self.invoke(initial=initial)
        self.assertEqual((code, stdout), (1, "OCCUPIED\n"))
        self.assertEqual(tmux_call.call_count, 0)

    def test_dialog_refuses_without_tmux_mutation(self) -> None:
        code, stdout, stderr, tmux_call = self.invoke(initial=result("DIALOG"))
        self.assertEqual((code, stdout), (2, "DIALOG\n"))
        self.assertIn("nothing sent", stderr)
        self.assertEqual(tmux_call.call_count, 0)

    def test_layout_unknown_names_class(self) -> None:
        initial = tmux_send.CaptureResult("UNKNOWN", "layout", "unrecognized", None)
        code, stdout, stderr, tmux_call = self.invoke(initial=initial)
        self.assertEqual((code, stdout), (3, "UNKNOWN layout\n"))
        self.assertIn("pane shape", stderr)
        self.assertEqual(tmux_call.call_count, 0)

    def test_server_and_target_unknown_name_class(self) -> None:
        for kind in ("server", "target"):
            with self.subTest(kind=kind):
                stdout = io.StringIO()
                stderr = io.StringIO()
                with (
                    mock.patch.object(
                        tmux_send,
                        "resolve_target",
                        return_value=(None, kind, f"{kind} failed"),
                    ),
                    contextlib.redirect_stdout(stdout),
                    contextlib.redirect_stderr(stderr),
                ):
                    code = tmux_send.send_message("s:w.0", self.message_path())
                self.assertEqual((code, stdout.getvalue()), (3, f"UNKNOWN {kind}\n"))
                self.assertIn(f"{kind} failed", stderr.getvalue())

    def test_buffer_failure_is_unknown_buffer(self) -> None:
        code, stdout, stderr, _ = self.invoke(
            initial=result("CLEAR"),
            tmux_result=self.completed(1, "buffer failed"),
        )
        self.assertEqual((code, stdout), (3, "UNKNOWN buffer\n"))
        self.assertIn("buffer failed", stderr)

    def test_paste_failure_is_delivery_unverified(self) -> None:
        okay = self.completed()
        failed = self.completed(1, "paste failed")
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            mock.patch.object(tmux_send, "resolve_target", return_value=(pane(), "", "")),
            mock.patch.object(tmux_send, "capture_target", return_value=result("CLEAR")),
            mock.patch.object(tmux_send, "_tmux", side_effect=[okay, failed, okay]),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            code = tmux_send.send_message("s:w.0", self.message_path())
        self.assertEqual((code, stdout.getvalue()), (4, "DELIVERY_UNVERIFIED paste-failed\n"))
        self.assertIn("do not retry", stderr.getvalue())

    def test_stale_clear_after_paste_never_sends_enter(self) -> None:
        code, stdout, _, tmux_call = self.invoke(
            initial=result("CLEAR"),
            processed_result=result("CLEAR"),
        )
        self.assertEqual((code, stdout), (4, "DELIVERY_UNVERIFIED paste-not-observed\n"))
        self.assertFalse(any(call.args[0] == "send-keys" for call in tmux_call.call_args_list))

    def test_enter_failure_is_delivery_unverified(self) -> None:
        okay = self.completed()
        failed = self.completed(1, "enter failed")
        stdout = io.StringIO()
        with (
            mock.patch.object(tmux_send, "resolve_target", return_value=(pane(), "", "")),
            mock.patch.object(tmux_send, "capture_target", return_value=result("CLEAR")),
            mock.patch.object(tmux_send, "_wait_for_processed_paste", return_value=owned()),
            mock.patch.object(tmux_send, "_tmux", side_effect=[okay, okay, failed]),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            code = tmux_send.send_message("s:w.0", self.message_path())
        self.assertEqual((code, stdout.getvalue()), (4, "DELIVERY_UNVERIFIED enter-failed\n"))

    def test_not_cleared_gets_no_recovery_enter(self) -> None:
        code, stdout, _, tmux_call = self.invoke(
            initial=result("CLEAR"),
            clear_result=owned(),
        )
        send_keys = [call for call in tmux_call.call_args_list if call.args[0] == "send-keys"]
        self.assertEqual((code, stdout), (4, "DELIVERY_UNVERIFIED not-cleared\n"))
        self.assertEqual(len(send_keys), 1)

    def test_dim_placeholder_after_dropped_enter_is_not_sent(self) -> None:
        placeholder = result(
            "CLEAR",
            tmux_send.Composer(
                "codex", "[Pasted Content 100 chars]", True, False
            ),
        )
        code, stdout, _, tmux_call = self.invoke(
            initial=cleared(),
            processed_result=placeholder,
            clear_result=placeholder,
        )
        send_keys = [call for call in tmux_call.call_args_list if call.args[0] == "send-keys"]
        self.assertEqual((code, stdout), (4, "DELIVERY_UNVERIFIED not-cleared\n"))
        self.assertEqual(len(send_keys), 1)

    def test_post_paste_interrupt_has_stable_token(self) -> None:
        okay = self.completed()
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            mock.patch.object(tmux_send, "resolve_target", return_value=(pane(), "", "")),
            mock.patch.object(tmux_send, "capture_target", return_value=result("CLEAR")),
            mock.patch.object(tmux_send, "_tmux", return_value=okay),
            mock.patch.object(
                tmux_send,
                "_wait_for_processed_paste",
                side_effect=KeyboardInterrupt,
            ),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            code = tmux_send.send_message("s:w.0", self.message_path())
        self.assertEqual(
            (code, stdout.getvalue()),
            (4, "DELIVERY_UNVERIFIED interrupted-before-enter\n"),
        )

    def test_second_signal_during_interrupt_cleanup_is_ignored(self) -> None:
        okay = self.completed()

        def tmux_call(*arguments, **_kwargs):
            if arguments[0] == "paste-buffer":
                raise KeyboardInterrupt
            if arguments[0] == "delete-buffer":
                tmux_send._raise_signal(signal.SIGTERM, None)
            return okay

        stdout = io.StringIO()
        with (
            mock.patch.object(tmux_send, "resolve_target", return_value=(pane(), "", "")),
            mock.patch.object(tmux_send, "capture_target", return_value=result("CLEAR")),
            mock.patch.object(tmux_send, "_tmux", side_effect=tmux_call),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            code = tmux_send.send_message("s:w.0", self.message_path())
        self.assertEqual(
            (code, stdout.getvalue()),
            (4, "DELIVERY_UNVERIFIED interrupted-before-enter\n"),
        )

    def test_interrupt_after_enter_does_not_authorize_another_enter(self) -> None:
        okay = self.completed()
        stdout = io.StringIO()
        with (
            mock.patch.object(tmux_send, "resolve_target", return_value=(pane(), "", "")),
            mock.patch.object(tmux_send, "capture_target", return_value=result("CLEAR")),
            mock.patch.object(tmux_send, "_wait_for_processed_paste", return_value=owned()),
            mock.patch.object(tmux_send, "_wait_for_clear", side_effect=KeyboardInterrupt),
            mock.patch.object(tmux_send, "_tmux", return_value=okay) as tmux_call,
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            code = tmux_send.send_message("s:w.0", self.message_path())
        send_keys = [call for call in tmux_call.call_args_list if call.args[0] == "send-keys"]
        self.assertEqual(
            (code, stdout.getvalue()),
            (4, "DELIVERY_UNVERIFIED interrupted-after-enter\n"),
        )
        self.assertEqual(len(send_keys), 1)

    def test_post_paste_exception_has_stable_token(self) -> None:
        okay = self.completed()
        stdout = io.StringIO()
        with (
            mock.patch.object(tmux_send, "resolve_target", return_value=(pane(), "", "")),
            mock.patch.object(tmux_send, "capture_target", return_value=result("CLEAR")),
            mock.patch.object(tmux_send, "_tmux", return_value=okay),
            mock.patch.object(
                tmux_send,
                "_wait_for_processed_paste",
                side_effect=RuntimeError("secret pane text"),
            ),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            code = tmux_send.send_message("s:w.0", self.message_path())
        self.assertEqual((code, stdout.getvalue()), (4, "DELIVERY_UNVERIFIED internal-error\n"))

    def test_failure_never_prints_capture_or_exception_text(self) -> None:
        secret = "pane transcript that must stay private"
        stdout = io.StringIO()
        stderr = io.StringIO()
        initial = tmux_send.CaptureResult("UNKNOWN", "layout", "pane shape is not recognized", None)
        with (
            mock.patch.object(tmux_send, "resolve_target", return_value=(pane(), "", "")),
            mock.patch.object(tmux_send, "capture_target", return_value=initial),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            code = tmux_send.send_message("s:w.0", self.message_path(secret))
        self.assertEqual(code, 3)
        self.assertNotIn(secret, stdout.getvalue())
        self.assertNotIn(secret, stderr.getvalue())

    def test_missing_arguments_exit_64_not_dialog(self) -> None:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = tmux_send.main([])
        self.assertEqual(code, 64)
        self.assertIn("usage error", stderr.getvalue())

    def test_help_does_not_reuse_sent_exit_code(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = tmux_send.main(["--help"])
        self.assertEqual(code, 64)
        self.assertNotIn("SENT", stdout.getvalue())

    def test_source_flags_do_not_accept_abbreviations(self) -> None:
        with self.assertRaises(tmux_send.UsageError):
            tmux_send._parser().parse_args(["s:w.0", "--std"])

    def test_signal_after_outcome_decision_is_ignored(self) -> None:
        tmux_send._OUTCOME_DECIDED = True
        tmux_send._raise_signal(15, None)

    def test_missing_tmux_executable_becomes_server_unknown(self) -> None:
        with mock.patch.object(
            tmux_send.subprocess,
            "run",
            side_effect=FileNotFoundError("tmux missing"),
        ):
            identity, kind, detail = tmux_send.resolve_target("s:w.0")
        self.assertIsNone(identity)
        self.assertEqual(kind, "server")
        self.assertIn("tmux missing", detail)


if __name__ == "__main__":
    unittest.main()
