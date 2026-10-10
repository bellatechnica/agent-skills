#!/usr/bin/env python3

from __future__ import annotations

import argparse
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).parents[1] / "scripts" / "claude_token_cost.py"
SPEC = importlib.util.spec_from_file_location("claude_token_cost", SCRIPT)
assert SPEC and SPEC.loader
claude_token_cost = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = claude_token_cost
SPEC.loader.exec_module(claude_token_cost)

START = datetime(2026, 1, 1, tzinfo=timezone.utc)
END = datetime(2026, 12, 31, tzinfo=timezone.utc)


def usage(output: int, *, input_tokens: int = 3, read: int = 1000, write_1h: int = 500) -> dict:
    return {
        "input_tokens": input_tokens,
        "cache_creation_input_tokens": write_1h,
        "cache_read_input_tokens": read,
        "output_tokens": output,
        "cache_creation": {"ephemeral_1h_input_tokens": write_1h, "ephemeral_5m_input_tokens": 0},
    }


def line(
    message_id: str,
    block: str,
    usage_object: dict,
    request_id: str = "req_1",
    timestamp: str = "2026-06-01T00:00:00Z",
) -> str:
    return json.dumps(
        {
            "type": "assistant",
            "uuid": f"{message_id}-{block}",
            "requestId": request_id,
            "timestamp": timestamp,
            "message": {
                "id": message_id,
                "model": "claude-test",
                "content": [{"type": block}],
                "usage": usage_object,
            },
        }
    )


def read(*files: list[str], start: datetime = START, end: datetime = END):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for index, lines in enumerate(files):
            (root / f"{index}.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
        return claude_token_cost.read_usage(root, start, end)


class FinalUsagePerResponse(unittest.TestCase):
    STREAMED = [
        line("msg_a", "thinking", usage(10)),
        line("msg_a", "text", usage(120)),
        line("msg_a", "tool_use", usage(413)),
    ]

    def test_response_split_across_lines_counts_the_final_output(self):
        events, diagnostics = read(self.STREAMED)
        self.assertEqual([event["output_tokens"] for event in events], [413])
        self.assertEqual(events[0]["input_tokens"], 3)
        self.assertEqual(events[0]["cache_read_tokens"], 1000)
        self.assertEqual(events[0]["cache_write_1h"], 500)
        self.assertEqual(diagnostics["responses_with_disagreeing_usage_lines"], 1)

    def test_replay_in_a_second_file_is_counted_once(self):
        events, _ = read(self.STREAMED, self.STREAMED[:2])
        self.assertEqual([event["output_tokens"] for event in events], [413])
        events, _ = read(self.STREAMED[:2], self.STREAMED)
        self.assertEqual([event["output_tokens"] for event in events], [413])

    def test_placeholder_zero_copy_does_not_hide_the_real_usage(self):
        zeros = [line("msg_a", "text", usage(0, input_tokens=0, read=0, write_1h=0))]
        for files in ([zeros, self.STREAMED], [self.STREAMED, zeros]):
            events, _ = read(*files)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["output_tokens"], 413)
            self.assertEqual(events[0]["cache_read_tokens"], 1000)
            self.assertEqual(events[0]["cache_write_1h"], 500)

    def test_distinct_responses_are_still_summed(self):
        second = [line("msg_b", "text", usage(7), request_id="req_2")]
        events, diagnostics = read(self.STREAMED, second)
        self.assertEqual(sorted(event["output_tokens"] for event in events), [7, 413])
        self.assertEqual(diagnostics["responses_with_disagreeing_usage_lines"], 1)

    def test_flat_cache_write_survives_an_all_zero_placeholder_breakdown(self):
        placeholder = usage(0, input_tokens=0, read=0, write_1h=0)
        flat_only = {
            "input_tokens": 3,
            "cache_creation_input_tokens": 500,
            "cache_read_input_tokens": 0,
            "output_tokens": 9,
        }
        events, diagnostics = read([line("msg_a", "text", placeholder), line("msg_a", "tool_use", flat_only)])
        self.assertEqual(events[0]["cache_write_5m"] + events[0]["cache_write_1h"], 500)
        self.assertEqual(diagnostics.get("ttl_split_mismatch", 0), 0)
        self.assertEqual(diagnostics["ttl_unspecified_assumed_5m"], 1)

    def test_window_membership_does_not_depend_on_file_order(self):
        early = line("msg_a", "text", usage(10), timestamp="2026-06-01T09:59:50Z")
        late = line("msg_a", "tool_use", usage(400), timestamp="2026-06-01T10:00:10Z")
        start = datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)
        for files in ([[late], [early, late]], [[early, late], [late]]):
            events, _ = read(*files, start=start)
            self.assertEqual(events, [])
        events, _ = read([late], [early, late], start=datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc))
        self.assertEqual([event["output_tokens"] for event in events], [400])

    def test_disagreement_diagnostic_counts_only_responses_in_the_window(self):
        old = [
            line("msg_old", "text", usage(1), timestamp="2026-02-01T00:00:00Z"),
            line("msg_old", "tool_use", usage(5), timestamp="2026-02-01T00:00:01Z"),
        ]
        start = datetime(2026, 6, 1, tzinfo=timezone.utc)
        _, diagnostics = read(old, self.STREAMED, start=start)
        self.assertEqual(diagnostics["responses_with_disagreeing_usage_lines"], 1)

    def test_a_ttl_subkey_first_seen_on_a_later_line_counts_as_disagreement(self):
        first = usage(5, write_1h=500)
        second = usage(5, write_1h=500)
        second["cache_creation"] = {"ephemeral_1h_input_tokens": 500}
        first["cache_creation"] = {"ephemeral_5m_input_tokens": 0}
        _, diagnostics = read([line("msg_a", "text", first), line("msg_a", "tool_use", second)])
        self.assertEqual(diagnostics.get("responses_with_disagreeing_usage_lines", 0), 1)

    def test_identical_lines_with_a_5m_then_1h_breakdown_do_not_disagree(self):
        u = usage(8, write_1h=650)
        u["cache_creation"] = {"ephemeral_5m_input_tokens": 0, "ephemeral_1h_input_tokens": 650}
        _, one = read([line("msg_a", "text", u)])
        _, two = read([line("msg_a", "text", u), line("msg_a", "tool_use", u)])
        self.assertEqual(one.get("responses_with_disagreeing_usage_lines", 0), 0)
        self.assertEqual(two.get("responses_with_disagreeing_usage_lines", 0), 0)

    def test_unparseable_timestamp_on_any_line_aborts_the_read(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            read([line("msg_a", "text", usage(5)), line("msg_a", "tool_use", usage(5), timestamp="garbage")])

    def test_same_write_under_different_ttls_is_priced_once_from_the_flat_total(self):
        a = usage(5, write_1h=0)
        a["cache_creation_input_tokens"] = 500
        a["cache_creation"] = {"ephemeral_5m_input_tokens": 500, "ephemeral_1h_input_tokens": 0}
        b = usage(5, write_1h=500)
        events, diagnostics = read([line("msg_a", "text", a), line("msg_a", "tool_use", b)])
        self.assertEqual(events[0]["cache_write_5m"] + events[0]["cache_write_1h"], 500)
        self.assertEqual(diagnostics["ttl_split_exceeds_flat_total"], 1)

    def test_sub_counter_disagreement_does_not_depend_on_line_order(self):
        zero_5m = usage(5)
        zero_5m["cache_creation"] = {"ephemeral_5m_input_tokens": 0}
        only_1h = usage(5)
        only_1h["cache_creation"] = {"ephemeral_1h_input_tokens": 500}
        for lines in ([zero_5m, only_1h], [only_1h, zero_5m]):
            _, diagnostics = read([line("msg_a", f"b{i}", u) for i, u in enumerate(lines)])
            self.assertEqual(diagnostics.get("responses_with_disagreeing_usage_lines", 0), 1)

    def test_flat_only_and_breakdown_lines_do_not_disagree_in_either_order(self):
        flat_only = {
            "input_tokens": 1,
            "cache_creation_input_tokens": 500,
            "cache_read_input_tokens": 0,
            "output_tokens": 5,
        }
        with_breakdown = usage(5, input_tokens=1, read=0, write_1h=500)
        with_breakdown["cache_creation"] = {"ephemeral_5m_input_tokens": 0, "ephemeral_1h_input_tokens": 500}
        for lines in ([flat_only, with_breakdown], [with_breakdown, flat_only]):
            events, diagnostics = read([line("msg_a", f"b{i}", u) for i, u in enumerate(lines)])
            self.assertEqual(diagnostics.get("responses_with_disagreeing_usage_lines", 0), 0)
            self.assertEqual(events[0]["cache_write_1h"], 500)

    def test_split_is_kept_when_no_flat_cache_write_counter_is_present(self):
        def no_flat(output: int) -> dict:
            u = usage(output)
            del u["cache_creation_input_tokens"]
            u["cache_creation"] = {"ephemeral_5m_input_tokens": 0, "ephemeral_1h_input_tokens": 500}
            return u

        events, diagnostics = read([line("msg_a", "text", no_flat(2)), line("msg_a", "tool_use", no_flat(5))])
        self.assertEqual(events[0]["cache_write_1h"], 500)
        self.assertNotIn("ttl_split_exceeds_flat_total", diagnostics)


if __name__ == "__main__":
    unittest.main()
