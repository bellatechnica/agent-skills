# agent-skills

Skills for agent CLIs that read a `skills/` directory of `SKILL.md` files —
Claude Code and Codex CLI both do. Each subdirectory of `skills/` is one skill:
a `SKILL.md` with YAML frontmatter (`name`, `description`) plus whatever
reference files and scripts it needs.

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

    git clone <remote> ~/src/agent-skills
    mv ~/.claude/skills ~/.claude/skills.bak     # if it exists and holds anything
    ln -s ~/src/agent-skills/skills ~/.claude/skills

Codex CLI reads `~/.codex/skills`; symlink that as well if you use both. A single
directory-level symlink is the reliable form. Symlinking individual skills one
level down depends on the CLI's discovery walk following symlinks, which is not
guaranteed.

## Agent Relay

Two skills here depend on a service that does not live in this repository.
`agent-relay-message` exchanges messages between coding-agent sessions through
Agent Relay, and `handoff` uses that channel by default, falling back to tmux
only when asked for it explicitly. Both assume the relay's `agent_relay` tools
are already configured in the agent CLI as a Model Context Protocol (MCP)
server, and neither substitutes another channel when they are missing — a
session without the relay configured will report the gap rather than route
around it.

The server itself, and the instructions for running it and pointing a CLI at
it, are in the `agent-relay` repository under the same account as this one.

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
