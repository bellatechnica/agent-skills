# Launch a session in Docker Sandbox

Read this when the user requests Docker Sandbox or a settings profile,
which selects the `codex-sbx` or `claude-sbx` launcher. Everything not
covered here — choosing the agent, the channel, the worktree rules, the
launch prompt, cleanup and the stall watch — follows `SKILL.md` in this
skill's directory.

## Model

For `codex-sbx` and `claude-sbx`, the required profile is the explicit
model/provider choice; do not add `--model` unless the user asks to
override that profile.

## Launch

Build the launch command for the selected agent, passing the task as
its initial prompt (write it without apostrophes, or send it literally
with `send-keys -l`):

    # Codex in Docker Sandbox
    codex-sbx <profile> "<prompt>"

    # Claude Code in Docker Sandbox
    claude-sbx <profile> --session-id <uuid> "<prompt>"

For `codex-sbx` and `claude-sbx`, launch from the repo root just as for the
corresponding direct client. The same repo root, agent, and profile reuse one
Docker sandbox and start another agent process there; this is expected. Give
every process a unique tmux window name and Relay slug even when the profile
repeats, plus its normal Codex session name or Claude UUID. Different agents
or profiles select different sandboxes.

The ordinary worktree rule is unchanged. Read-only sessions may share the
repo root. Every session that will edit files creates its OWN new worktree
after launch and moves into it before the first edit; two processes in one
container do not share an editing worktree. Do not launch either wrapper from
a host linked worktree: Docker mounts that directory without the parent
repository's Git metadata, so the sandboxed process cannot use Git there.

The launcher supplies the curated skills and `agent_relay` MCP configuration,
so do not add the Relay server interactively. A new Codex sandbox stops at
its login menu; before an unattended launch, have the user authenticate
inside that sandbox and verify `codex login status` there. Never mount or copy
host Codex credentials. Docker's Codex startup already supplies
`--dangerously-bypass-approvals-and-sandbox`; do not append a duplicate because
Codex rejects it.

## Log the session for resume

Give the session a stable name as `SKILL.md` §3 says, but record the
sandbox entry below in `docs/do_not_commit/handoff-sessions.log` in place
of the direct one. For sandboxed Codex, append
`<date> codex-sbx <profile> <window-slug>` so a later resume uses the same
persistent sandbox. Record Claude's profile with its session UUID:

    <date> claude-sbx <profile> <window-slug> <uuid>

## Resume

For sandboxed Codex, find the recorded profile in
`docs/do_not_commit/handoff-sessions.log` and run
`codex-sbx <recorded-profile> resume <window-slug>` from the same repo root.
For sandboxed Claude Code, find the UUID in the same log and use
`claude-sbx <recorded-profile> --resume <uuid>` from the same repo root.

Sandbox stop/start preserves the shared VM state; sandbox removal or reset
destroys every stored login and agent session in it. Do not remove a reused
sandbox until every session using that repo/agent/profile combination has
finished.
