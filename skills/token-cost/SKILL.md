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
   - For Codex rollout JSONL, read `references/codex.md` and run `scripts/codex_token_cost.py`.
   - For Claude Code project transcript JSONL (`~/.claude/projects/**/*.jsonl`), read `references/claude-code.md` and run `scripts/claude_token_cost.py`.
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
   - Resolve time-sensitive mappings again for every report. The dated mappings known so far are in `references/codex.md`; check it for an internal model slug even when the user supplies token totals instead of logs.
   - If no current official mapping is available, produce clearly labeled proxy scenarios rather than silently pricing the internal slug.

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
- Do not translate usage credits into dollars without an official conversion that applies to the user's plan.
- Do not round intermediate calculations; round only presentation values.
- Preserve an exact machine-readable result with `--format json` when the user needs auditability.
