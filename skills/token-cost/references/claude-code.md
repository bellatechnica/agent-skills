# Claude Code Transcript Accounting

Use a command shaped like the following. The rates shown are dated examples as of 2026-08-04: cache read is 0.1x input, a 5-minute cache write 1.25x input, and a 1-hour cache write 2x input.

```bash
python3 <skill-dir>/scripts/claude_token_cost.py \
  --logs-root /home/user/.claude/projects \
  --since '2026-08-03 20:00:00' \
  --until-message 'recalculate since August 3, 8:00 PM PT' \
  --timezone America/Los_Angeles \
  --rate 'claude-opus-5=5,6.25,10,0.5,25' \
  --rate 'claude-fable-5=10,12.5,20,1,50' \
  --rate 'claude-sonnet-5=3,3.75,6,0.3,15' \
  --rate 'claude-haiku-4-5-20251001=1,1.25,2,0.1,5'
```

Rate order is `uncached input, cache write 5m TTL, cache write 1h TTL, cache read, output`, per million tokens. Long-context order is `input-token threshold, input multiplier, output multiplier`. The threshold applies to a request's total context (uncached + cache write + cache read).

The script implements the non-obvious safeguards:

- Responses are deduplicated globally across all files by `(message.id, requestId)`, which also removes lines replayed into resumed and forked sessions. Each response's usage is taken whole from one line. Report these diagnostics when non-zero: `responses_with_disagreeing_usage_lines` (in-window responses whose lines disagreed), and `chosen_line_input_side_below_another_line` / `chosen_line_output_below_another_line` (the chosen line was not the maximum on that side).
- The TTL split comes from `cache_creation.ephemeral_5m/1h_input_tokens`. A line without a usable split is priced as a 5-minute write and counted in `ttl_unspecified_assumed_5m`. `ttl_split_mismatch` counts splits that do not sum to the flat total. A malformed or zone-less timestamp aborts the run. A response with no timestamped line is dropped and counted in `missing_timestamp`.
- Treat `input_tokens` in Claude's `usage` object as already excluding cache read/write — do not subtract cache categories from it.
- A turn is a live human or subagent prompt. Records that are purely `tool_result` continue the enclosing turn.

The `--rate` values are standard-tier rates. A response whose usage carries any `service_tier` other than `standard` (for example `priority`) goes in its own `<model> / <tier>` row and stays unpriced: that row is listed among the unpriced models, so the total is unpriced too and `--strict-pricing` fails, and the response is counted in `unpriced_service_tier_<tier>`. A response with no tier is priced as standard and counted in `service_tier_unspecified_assumed_standard`. Report both counts when non-zero.

**By project:** `--by-project` groups by the top-level directory under `--logs-root` (one per working directory, slugified, e.g. `-home-me-proj`). It prints a project table and a per-project model breakdown, and adds a top-level `"projects"` key to JSON output. Dedup runs once globally first, so a response straddling two project directories counts once, under the first file scanned.
