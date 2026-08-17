---
name: handoff
description: Hand off a work item to a new parallel agent session in a new tmux window, defaulting to the same assistant CLI as the spawning session unless the user specifies another. Use a prompt for simple tasks, a handoff doc in a do_not_commit area for complex ones, an isolated worktree for file edits, and coordination constraints when shared resources demand them.
---

# Hand off work to a parallel session

Prefer a session (not a subagent) when the user will steer the work
directly, it spans hours or many commits, or it must survive this
session. Subagents live inside the spawning session and report back to
it, not to the user.

Choose the target agent before sizing the handoff. Unless the user names
one, launch the same assistant family as the spawning session: Codex
launches `codex`, Claude Code launches `claude`, and another supported
assistant launches its own CLI. An explicit user choice always wins.
Verify that the selected executable exists; if it does not, report that
instead of silently substituting another agent.

## 0. Size the handoff first

Two independent choices — make both explicitly, and default to the
cheap side of each:

- **Handoff doc or just a prompt?** A handoff doc exists to give the
  new session something durable to anchor on: multi-step implementation
  breakdowns, design notes and decisions it must respect, spec
  pointers, consumer/call-site inventories, traps, commit order,
  coordination conditions. Write one when the handoff carries more
  than fits comfortably in a prompt, or when the content must outlive
  the first message (the session re-reads it; other sessions can see
  it). **Simple, self-contained tasks need no doc** — put the whole
  task in the spawn prompt and skip section 1. A one-paragraph handoff
  doc is a sign the prompt would have been enough.
- **Worktree or the repo as-is?** Three places exist and a spawned
  session must not confuse them. Name them by ABSOLUTE PATH in the
  prompt — never by the word "main", which is ambiguous three ways (the
  branch, the repo root, and a worktree that happens to be called
  `main`):
  - **The repo root** (the main checkout, e.g. `/home/me/proj`) — where
    read-only work runs. Reading here is free and needs no setup.
  - **Another session's worktree** (any linked checkout reported by
    `git worktree list`, including tool-managed paths such as
    `<repo>/.claude/worktrees/`) — **off limits entirely, read or
    write.** These are live workspaces holding uncommitted in-flight
    work that an outside edit corrupts silently. Never let a worktree's
    directory name be mistaken for a branch or for the repo root: if
    one is named after a branch, "based on X" gets read as "inside the
    directory called X", and the handoff lands in someone's workspace.
  - **The spawned session's OWN new worktree** — the only place it may
    edit anything.

  So: work that will EDIT FILES creates its own worktree **from the
  start**; read-only work starts at the repo root and creates a
  worktree **at the moment it turns into edits, before the first
  edit** — never editing where it was reading.

  **Which commit does the new worktree start from?** A worktree is not
  a copy — every worktree in a repo shares one object store — so the
  only real choice is the base commit. **Default to the trunk (`main`),
  not this session's branch.** The trunk is reviewed and current, while
  an unlanded branch can still be rebased, squashed or rejected under
  the child; worse, a child based on it carries the parent's commits
  into its own merge, so landing the child lands unreviewed parent work
  with it. Base on THIS session's branch only when the handed-off work
  genuinely cannot build or run without commits that have not landed
  yet. When it does:
  - **commit them first** — a worktree starts from a commit, never from
    a dirty tree, so uncommitted work is not inheritable at all;
  - name the BRANCH to base on, never the directory;
  - write the coupling into the handoff doc: the child rebases onto the
    trunk once the parent lands, and must not merge before the parent.

Everything below applies to whichever pieces you chose.

## 1. Write the handoff doc first (when the size warrants one)

Into a `do_not_commit` area of the MAIN checkout (visible to every
session regardless of worktree), named `handoff-<date>-<slug>.md`. The
`handoff-` prefix is what distinguishes it from a session's own working
plan for the same subject, which may sit alongside it.

**Where exactly: follow the directory's own convention, and look before
writing.** A `do_not_commit` area that has grown past a few dozen files
usually sorts them into folders by KIND — `handoffs/`, `findings/`,
`designs/` — in which case the doc goes in the one for handoffs, e.g.
`docs/do_not_commit/handoffs/handoff-2026-03-14-flaky-tests.md`. Where
there are no folders, the top level is right. `ls` the directory and
match what is there; a convention nobody follows decays at the speed
people write, and the writer who has not looked is how it decays.

The doc is best-effort context, not a self-sufficient brief. A session
is not serializable, so polishing toward completeness costs the sender
more than it returns — the receiver pauses and asks when it hits a
real gap (section 2). Carry what the receiver could not reconstruct
or think to ask about, and let the reply channel handle the rest.

- **Spec pointers, not spec**: the committed docs are the spec; list
  exactly which files/sections. The handoff doc holds the breakdown.
- **Binding vs advisory, as two lists**: which requirements are defects
  if violated, and which are suggestions to override freely on finding
  something better. Undifferentiated, a receiver complies slavishly
  with an accident and casually breaks an essential — and it cannot ask
  about a distinction it never sees.
- **Ruled out, with the reason.** Otherwise the receiver re-proposes
  the rejected option, or drifts back into it.
- **Open questions, marked open.** An unstated uncertainty gets
  silently resolved by the receiver, in some other direction.
- **Quote the user verbatim** rather than summarizing their messages.
  Paste is cheaper than paraphrase, and paraphrase is where intent
  dies.
- **Coordination section — only when shared resources are in play**
  (live DB, services, in-flight background jobs of other sessions):
  what the new session must NOT do yet, the concrete wait/verify
  condition (e.g. "no model_calls newer than 15 min", "status file
  updated"), and what is safe immediately (typically: code + offline
  tests on an isolated test database; own worktree). The section must
  also name the coordination channel: the spawning session's tmux pane
  address, so the two sessions can talk instead of only polling. Fully
  independent work needs no coordination section — do not invent wait
  conditions.
- **The rest by handoff type.** IMPLEMENTATION: steps with known traps
  called out, consumer/call-site inventory, test list, commit order
  (respect repo rules like docs-before-code), any migration decision
  already made. DESIGN, INVESTIGATION or RESEARCH: what is already
  decided and fixed, what is genuinely open, what is out of scope, and
  what the deliverable is — a written design, a diagnosis, a
  recommendation. There are no steps to break down yet, so the doc is
  context and boundaries only.

## 2. Spawn the session in a new tmux window

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
  prompt so the session knows it was chosen, not inherited.
- **Give the agent session a stable name for later resume.** For Codex,
  send `/rename <window-slug>` once the session is up; revive it with
  `codex resume <window-slug>`. For Claude Code, mint a UUID with
  `uuidgen`, launch with `claude --session-id <uuid>`, append
  `<date> claude <window-slug> <uuid>` to
  `docs/do_not_commit/handoff-sessions.log`, and revive it with
  `claude --resume <uuid>`. Send `/rename <window-slug>` there too so
  its picker exposes the human-readable name.
- Build the launch command for the selected agent, passing the handoff
  as its initial prompt (write it without apostrophes, or send it
  literally with `send-keys -l`):

      # Codex (the default when this skill runs in Codex)
      codex -C <repo-root> --model <model> "<prompt>"

      # Claude Code (when this skill runs there or the user requests it)
      claude --session-id <uuid> --model <model> "<prompt>"

  Other explicitly requested assistants use their equivalent workspace,
  model, initial-prompt, naming, and resume options. Do not weaken their
  normal sandbox or approval policy just to make the handoff unattended.
- With a handoff doc and file edits, make the prompt say "create your
  OWN NEW worktree", and name the branch to base it on; "based on main"
  alone is what gets misread as "inside the worktree called main":

      tmux send-keys -t <session>:<slug> -l '<agent-launch> "Read <handoff-doc-path>, then create your OWN NEW git worktree based on branch <branch> and implement it there. Do not edit any existing linked worktree reported by git worktree list, and do not edit the repo root. <constraints>"'
      tmux send-keys -t <session>:<slug> Enter

  Without either — the whole task in the prompt, no worktree. State the
  read-only rule AND its escape hatch in the same breath, or the second
  half gets invented on the spot:

      tmux send-keys -t <session>:<slug> -l '<agent-launch> "<the full task>. You are in the repo root - read it and run things in it, but do NOT edit any file here, and do NOT touch any existing linked worktree reported by git worktree list. If the work turns into edits, create your OWN NEW worktree first and edit only there. <other constraints>. Report back to the user when done."'
      tmux send-keys -t <session>:<slug> Enter

  Mix as needed (a handoff doc with no worktree, a worktree with no doc).

- When there ARE coordination constraints, repeat the hard rule inline
  in the prompt (e.g. "edit code and run the offline suite only; do not
  touch the live DB until the doc's Coordination condition holds") —
  don't rely on the session reading the doc carefully enough.
  Unconstrained handoffs omit this.
- Tell the session how to involve the user:
  - **Larger features** (or whenever the user asked for a plan): refine
    the plan first and present it to the USER for review before
    implementing — do not start building on the handoff doc alone. Tell
    the session to run the `plan-upfront` skill for this.
  - **Everything else**: start directly — the session itself judges
    when the work is worth stopping. The moment it turns up a real
    decision, it pauses and asks instead of guessing: gaps in the
    handoff itself go to the sender's pane (the context holder); calls
    the sender cannot settle — product-visible behavior, revising a
    committed decision — go to the user. Work that never surfaces one
    runs straight through. Either way it ends with a short RECAP to
    the user — what changed, key decisions, how it was verified,
    anything pending. The user does not read the handoff doc; the
    recap is their record.
  Say which case applies when writing the prompt.
- Say in the prompt that ownership runs past the merge: once the branch
  lands, the session cleans up its own worktree, branch and scratch
  databases (section 5) unless the user has noted further work on it.
- Give the new session a reply address: your own pane from
  `tmux display-message -p -t "$TMUX_PANE" '#S:#I.#P'`, with the
  instruction to report back to it. Delivery mechanics — addressing,
  inspecting the pane before typing, sending, backing off when the line
  is occupied, verifying — are the `tmux-message` skill; invoke it
  before your first send and tell the spawned session to do the same.
  Optional for independent work (a completion ping is still nice);
  REQUIRED when coordination constraints exist, and two-way: the
  spawned session pings you when it reaches the blocked step or is
  ready, and you ping it (plus update the durable signal file) the
  moment the blocking condition clears — neither side should discover
  state changes only by polling.

## 3. Report and maintain the signal

- Tell the user: window name, how to switch to it, and what the new
  session was told to wait for.
- One worktree per session — never point the new session at a worktree
  another session is using, and check what is already there
  (`git worktree list`) before naming one. Sessions doing read-only work
  share the repo root harmlessly; only editors need isolation.
- **Your own worktree is not a handoff target.** If this session is
  itself working in one, never phrase the prompt in a way that points
  there — pass the BRANCH to base a new worktree on, plus the absolute
  path of the repo root for reading.
- If a coordination signal exists: update it (status file / message)
  when the blocking work in this session finishes, so the waiting
  session can proceed.

## 4. Hands off after the handoff

The handoff transfers OWNERSHIP. The spawned session owns its branch
end to end — including reporting readiness to the user and running the
merge flow itself when a user-originated authorization arrives —
directly from the user, or relayed by another session passing the
user's instruction on (multi-hop and conditional relays count: e.g.
"review, then ask it to merge if good"). A session's own initiative
never authorizes a merge; the chain must start at the user. The spawning session does
not shepherd, batch, or relay other sessions' merges, and does not act
as a standing manager or message hub for them. Coordinate only when
absolutely necessary: a shared-resource condition from the handoff
doc's Coordination section (GPU, live DB, services), or a direct conflict
between sessions. When a spawned session reports READY, relay that to
the user and stop — what happens next is between the user and that
session.

## 4b. Reviving a closed session

When a handed-off session's window is gone but its work is outstanding
(unmerged branch, undelivered report), **resume the original session —
never spawn a fresh one to re-learn the work.** The conversation state
is the most valuable artifact a session leaves behind: the diagnosis
details, the numbers, the half-made decisions all survive in it.

- Resume with the same agent that owns the session. For Codex, use
  `codex resume <window-slug>`. For Claude Code, find the UUID in
  `docs/do_not_commit/handoff-sessions.log` and use
  `claude --resume <uuid>`. For older unnamed sessions, use that
  agent's resume picker and match the first user message against the
  spawn prompt; keyword grep is too noisy because many sessions mention
  the same docs.
- Send a SHORT catch-up as the next message: only what changed since it
  closed (how far main moved, what landed that overlaps, what to do
  now). It needs the delta, not a reconstruction.
- Before resuming, verify its worktree is clean and no rebase is in
  flight — a fresh session poking the same worktree first can leave
  both confused.
- Use the selected agent's fork command only for the rare case of
  wanting a COPY of a session's context while leaving the original
  resumable (`codex fork <uuid>` or Claude Code's `--fork-session`).

## 5. Clean up once the branch has landed

Tell the spawned session, in the prompt, that finishing includes
cleaning up after itself — **unless the user has said work continues on
that branch**, in which case leave everything in place and say so.
Otherwise a session's leftovers outlive it: a stale worktree, a merged
branch, and scratch databases nobody can attribute months later.

After the merge is confirmed landed (the branch is an ancestor of the
trunk — not merely "the merger accepted"):

- **Remove the worktree**, run from the repo root, never from inside the
  worktree being removed: `git -C <repo root> worktree remove <path>`,
  then `git -C <repo root> worktree prune`. If the filesystem leaves a
  half-removed directory (this happens on Windows-mounted paths), fix it
  before moving on rather than leaving an unusable entry behind.
- **Delete the branch** with `git -C <repo root> branch -d <branch>` —
  lowercase `-d`, which refuses when commits are unmerged and is
  therefore the safety check, not a formality. If it refuses,
  something did not land: investigate, never reach for `-D`.
- **Drop the scratch databases and fixtures the branch created.** Test
  databases are often per-checkout and per-day, so one worktree can
  leave several; list them by the naming scheme before dropping, and
  drop only those belonging to this checkout — never a name you cannot
  positively attribute.

Report the cleanup in the recap: what was removed, and anything
deliberately kept.
