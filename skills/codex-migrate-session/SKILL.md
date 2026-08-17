---
name: codex-migrate-session
description: Migrate or fork a Codex CLI session to a different workspace while preserving its conversation context. Use when a repository is moved or renamed, an active thread must continue under another cwd, the default `codex resume` picker no longer shows a thread after a path change, or Codex session context needs a safe local workspace migration without editing internal SQLite or JSONL state.
---

# Codex Session Migration

Preserve context by using Codex's public session commands. Create a fork when the
workspace changes; do not rewrite the original thread's internal metadata.

## Workflow

1. Identify the source session ID and target workspace.
2. Verify that the target directory exists and is the intended workspace.
3. Inspect `codex fork --help` because available flags can vary by CLI version.
4. Choose the operation:
   - Use `codex resume <session-id>` when the workspace has not changed.
   - Use `codex fork -C <target-workspace> <session-id>` when the workspace has changed.
5. Run `codex fork` in a PTY. Wait until Codex reports that the thread was forked and
   displays the target directory, then exit the idle TUI gracefully if the migration
   is being performed on the user's behalf.
6. Record the new session ID printed by Codex during shutdown.
7. From the target workspace, run the default `codex resume` picker and confirm that
   the new thread appears with the cwd filter enabled.
8. Report the new session ID, target workspace, verification result, and whether the
   repository worktree changed.

Example:

```bash
codex fork -C /path/to/new-workspace 00000000-0000-0000-0000-000000000000
```

Resume the migrated thread with:

```bash
codex resume <new-session-id>
```

## Guardrails

- Prefer `codex fork` over copying session files or updating Codex databases.
- Do not edit `state_*.sqlite`, `history.jsonl`, or rollout JSONL files.
- Do not copy transcripts into a repository; they can contain prompts, tool output,
  credentials, and other sensitive context, and copied files are not automatically
  registered with the resume index.
- Do not delete or archive the source thread until the fork is verified.
- Do not claim that `resume -C` permanently rebinds a thread. Verify picker behavior;
  some CLI versions retain the source thread's original cwd.
- Treat path spelling and case normalization as implementation details. Verify using
  the default picker from the actual target directory.
- A fork contains source history available when the fork starts. Continue work in the
  new thread so messages added later to the source are not missed.
- Keep repository migration and session migration separate. Confirm Git status before
  and after session operations.

## Fallbacks

If `codex fork` is unavailable, use `codex resume --all` to locate the source thread
and `codex resume -C <target-workspace> <session-id>` for temporary access. Explain
that this may not rebind the picker, recommend upgrading Codex, and avoid modifying
internal state.

For cross-machine migration, do not copy live Codex databases. Create a concise
handoff summary and start a new session on the destination unless the installed Codex
version provides an explicit export/import workflow.
