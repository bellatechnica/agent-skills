---
name: handoff
description: Hand off a work item to a new parallel agent session, using Agent Relay as the default durable channel, tmux as an announced preflight fallback, and a tmux wake notice only when Relay reports no active recipient listener. Default to the same assistant CLI unless the user specifies another, and launch Codex or Claude Code through codex-sbx or claude-sbx when Docker Sandbox or a settings profile is requested. Use a prompt for simple tasks, a handoff doc in a do_not_commit area for complex ones, an isolated worktree for file edits, and coordination constraints when shared resources demand them.
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

Choose the communication channel before sizing the handoff:

- **Agent Relay is the default durable channel.** Confirm that the
  configured `agent_relay` MCP server answers a live tool call. Choose distinct,
  human-readable slugs for this session and the new session, then call
  `register_session` for this session before launch. Re-registration is safe.
  Invoke the `agent-relay-message` skill and ensure this session has one listener
  after the launch; two-way communication requires both sessions to receive. For
  every successful send or reply, inspect `recipient_waiting_at_send`. A true
  result uses Relay alone. A false result leaves the payload in Relay and permits
  one `tmux-message` wake notice containing only the Relay message ID and an
  instruction to process the inbox and restore exactly one listener. If no tmux
  path reaches the recipient, report that the message is queued but active
  wake-up is unverified. Never resend the payload after an ambiguous Relay
  result.
- **Full tmux messaging is explicit or an announced preflight fallback.** Use it
  when the user requests tmux mode. Also use it when Relay registration or its
  live preflight fails before launch and both sessions are reachable through the
  same tmux server; report the fallback to the user and give both sessions their
  pane addresses. If tmux is unavailable too, report the blocker. Tmux may still
  host a local agent window while Relay carries its payloads; process hosting
  alone does not select tmux messaging.

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
(When such a directory is reorganised, sort every skill reference to
it into POINTERS and DIRECTIVES — only directives matter: a stale
pointer fails visibly the first time someone follows it, where a stale
directive naming a flat write path keeps working and re-scatters the
directory one obedient session at a time. A directive that names a
folder produces a folder; one that names a flat filename produces a
flat directory.)

The doc is best-effort context, not a self-sufficient brief. A session
is not serializable, so polishing toward completeness costs the sender
more than it returns — the receiver pauses and asks when it hits a
real gap (section 2). Carry what the receiver could not reconstruct
or think to ask about, and let the reply channel handle the rest.

- **Spec pointers, not spec**: the committed docs are the spec; list
  exactly which files/sections. The handoff doc holds the breakdown.
- **Name the committed design documents the work touches — required,
  every handoff.** List the relevant files under the repo's designs
  area or state that none apply, and name them as candidates to rule
  in or out, not assertions ("plausibly relevant, not checked" is
  honest and useful). The expensive failure this prevents: a receiver
  recommending something a design forbids in as many words, undetected
  because the brief looked complete.
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
  also name the coordination channel: both Agent Relay slugs by default, plus
  both recovery pane addresses when the sessions share a tmux server; or the
  spawning session's tmux pane address in full tmux mode.
  Fully independent work needs no coordination section — do not invent
  wait conditions.
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
- Build the launch command for the selected agent, passing the handoff
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
  normal sandbox or approval policy just to make the handoff unattended.
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
  its login menu; before an unattended handoff, have the user authenticate
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
- When Relay is selected, give the new session its Agent Relay slug and this
  session's slug. Include this instruction in the initial prompt, substituting
  the actual values:

      Use Agent Relay as the durable source for every actionable inter-session
      message. Register with slug <child-slug> and agent kind <kind>. The
      spawning session's slug is
      <parent-slug>. Use the agent-relay-message skill. Read every pending
      message now, then maintain exactly one background listener using
      wait_for_messages. Acknowledge a message only after processing it. Use
      reply_to_message for responses, and send blockers, clarification requests,
      and completion notices to <parent-slug>. Replace the listener after
      handling its complete result. After every successful send or reply, inspect
      recipient_waiting_at_send. If true, use no tmux message. If false, invoke
      tmux-message and send <recipient-pane> only a wake notice containing the
      Relay message ID and an instruction to process the Relay inbox and restore
      exactly one listener; never copy the actionable payload into the notice.
      The recovery pane addresses are <parent-pane> and <child-pane>. If a pane
      is unreachable, report that Relay queued the message but active wake-up is
      unverified. Never resend through tmux after an ambiguous Relay result.

  Append the listener rule for the selected child client to that initial prompt:

  - **Codex:** use a `gpt-5.6-luna`, low-reasoning background subagent when
    available. Keep the parent turn active on the collaboration wait while the
    listener is blocked; if a user prompt steers the running turn, handle it and
    continue waiting for the same child. Do not return to an idle prompt with a
    live listener.
  - **OpenCode:** start the child with `task(background: true)` and the current
    model. Before launch, verify that the OpenCode process inherits
    `OPENCODE_EXPERIMENTAL_BACKGROUND_SUBAGENTS=true`; a manual `Ctrl+B`
    detachment is not a substitute.
  - **Claude Code:** use a background subagent and request a cheaper model only
    when its provider supports that choice. Let the parent return to the prompt
    only when the running client starts a parent turn on background completion;
    otherwise keep the parent waiting as described for Codex.

  In Relay mode, after launching the child, apply the matching listener and
  conditional-wake rules to this spawning session. The initial user-facing
  handoff report is a commentary update when the current client must keep its
  turn active; do not end the turn and strand the listener merely to produce a
  final response.
- Resolve this session's pane with
  `tmux display-message -p -t "$TMUX_PANE" '#S:#I.#P'` and the child's pane by
  stable window name. In Relay mode these are recovery addresses only. In
  explicit or fallback full-tmux mode they are reply addresses. Every actual
  tmux delivery follows `tmux-message`: invoke it before the first send and tell
  the spawned session to do the same.
- Coordination is two-way in either mode: the spawned session reports when it
  reaches a blocked step or is ready, and the spawning session sends the signal
  as soon as the blocking condition clears. Also update any durable signal
  file; neither side should learn state changes only by polling.

## 3. Report and maintain the signal

- Tell the user: window name, how to switch to it, the communication channel,
  both relay slugs when relay is used, and what the new session was told to wait
  for.
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

- Resume with the same agent that owns the session. For direct Codex, use
  `codex resume <window-slug>`; for sandboxed Codex, find the recorded profile
  in `docs/do_not_commit/handoff-sessions.log` and run
  `codex-sbx <recorded-profile> resume <window-slug>` from the same repo root.
  For Claude Code, find the UUID in
  `docs/do_not_commit/handoff-sessions.log`. Use `claude --resume <uuid>`
  for a direct session, or use
  `claude-sbx <recorded-profile> --resume <uuid>` from the same repo root
  for a sandboxed session. For older unnamed sessions, use that agent's
  resume picker and match the first user message against the spawn prompt;
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

## 6. Receiving a routed question

**Rule a routed question OUT of your area before answering it inside
it.** A receiver who checks whether the question is even theirs, with
evidence, beats one who answers it well — an item routed as "a
question about your subsystem" has turned out to be a test defect, and
establishing that first is what made the fix small and correct.
