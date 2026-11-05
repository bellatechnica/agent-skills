# Launch a session in Docker Sandbox

Read this when the user requests Docker Sandbox or a settings profile,
which selects the `codex-sbx`, `claude-sbx` or `muse-sbx` launcher. Everything not
covered here — choosing the agent, the channel, the worktree rules, the
launch prompt, cleanup and the stall watch — follows `SKILL.md` in this
skill's directory.

## Model

A profile is a directory holding the agent's settings file
(`config.toml` for Codex, `settings.json` for Claude Code or Muse Code),
and it is the
explicit model/provider choice; do not add `--model` unless the user
asks to override that profile. Pass it only as `--profile-dir <dir>`; a profile
the user names is the directory `~/.agents/models/<name>`. A bare first
argument is the agent's prompt, not a profile. Without
`--profile-dir` the sandbox runs the agent on its own defaults, so pass
`--model` as `SKILL.md` §3 says.

A Muse Code profile is not a model choice: its `settings.json` is merged
into the client's own and must be a Muse Code settings file, which carries a
`schema_version` member. Profiles written for Claude Code are not Muse
profiles; never pass one to `muse-sbx`. Always pass `--model` to `muse-sbx`
as `SKILL.md` §3 says.

## Launch

Build the launch command for the selected agent, passing the task as
its initial prompt (write it without apostrophes, or send it literally
with `send-keys -l`):

    # Codex in Docker Sandbox
    codex-sbx --profile-dir <profile-dir> "<prompt>"

    # Claude Code in Docker Sandbox
    claude-sbx --profile-dir <profile-dir> --session-id <uuid> "<prompt>"

    # Muse Code in Docker Sandbox
    muse-sbx --profile-dir <profile-dir> "<prompt>"

For every launcher, launch from the repo root just as for the
corresponding direct client. The same agent, profile name, and repo-root
basename reuse one Docker sandbox and start another agent process there; this
is expected. Give
every process a unique tmux window name and Relay slug even when the profile
repeats, plus its normal Codex or Muse Code session name or Claude UUID. Different agents
or profiles select different sandboxes.

The worktree rules in `SKILL.md` §2 apply unchanged: sessions sharing one
sandbox still each edit only in their own new worktree, created after
launch. Do not launch any of these wrappers from
a host linked worktree: Docker mounts that directory without the parent
repository's Git metadata, so the sandboxed process cannot use Git there.

The launcher supplies the curated skills and `agent_relay` MCP configuration,
so do not add the Relay server interactively. A new Codex sandbox stops at
its login menu; before an unattended launch, have the user authenticate
inside that sandbox and verify `codex login status` there. Never mount or copy
host Codex credentials. Docker's Codex startup already supplies
`--dangerously-bypass-approvals-and-sandbox`; do not append a duplicate because
Codex rejects it. A new Muse Code sandbox likewise stops at its sign-in
menu; have the user complete the browser login inside it before an
unattended launch. `muse-sbx` already starts the client with `--yolo`.

## Log the session for resume

Give the session a stable name as `SKILL.md` §3 says, but record the
sandbox entry below in `docs/do_not_commit/handoff-sessions.log` in place
of the direct one, with the profile directory as an absolute path. For
sandboxed Codex, append `<date> codex-sbx <profile-dir> <window-slug>` so
a later resume uses the same persistent sandbox; sandboxed Muse Code
likewise appends `<date> muse-sbx <profile-dir> <window-slug>`. Record
Claude's profile
directory with its session UUID:

    <date> claude-sbx <profile-dir> <window-slug> <uuid>

## Resume

For sandboxed Codex, find the recorded profile directory in
`docs/do_not_commit/handoff-sessions.log` and run
`codex-sbx --profile-dir <recorded-dir> resume <window-slug>` from the same
repo root. For sandboxed Claude Code, find the UUID in the same log and use
`claude-sbx --profile-dir <recorded-dir> --resume <uuid>` from the same repo
root. For sandboxed Muse Code, run
`muse-sbx --profile-dir <recorded-dir> resume <window-slug>` from the same
repo root.

An entry that records a bare profile name instead of a directory does not
say how the session was launched. Run `sbx ls` (in sandbox names, characters
outside `A-Za-z0-9.+-` become `-`):

- `<agent>-<profile>-<repo-root basename>` was launched with a profile of
  that name: resume with `--profile-dir ~/.agents/models/<profile>`, which
  must be the directory the sandbox was created with, since its mounts are
  fixed when it is created.
- `<agent>-<repo-root basename>` was launched without a profile: resume
  without `--profile-dir`.
- Both names: ask the user which one holds the session.
- Neither name: the session's sandbox is gone, or was created with
  `--name`, which the entry does not record. Ask the user whether they know
  its name, and resume with `--name <that name>` if they do; otherwise
  report the session as unrecoverable rather than launching, since a launch
  would create a new, empty sandbox.

Sandbox stop/start preserves the shared VM state; sandbox removal or reset
destroys every stored login and agent session in it. Do not remove a reused
sandbox until every session using that agent, profile name and repo-root
basename has finished.
