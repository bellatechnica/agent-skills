# Where sessions create git worktrees

Maintainer notes for the worktree rule in the `new-session` skill and its
launch prompts. The skill states the rule; this file records why every agent
CLI the skills launch is told to follow it instead of its own worktree feature.
Only Claude Code's, Codex's and Cursor CLI's worktree features were checked.

## Rule

Every worktree a session edits in, a subagent's included, is created with plain
git at `<repo root>/.agents/worktrees/<new-branch>`, whichever client works in
it, on a new branch from an explicitly named base. A detached worktree, such as a reviewer's,
goes in the same directory under a descriptive name. The directory must be
ignored in the repository, through `.git/info/exclude` when the repository's own
ignore rules do not cover it. No session reads or searches another session's
worktree there, or in `.claude/worktrees/`, where older worktrees and those made
by Claude Code's own tool live.

## Why not each client's own worktree feature

The clients disagree on both where a worktree goes and what it starts from.
Observed 2026-10-31:

| Client | Location | Base |
| --- | --- | --- |
| Claude Code 2.1.316 `EnterWorktree` | `<repo root>/.claude/worktrees/<name>` | `origin/<default branch>` (setting `worktree.baseRef`, default `fresh`) |
| Codex CLI 0.163.0 `--worktree` (behind `--enable worktrees`) | `~/.codex/worktrees/<4-hex id>/<repo name>` | the current commit, detached — no branch |
| Cursor CLI 2026.10.22 `--worktree` | `~/.cursor/worktrees/<repo name>/<name>` | current HEAD unless `--worktree-base` is given |

Sources: Claude Code's tool description; Codex, by creating one in a scratch
repository; Cursor, its `--help`.

These consequences decide the rule:

- **The base must be stated, not defaulted.** `new-session` bases a new
  worktree on the local trunk, or on a named unlanded branch when the work
  depends on it. Claude Code's default is the remote's default branch, which is
  stale whenever local commits have not been pushed. Codex and Cursor take whatever
  HEAD the launching shell happens to be on.
- **A detached worktree has no branch to land.** Codex's worktree gives the
  session no branch to commit on unless it creates one, and the merge and
  cleanup steps name a branch.
- **Home-directory pools need a collision-proof key.** Cursor keys its pool by
  repository name alone, so two repositories with the same name share one
  directory and can collide on a worktree name; Codex avoids that with a random
  id per worktree. A location inside
  the repository cannot collide with another repository's.

A client's own feature also does not get a sandboxed session past the sandbox.
Observed 2026-10-31 with Codex CLI 0.163.0 in a scratch repository, running
`codex exec -s workspace-write` with a prompt to commit one file: at the
repository root the commit failed on a read-only `.git/index.lock`, and in a
worktree Codex created itself with `--worktree` it failed the same way on
`.git/worktrees/<name>/index.lock`. The sandbox keeps the main repository's
`.git` read-only, and every worktree's index and refs live there; it follows,
though only those two locations were tested, that a sandboxed Codex needs
approval to create a worktree or commit in one wherever the worktree is. Codex's worktree
location also could not be moved from the command line: `-c` overrides named
`desktop.git-worktree-root`, `git_worktree_root` and `worktree_root` each
still created it under `~/.codex/worktrees/`.

Plain `git worktree add` puts a worktree exactly where its arguments say, on the
base they name, whichever client runs it, so the skill prescribes it. Switching into a worktree
needs no client tool either: a session that creates one changes directory into
it or works by absolute path.

## Why inside the repository rather than a home-directory pool

The choice is close; these points decide it:

- **Visible to an editor opened on the repository.** A worktree outside the
  repository directory does not appear in an IDE's file tree, so a person
  following a session's work does not see its files. VS Code's search honours
  ignore files by default (`search.useIgnoreFiles`), so an ignored worktree
  directory stays out of its results; other editors were not checked and may
  search ignored directories.
- **No naming scheme.** A pool shared by many repositories needs a key that
  cannot collide (see Cursor above), stated in every launch prompt. Inside the
  repository the path is unique by construction.
- **One lifetime.** Deleting or backing up the repository takes its worktrees
  with it. A pool elsewhere outlives the repository as orphan checkouts, and
  deleting the pool leaves records in the repository that dangle until
  pruned.
- **Sandbox mounts.** A sandbox that mounts the repository directory covers a
  worktree under it, together with the main `.git` the worktree depends on; a
  worktree in the home directory is outside that mount. Not tested.

A location outside the repository would avoid the search exposure and the
per-repository ignore step described below, which is why this could be
revisited if those costs grow.

## Why `.agents/worktrees/` for every client

One directory keeps the rules to one path: a per-client directory makes every
creator choose the right one for the client that will work in the worktree, and
a wrong choice puts warnings and worktrees in different places. The name is
neutral, so a Codex or Cursor session does not write into a directory named
after another client. `.claude/worktrees/`, where Claude Code's own tool creates
worktrees, was the alternative; the gain from sharing it is small, because a
person or session rarely uses that tool in the maintainer's repositories — on 2026-10-31,
one of 26 worktrees under `.claude/worktrees/` across the maintainer's
repositories had a branch named `worktree-<directory>`, the shape that tool
appears to give (inferred from that one worktree, not confirmed). Those worktrees still exist,
so the off-limits rule names `.claude/worktrees/` as well.

## What the location costs

- **Searches from the repo root can reach other sessions' worktrees.** `grep
  -r`, `find` and many glob tools enter the directory whether or not it is
  ignored, and excluding it by name is fragile (`--exclude-dir=.claude` also
  hides the repository's own tracked `.claude/` files). `git grep` searches only
  tracked files, and even with `--untracked --no-exclude-standard` it does not
  descend into a directory holding a `.git` file, but `git grep --no-index`
  enters linked worktrees. Because every per-tool recipe has a case like these,
  the skill states only the rule — never read or search another session's
  worktree — and leaves the tool to the session.
- **The directory must be ignored** in each repository, or every session sees
  it as untracked at the root, and a careless `git add -A` stages a worktree as
  an embedded repository. The `init-repo` skill's ignore file lists it, and
  `.claude/worktrees/` too; for other repositories the skill adds a local exclude before the first
  worktree is created.
