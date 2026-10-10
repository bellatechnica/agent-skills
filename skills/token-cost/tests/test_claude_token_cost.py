#!/usr/bin/env python3

from __future__ import annotations

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


def line(message_id: str, block: str, usage_object: dict, request_id: str = "req_1") -> str:
    return json.dumps(
        {
            "type": "assistant",
            "uuid": f"{message_id}-{block}",
            "requestId": request_id,
            "timestamp": "2026-06-01T00:00:00Z",
            "message": {
                "id": message_id,
                "model": "claude-test",
                "content": [{"type": block}],
                "usage": usage_object,
            },
        }
    )


def read(*files: list[str]):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for index, lines in enumerate(files):
            (root / f"{index}.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
        return claude_token_cost.read_usage(root, START, END)


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


if __name__ == "__main__":
    unittest.main()
