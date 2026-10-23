---
name: new-session
description: Launch a new agent session in its own tmux window - choose the agent CLI and model (the same as this session's unless the user names another, through codex-sbx or claude-sbx when Docker Sandbox or a settings profile is requested), set up its message channel through session-message and tell it to load that skill when the two sessions will communicate, place it at the repo root or in its own new worktree on the right base commit, name it for resume, revive it after it closes, and clean up its worktree and branch once its work has landed, and watch it for stalls while waiting on it. Use whenever a workflow starts a separate session (handoff, implement, review-session, and others); the calling workflow decides the task and who owns it.
---

# Launch a new session

This skill starts a separate agent session and keeps it reachable. It
does not decide what the session works on, who owns the result, or
how it involves the user: the calling workflow (`handoff`, `implement`,
`review-session`, or another) writes that into the prompt.

## 0. Choose the agent

Unless the user names one, launch the same assistant family as this
session: Codex launches `codex`, Claude Code launches `claude`, and
another supported assistant launches its own CLI. An explicit user
choice always wins. Verify that the selected executable exists; if it
does not, report that instead of silently substituting another agent.

## 1. Choose the channel when the sessions will communicate

Decide before launch whether communication is anticipated: will the
new session send anything to another session, or receive anything from
one? Reports, questions, ready branches, review rounds, escalations, a
go signal, and a copy of a recap all count. A session that only works
and reports to the user needs no channel.

When communication is anticipated:

- Select the channel with `session-message` before launch — Relay
  preflight, the announced direct fallback, registration, listeners,
  conditional wake notices, and response delivery — and keep that
  channel for this session's whole life.
- **The launch prompt tells the new session to load the
  `session-message` skill before anything else and follow it for its
  side of the channel.** Without it the session has addresses but not
  the protocol: it does not register, keep a listener, or apply the
  wake rule, and messages to it sit unread.
- Give the new session and this one the exact channel instructions and
  addresses `session-message` specifies, including the selected
  client's listener rule from `agent-relay-message` when Relay is
  selected. Resolve this session's pane with
  `tmux display-message -p -t "$TMUX_PANE" '#S:#I.#P'` and the new
  session's pane by stable window name; these are tmux recovery or
  direct reply addresses. Also exchange each reachable Codex thread UUID
  or exact session name and, between Claude Code sessions, each Claude
  session name. Do not require a native address from a session that has
  no reachable one.
- After launch, maintain this session's listener when Relay is
  selected. The initial user-facing launch report is a commentary
  update when the current client must keep its turn active for that
  listener.

## 2. Decide where the new session works

Three places exist and a new session must not confuse them. Name them
by ABSOLUTE PATH in the prompt — never by the word "main", which is
ambiguous three ways (the branch, the repo root, and a worktree that
happens to be called `main`):

- **The repo root** (the main checkout, e.g. `/home/me/proj`) — where
  read-only work runs. Reading here is free and needs no setup.
- **Another session's worktree** (any linked checkout reported by
  `git worktree list`, including tool-managed paths such as
  `<repo>/.claude/worktrees/`) — **off limits entirely, read or
  write.** These are live workspaces holding uncommitted in-flight
  work that an outside edit corrupts silently. Never let a worktree's
  directory name be mistaken for a branch or for the repo root: if
  one is named after a branch, "based on X" gets read as "inside the
  directory called X", and the session lands in someone's workspace.
- **The new session's OWN new worktree** — the only place it may
  edit anything.

So: work that will EDIT FILES creates its own worktree **from the
start**; read-only work starts at the repo root and creates a
worktree **at the moment it turns into edits, before the first
edit** — never editing where it was reading. One worktree per session:
never point the new session at a worktree another session is using,
and check what is already there (`git worktree list`) before naming
one. **This session's own worktree is not a target either.** If this
session is working in one, never phrase the prompt in a way that points
there — pass the BRANCH to base a new worktree on, plus the absolute
path of the repo root for reading.

**Which commit does the new worktree start from?** A worktree is not
a copy — every worktree in a repo shares one object store — so the
only real choice is the base commit. **Default to the trunk (`main`),
not this session's branch.** The trunk is reviewed and current, while
an unlanded branch can still be rebased, squashed or rejected under
the child; worse, a child based on it carries the parent's commits
into its own merge, so landing the child lands unreviewed parent work
with it. Base on THIS session's branch only when the new session's
work genuinely cannot build or run without commits that have not
landed yet. When it does:

- **commit them first** — a worktree starts from a commit, never from
  a dirty tree, so uncommitted work is not inheritable at all;
- name the BRANCH to base on, never the directory;
- write the coupling into the prompt or brief: the child rebases onto
  the trunk once the parent lands, and must not merge before the
  parent. When the parent lands by squash or rebase merge, the child
  moves only its own commits: `git rebase --onto <trunk> <parent's old
  branch tip>`.

## 3. Launch it in a new tmux window

- Current tmux session name: `tmux display-message -p '#S'`.
- `tmux new-window -d -t '<session>:' -n <slug> -c <repo-root>` (`-d`
  keeps the user's focus where it is; the trailing colon matters — a
  bare `-t <session>` is parsed as a window index and fails once a
  window occupies that index).
- **Pass the model explicitly: default to the SAME model this session
  is running.** Use `codex --model <model>` for Codex or
  `claude --model <model>` for Claude Code. Without the flag the new
  session falls back to a saved default, which can drift as the user
  switches models. Deviate only deliberately — a genuinely mechanical
  task on a cheaper model, or a model the user named — and say so in the
  prompt so the session knows it was chosen, not inherited. For `codex-sbx`
  and `claude-sbx`, the required profile is the explicit model/provider
  choice; do not add `--model` unless the user asks to override that profile.
- **Give the agent session a stable name for later resume.** For Codex,
  send `/rename <window-slug>` once the session is up; revive it with
  `codex resume <window-slug>`. For Claude Code, mint a UUID with
  `uuidgen`, launch with `claude --session-id <uuid>`, append
  `<date> claude <window-slug> <uuid>` to
  `docs/do_not_commit/handoff-sessions.log`, and revive it with
  `claude --resume <uuid>`. Send `/rename <window-slug>` there too so
  its picker exposes the human-readable name. For sandboxed Codex, also append
  `<date> codex-sbx <profile> <window-slug>` so a later resume uses the same
  persistent sandbox.
- Build the launch command for the selected agent, passing the task
  as its initial prompt (write it without apostrophes, or send it
  literally with `send-keys -l`):

      # Codex (the default when this skill runs in Codex)
      codex -C <repo-root> --model <model> "<prompt>"

      # Codex in Docker Sandbox
      codex-sbx <profile> "<prompt>"

      # Claude Code (when this skill runs there or the user requests it)
      claude --session-id <uuid> --model <model> "<prompt>"

      # Claude Code in Docker Sandbox
      claude-sbx <profile> --session-id <uuid> "<prompt>"

  Other explicitly requested assistants use their equivalent workspace,
  model, initial-prompt, naming, and resume options. Do not weaken their
  normal sandbox or approval policy just to make the session unattended.
- For `codex-sbx` and `claude-sbx`, launch from the repo root just as for the
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
  Codex rejects it. Record Claude's profile with its session UUID:

      <date> claude-sbx <profile> <window-slug> <uuid>

  Resume from the same repo root with `codex-sbx <profile> resume
  <window-slug>` or `claude-sbx <profile> --resume <uuid>`. Sandbox stop/start
  preserves the shared VM state; sandbox removal or reset destroys every stored
  login and agent session in it. Do not remove a reused sandbox until every
  session using that repo/agent/profile combination has finished.
- With a brief document and file edits, make the prompt say "create
  your OWN NEW worktree", and name the branch to base it on; "based on
  main" alone is what gets misread as "inside the worktree called main":

      tmux send-keys -t <session>:<slug> -l '<agent-launch> "Read <brief-path>, then create your OWN NEW git worktree based on branch <branch> and work there. Do not edit any existing linked worktree reported by git worktree list, and do not edit the repo root. <constraints>"'
      tmux send-keys -t <session>:<slug> Enter

  Without either — the whole task in the prompt, no worktree. State the
  read-only rule AND its escape hatch in the same breath, or the second
  half gets invented on the spot:

      tmux send-keys -t <session>:<slug> -l '<agent-launch> "<the full task>. You are in the repo root - read it and run things in it, but do NOT edit any file here, and do NOT touch any existing linked worktree reported by git worktree list. If the work turns into edits, create your OWN NEW worktree first and edit only there. <other constraints>. <who to report to, and how>."'
      tmux send-keys -t <session>:<slug> Enter

  Mix as needed (a brief with no worktree, a worktree with no brief).
- Name the repository's agent instructions and the user's global ones
  by path in every prompt, and say they bind. A CLI loads its own
  global file, which may not be the one this session follows, or none.
- When the session will edit in its own worktree, say in the prompt
  that finishing includes cleaning up after itself once its branch has
  landed (§6), unless the user has noted further work on it.

## 4. Report the launch

Tell the user: the window name, how to switch to it, the communication
channel, both Relay slugs when Relay is used, and what the new session
was told to do or wait for.

## 5. Revive a closed session

When a session's window is gone but its work is outstanding
(unmerged branch, undelivered report, review rounds left), **resume the
original session — never spawn a fresh one to re-learn the work.** The
conversation state is the most valuable artifact a session leaves
behind: the diagnosis details, the numbers, the half-made decisions all
survive in it.

- Resume with the same agent that owns the session. For direct Codex, use
  `codex resume <window-slug>`; for sandboxed Codex, find the recorded profile
  in `docs/do_not_commit/handoff-sessions.log` and run
  `codex-sbx <recorded-profile> resume <window-slug>` from the same repo root.
  For Claude Code, find the UUID in
  `docs/do_not_commit/handoff-sessions.log`. Use `claude --resume <uuid>`
  for a direct session, or use
  `claude-sbx <recorded-profile> --resume <uuid>` from the same repo root
  for a sandboxed session. For older unnamed sessions, use that agent's
  resume picker and match the first user message against the launch prompt;
  keyword grep is too noisy because many sessions mention the same docs.
- Send a SHORT catch-up as the next message: only what changed since it
  closed (how far main moved, what landed that overlaps, what to do
  now). It needs the delta, not a reconstruction.
- Before resuming, verify its worktree is clean and no rebase is in
  flight — a fresh session poking the same worktree first can leave
  both confused.
- Use the selected agent's fork command only for the rare case of
  wanting a COPY of a session's context while leaving the original
  resumable (`codex fork <uuid>` or Claude Code's `--fork-session`).

## 6. Clean up once the branch has landed

Finishing includes cleaning up after the work — **unless the user has
said work continues on that branch**, in which case leave everything in
place and say so. Otherwise a session's leftovers outlive it: a stale
worktree, a merged branch, and scratch databases nobody can attribute
months later.

After the merge is confirmed landed (the branch is an ancestor of the
trunk, or, after a squash or rebase merge, its PR shows merged — not
merely "the merger accepted"):

- **Remove the worktree**, run from the repo root, never from inside the
  worktree being removed: `git -C <repo root> worktree remove <path>`,
  then `git -C <repo root> worktree prune`. If the filesystem leaves a
  half-removed directory (this happens on Windows-mounted paths), fix it
  before moving on rather than leaving an unusable entry behind.
- **Delete the branch** with `git -C <repo root> branch -d <branch>` —
  lowercase `-d`, which refuses when commits are unmerged and is
  therefore the safety check, not a formality. If it refuses,
  something did not land: investigate, never reach for `-D` — except
  after a squash or rebase merge, which `-d` cannot see: confirm the
  merged PR's head is this branch's tip, then use `-D`.
- **Drop the scratch databases and fixtures the branch created.** Test
  databases are often per-checkout and per-day, so one worktree can
  leave several; list them by the naming scheme before dropping, and
  drop only those belonging to this checkout — never a name you cannot
  positively attribute.

Report the cleanup in the recap: what was removed, and anything
deliberately kept.

## 7. Watch a session you wait on

Use this when the calling workflow says to: this session is waiting on
something the new session owes it — a ready branch, an escalation, a
review result, a deliverable. A message listener or a completion
watcher does not make the watch unnecessary: a stalled session sends
nothing, so neither ever fires. A session that only reports to the user
needs no watch.

- Two channels, never confused: EVENT watchers (a landing, a run exit,
  a message arriving) re-invoke this session when something completes;
  a LIVENESS poll catches stalls the events will never
  report. On each poll, capture the session's screen, judge progress
  against its last report, and intervene only on stall or error.
- **The poll is ARMED, not intended — and gated on in-flight work.**
  While any watched session owes something, keep one persistent
  heartbeat running that actually re-invokes this session; each tick
  checks every session it watches. Use the client's own mechanism: in
  Claude Code, a Monitor emitting one line about every 30 minutes; in
  Codex, the `wait_agent` timeout that `agent-relay-message`'s Codex
  rule sets is the tick. Where the client has no mechanism that
  re-invokes this session — Codex in direct mode, with no Relay
  listener to wait on — tell the user the watch is not armed. A poll
  held as an intention silently dies with the turn, and an idle waiter
  and an idle worker look identical from outside. Re-arm it first
  thing on any resume that finds such work open. Work waiting on the
  user — a draft PR awaiting their merge, a branch reported ready to
  them, decisions awaiting their approval — is not in flight: the user's message, or a watcher on the
  landing, is the wake. With NOTHING in flight, STOP the tick; a poll
  that only re-reads unchanged state is noise in the operator's
  terminal.
- On a stall, before waking the session, check whether the
  deliverable already EXISTS unrelayed — in the main checkout's
  `do_not_commit/` area or as commits on the session's branch:
  sessions repeatedly finish the artifact, idle, and never send the
  message. The fix is to read the file and proceed, not to ask for it
  again. Judge by the artifact, not by the session's own summary: a
  pane that reads idle can hold an approved branch it never submitted.
- **Escalation ladder per deliverable: wake once; on a second stall
  of the SAME deliverable, tell the user instead of waking a third
  time.** A session that stalls twice on one item will stall a third.
