# agent-skills

My personal collection of skills for coding agents. Each one teaches an agent
CLI such as Claude Code or Codex CLI how to do one recurring job the way I
want it done. Some skills are checklists, some are workflows, and some ship a
script that does the job. They are written for my own setup, but none depends
on it.

## What's here

**Coordinating parallel agent sessions**

- `handoff` — hand a work item to a new agent session. It writes a prompt or
  handoff doc, launches the session, and keeps a durable channel to it.
- `tmux-message` — send one message into another agent's tmux pane. The sender
  refuses to type into a busy or unrecognised composer, and checks that the
  message was actually submitted.

**Keeping repositories clean**

- `init-repo` — set up a new project directory: git, a tailored `.gitignore`,
  direnv, a README and a first commit.
- `never-commit` — what must never enter git history (credentials, personal
  identity, machine details, local paths and more), with the signal to search
  for and the usual false positive for each.
- `history-audit` — sweep a repository's whole history for those things and
  price a history rewrite honestly before recommending one.

**Planning**

- `plan-upfront` — explore the task, surface the requirements, ask a few
  rounds of questions, and save the approved plan before writing code.

**Agent CLI housekeeping**

- `token-cost` — work out what a stretch of Claude Code or Codex usage would
  cost at API prices, from the CLI's own session logs.
- `codex-migrate-session` — move a Codex conversation to a new workspace path
  after a repository is moved or renamed.

**Windows and WSL**

- `wsl-service` — run a WSL project as a systemd service, keep WSL alive
  without an open terminal, and expose the service to the local network.

## How skills are structured

Agent CLIs that read a `skills/` directory of `SKILL.md` files can use these
skills; Claude Code and Codex CLI both do. Each subdirectory of `skills/` is
one skill: a `SKILL.md` with YAML frontmatter (`name`, `description`) plus
whatever reference files and scripts it needs.

## Layout

This repository is not the agent's configuration directory. It holds the skills;
the configuration directory reaches them through a symlink, so there is one copy
of each skill and editing it in either place is the same edit.

    ~/.claude/skills  ->  <this repo>/skills

Skills that are not shared live in the same `skills/` directory but are excluded
by `.gitignore`, so they are present on the machine and invisible to git.

## Installing on another machine

Clone the repository, then point the agent's skills directory at it. Back up or
merge anything already there first — this replaces the directory:

    git clone https://github.com/bellatechnica/agent-skills.git ~/src/agent-skills
    mv ~/.claude/skills ~/.claude/skills.bak     # if it exists and holds anything
    ln -s ~/src/agent-skills/skills ~/.claude/skills

Codex CLI reads `~/.codex/skills`; symlink that as well if you use both. A single
directory-level symlink is the reliable form. Symlinking individual skills one
level down depends on the CLI's discovery walk following symlinks, which is not
guaranteed.

## Agent Relay

`handoff` uses Agent Relay as its default durable channel for messages between
coding-agent sessions. It assumes the relay's `agent_relay` tools are configured
in the agent CLI as a Model Context Protocol (MCP) server, and confirms that
with a live tool call before each handoff. When that preflight fails, it
announces a fallback to tmux messaging rather than failing silently; if tmux
cannot reach the other session either, it reports the blocker.

The server, the `agent-relay-message` skill that drives it, and the instructions
for running both, are in the
[agent-relay](https://github.com/bellatechnica/agent-relay) repository.
Install that skill alongside the MCP server. `handoff` relies on it for the
listener protocol and for wake notices, and `tmux-message` follows its fixed
format for those notices.

## Adding a skill

New skills are private by default: they land in `skills/`, match the deny-all
rule in `.gitignore`, and stay untracked until someone opts them in. That is the
safe direction, but it is silent — a skill written months ago can still be
sitting there unshared. `bin/check-skills` is what makes it visible; it lists
every skill directory that is neither tracked nor recorded as deliberately
private, and exits non-zero when it finds one.

To share a skill, add a `!/skills/<name>/` line to `.gitignore` and `git add` it.
To mark one as deliberately private, add its name to `.private-skills` at the
repository root — that file is itself ignored, so the names of private skills are
not published. Verify the split with:

    git ls-files skills | cut -d/ -f2 | sort -u    # exactly the shared skills
    git check-ignore -v skills/<name>/SKILL.md     # which rule excludes a skill

## Do not run `git clean -xdf` here

Private skills are untracked files inside this working tree, and that is exactly
what `git clean -xdf` deletes, without a prompt and without a way back. They are
not in the history, so nothing in git can restore them. Take a copy of `skills/`
before any cleaning operation, or run `git clean` with `--dry-run` first and read
what it plans to remove.

## License

Copyright 2026 Bella Technica. Licensed under the [Apache License 2.0](LICENSE).
