# Codex Rollout Accounting

Use a command shaped like the following. The shown model mapping, rates, and multipliers are dated examples as of 2026-08-09.

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

API and credit rate order is `uncached input, cache write, cache read, output`, all per million tokens. Fast-multiplier order is `API multiplier, usage-credit multiplier`. Long-context order is `input-token threshold, input multiplier, output multiplier`.

The script implements the non-obvious safeguards:

- The script drops fork history copied before a rollout's first live `turn_context`, baselines sessions already running at the cutoff, and sums deltas of `total_token_usage`, not `last_token_usage`.
- `default` is Standard and `priority` is Fast. A turn with no tier marker is Standard and counted in diagnostics. An unrecognised named tier stays unpriced. Report both.
- A turn that switches modes appears in both detail rows but counts once in the total.
- Every rollout file is read. Never pre-select files by modification time.

**By project:** `--by-project` assigns each token delta to the working directory of the active live `turn_context`. Paths resolving to the same directory merge, and paths that cannot be statted stay distinct. It adds a project-folder table. JSON rows carry `service_tier`, `api_cost` and `usage_credits`, and unpriced API and credit combinations are listed separately.

## Dated model mappings

As dated evidence, OpenAI's official [July 30, 2026 announcement](https://x.com/OpenAI/status/2082878180478910571) identifies the current Codex Auto Review model as GPT-5.6 Luna. If that announcement is still current, map `codex-auto-review` to `gpt-5.6-luna`.
