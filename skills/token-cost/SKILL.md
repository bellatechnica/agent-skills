---
name: token-cost
description: Calculate API-equivalent token costs and, for Codex, usage credits split by Fast and Standard mode from rollout JSONL, Claude Code project transcript JSONL, other agent logs, or supplied token totals. Use when a user asks how much model usage cost over a time window, wants Codex Fast-mode versus Standard-mode usage, wants costs broken down by model or token component, needs fork/replay-safe Codex or Claude Code accounting (including Claude's cache-write TTL split), or wants a current-price proxy range for internal model slugs.
---

# Token Cost

Produce a reproducible API-equivalent estimate and, where the provider publishes them, usage credits. Do not present either as an invoice or an additional charge.

## Workflow

1. Resolve the window precisely.
   - Require or infer the year and IANA timezone from reliable context.
   - Convert the boundary to an absolute timestamp before filtering.
   - For a live "since" question, prefer the exact timestamp of the user's request as the end. This excludes tokens spent calculating the answer and makes the result reproducible.
   - If the exact request timestamp is unavailable, use the current time and label it explicitly.

2. Identify the source format.
   - For Codex rollout JSONL, run `scripts/codex_token_cost.py`.
   - For Claude Code project transcript JSONL (`~/.claude/projects/**/*.jsonl`), run `scripts/claude_token_cost.py`.
   - Treat each provider parser as an adapter. Normalize its events to: timestamp, model, service tier when represented, turn, uncached input, cache write, cache read, and output; keep pricing and reporting provider-neutral.
   - For another provider's logs, inspect the schema before adding a separate adapter; do not copy Codex's fork/replay assumptions or Claude's cache-write TTL split onto a provider whose logs don't expose the equivalent concept.
   - For user-supplied aggregates, calculate directly without inventing missing categories.

3. Fetch current prices from the provider's official documentation.
   - Record rates per million tokens for uncached input, cache write, cache read, and output.
   - For Codex signed in with ChatGPT, also record usage-credit rates and the Fast-mode credit multiplier. Keep these separate from API rates: Fast-mode credits and API Priority processing can use different multipliers.
   - Record per-request long-context thresholds and multipliers when applicable.
   - Never rely on remembered prices for a current estimate.

4. Calculate per request, then aggregate.
   - Apply the request's recorded Fast or Standard tier before aggregating. Do not multiply the whole window when modes are mixed.
   - Apply long-context multipliers to each qualifying request, not to the aggregate.
   - Treat cache-read and cache-write tokens as subsets/categories of input; do not add cache reads to total input again.
   - Treat reasoning output as a diagnostic subset of output unless the provider explicitly bills it separately.

5. Handle private or internal model names honestly.
   - Price public model rows directly.
   - Do not assert that an internal slug maps to a public model without an official source.
   - Resolve time-sensitive mappings again for every report. As dated evidence, OpenAI's official [July 30, 2026 announcement](https://x.com/OpenAI/status/2082878180478910571) identifies the current Codex Auto Review model as GPT-5.6 Luna. If that announcement is still current, map `codex-auto-review` to `gpt-5.6-luna`; do not freeze this mapping permanently.
   - If no current official mapping is available, produce clearly labeled proxy scenarios rather than silently pricing the internal slug.

## Codex Rollout Accounting

Use a command shaped like the following. The shown model mapping, rates, and multipliers are dated examples as of 2026-08-09; refresh them before every real report.

```bash
python3 <skill-dir>/scripts/codex_token_cost.py \
  --sessions-root /home/user/.codex/sessions \
  --since '2026-08-03 20:00:00' \
  --until-message 'recalculate since August 3, 8:00 PM PT' \
  --timezone America/Los_Angeles \
  --rate 'gpt-5.6-sol=5,6.25,0.5,30' \
  --rate 'gpt-5.6-terra=2.5,3.125,0.25,15' \
  --rate 'gpt-5.6-luna=1,1.25,0.1,6' \
  --credit-rate 'gpt-5.6-sol=125,0,12.5,750' \
  --credit-rate 'gpt-5.6-terra=50,0,5,300' \
  --credit-rate 'gpt-5.6-luna=5,0,0.5,30' \
  --fast-multiplier 'gpt-5.6-sol=2,2.5' \
  --fast-multiplier 'gpt-5.6-terra=2,2.5' \
  --fast-multiplier 'gpt-5.6-luna=2,2.5' \
  --proxy 'codex-auto-review=gpt-5.6-luna' \
  --long-context 'gpt-5.6-sol=272000,2,1.5' \
  --long-context 'gpt-5.6-terra=272000,2,1.5' \
  --long-context 'gpt-5.6-luna=272000,2,1.5' \
  --by-project
```

API and credit rate order is `uncached input, cache write, cache read, output`, all per million tokens. Fast-multiplier order is `API multiplier, usage-credit multiplier`. Long-context order is `input-token threshold, input multiplier, output multiplier`. The example rates and multipliers are dated 2026-08-09; refresh every value from official documentation before a real report.

The script implements the non-obvious safeguards:

- Ignore copied fork history before a rollout file's first live `turn_context`.
- Establish a pre-window cumulative baseline for sessions already running at the cutoff.
- Use deltas of `total_token_usage`; do not blindly sum `last_token_usage`, because compaction records can omit its component split.
- Fall back to `last_token_usage` only for the first live sample or a counter reset.
- Track the current model and turn from `turn_context` events.
- Normalize Codex's recorded `default` tier to Standard and `priority` tier to Fast. Carry the active tier forward until an explicit change. For a session's initial unmarked state, backfill only when that turn has exactly one explicit tier marker. Keep ambiguous or unfamiliar tiers unpriced rather than guessing.
- Split rows by model and service tier. A turn that switches modes can appear in both detail rows but counts once in the total.
- Count unique turns separately from sampling calls.
- Read every rollout file, including concurrent and resumed sessions; do not select files by modification time.

**Breaking Codex totals down by project folder:** add `--by-project`. Each token delta is assigned to the working directory in the active live `turn_context`, rather than to a rollout file's initial directory. Directories that resolve to the same filesystem object are merged; if a formerly used path cannot be statted, keep it as a distinct path rather than guessing. Text output adds a project-folder table with turns, token categories, API-equivalent cost, and usage credits. JSON model rows include `service_tier`, `api_cost`, and `usage_credits`; the top-level and per-project objects identify unpriced API and credit model/mode combinations separately.

## Claude Code Transcript Accounting

Use a command shaped like the following. The shown rates are dated examples as of 2026-08-04 (per-million-token USD: standard tier, `claude-opus-5` $5 input / $25 output, `claude-fable-5` $10 input / $50 output; cache read = 0.1x input, cache write 5-minute TTL = 1.25x input, cache write 1-hour TTL = 2x input); refresh them from current Anthropic pricing before every real report.

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

Rate order is `uncached input, cache write 5m TTL, cache write 1h TTL, cache read, output`, all per million tokens — unlike Codex's single cache-write rate, Claude's transcripts expose the 5-minute vs 1-hour cache TTL split and it is priced separately. Long-context order matches Codex: `input-token threshold, input multiplier, output multiplier` (relevant for requests whose total context — uncached + cache write + cache read — exceeds a model's standard-pricing threshold).

The script implements the non-obvious safeguards:

- Dedup globally across all files by `(message.id, requestId)`. Each content block (text, tool call, ...) of one API response is written as its own JSONL line and repeats the identical `usage` object; summing lines naively multiplies every response's cost by its block count. Resumed and forked sessions also replay prior lines verbatim — with the original timestamps intact — into new session files; global dedup (not a per-file "first live event" cutoff, which Claude's schema has no equivalent marker for) handles both cases with one mechanism.
- Read `cache_creation.ephemeral_5m_input_tokens` / `ephemeral_1h_input_tokens` for the TTL split; fall back to the flat `cache_creation_input_tokens` field as a 5-minute (the default TTL) write only when the split is absent, and record that fallback as a diagnostic.
- Treat `input_tokens` in Claude's `usage` object as already excluding cache read/write — do not subtract cache categories from it.
- Count a "turn" as a live human/subagent prompt: a `user`-type record whose content is a plain string or contains a non-`tool_result` block. Records that are purely `tool_result` blocks are synthetic continuations of the same turn, not new turns; count them toward the enclosing turn only.
- Every `assistant` record observed in this dataset carries `service_tier: "standard"`; if a report ever finds `"priority"` records, price them separately since Anthropic's priority tier has different rates.

**Breaking totals down by project:** add `--by-project` to also group by the top-level directory under `--logs-root` — for Claude Code transcripts that directory is one entry per working-directory the CLI was run from (e.g. `-home-me-proj`), auto-slugified from the absolute path. This prints a project-summary table (project, turns, API $) plus a per-project model breakdown, and adds a top-level `"projects"` key to `--format json` output shaped like `{project: {models: {...}, long_context_requests: {...}, unpriced_models: [...]}}`. Dedup still happens once, globally, in the read pass before events are split by project — a message that (rarely) straddles two project directories is attributed to whichever file the scan reaches first, not double-counted.

## Output Contract

When the fields apply, lead with a Unicode table in this shape:

```text
┌──────────────┬───────┬───────┬─────────────┬────────────┬────────┬───────┬───────────────┐
│ model / mode │ turns │ input │ cache write │ cache read │ output │ API $ │ usage credits │
└──────────────┴───────┴───────┴─────────────┴────────────┴────────┴───────┴───────────────┘
```

Here `input` means uncached input. Include a `total` row. Omit a category only when the source cannot represent it; show an em dash for a represented zero or an unpriced value. For Codex, show Standard and Fast as separate rows and put `API $` and `usage credits` beside each other. Usage credits are provider units, not dollars.

Follow with a cost table when at least two priced components are nonzero:

```text
┌────────────────┬─────┬───────┐
│ component      │ $   │ share │
└────────────────┴─────┴───────┘
```

Use provider-specific component names, including TTL distinctions only when the logs actually expose them. Then state:

- exact local-time window and first/last counted activity;
- pricing source and rates;
- Fast-mode API and usage-credit multipliers, when applicable;
- proxy mappings or unpriced rows;
- whether any long-context multiplier applied;
- that API cost is an API-equivalent estimate and usage credits are not necessarily an additional subscription charge.

## Reliability Rules

- Do not sum cumulative snapshots as independent usage.
- Do not count replayed history in forked sessions.
- Do not use file modification times as usage timestamps.
- Do not double-count cached input or reasoning output.
- Do not silently price an internal model.
- Do not silently treat Unknown service tier as Standard or apply one Fast multiplier to a mixed window.
- Do not translate usage credits into dollars without an official conversion that applies to the user's plan.
- Do not encode a provider-specific parser, cache category, or transient model mapping into the shared report contract.
- Do not round intermediate calculations; round only presentation values.
- Preserve an exact machine-readable result with `--format json` when the user needs auditability.
