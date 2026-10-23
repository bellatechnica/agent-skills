---
name: handoff
description: Hand off a work item to a new parallel agent session that takes ownership of it - decide between a prompt and a handoff doc in a do_not_commit area, write the doc (spec pointers, binding versus advisory requirements, ruled-out options, coordination constraints when shared resources demand them), tell the session how to involve the user, and launch it with new-session. Use when the user wants work handed to another session, or a workflow dispatches a work item a session will own end to end.
---

# Hand off work to a parallel session

Prefer a session (not a subagent) when the user will steer the work
directly, it spans hours or many commits, or it must survive this
session. Subagents live inside the spawning session and report back to
it, not to the user.

A handoff transfers ownership of a work item to a new session (§4).
`new-session` launches it: the agent and model, the message channel,
the repo root or its own worktree and the base commit, the tmux window,
resume, and cleanup once its branch has landed. This skill decides what
the new session is given and how it involves the user.

## 0. Prompt or handoff doc?

Default to the cheap side. A handoff doc exists to give the
new session something durable to anchor on: multi-step implementation
breakdowns, design notes and decisions it must respect, spec
pointers, consumer/call-site inventories, traps, commit order,
coordination conditions. Write one when the handoff carries more
than fits comfortably in a prompt, or when the content must outlive
the first message (the session re-reads it; other sessions can see
it). **Simple, self-contained tasks need no doc** — put the whole
task in the launch prompt and skip section 1. A one-paragraph handoff
doc is a sign the prompt would have been enough.

Whether the session works at the repo root or in its own worktree, and
on which base commit, is `new-session` §2.

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

- **Spec pointers, not spec**: the design and plan documents are the
  spec — committed files, files in the main checkout's `do_not_commit`
  area, or a published document cited by its link; list exactly which
  files/sections. The handoff doc holds the breakdown.
- **Name the design documents the work touches — required, every
  handoff.** List the relevant ones — under the repo's designs area, in
  the main checkout's `do_not_commit` area, or published and cited by
  link — or state that none apply, and name them as candidates to rule
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
  both native recipient addresses when reachable and both recovery pane
  addresses when the sessions share a tmux server; or both usable direct
  addresses when Relay is unavailable.
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

## 2. Write the prompt and launch

Launch with `new-session`. A handoff always anticipates communication —
the session asks the sender about gaps in the handoff (below) — so the
prompt tells it to load `session-message`, as `new-session` §1 says.
The prompt also carries:

- When there ARE coordination constraints, repeat the hard rule inline
  in the prompt (e.g. "edit code and run the offline suite only; do not
  touch the live DB until the doc's Coordination condition holds") —
  don't rely on the session reading the doc carefully enough.
  Unconstrained handoffs omit this.
- When the handoff names known traps, doc or prompt: a named trap may
  still fire. Tell the session that if one does, it reports it to the
  sender before anything else and saves what the trap changed in its
  work as a patch, so the change can be inspected and undone.
- Tell the session how to involve the user:
  - **Larger features** (or whenever the user asked for a plan), unless
    the handoff already carries a plan the user approved: refine
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
  databases (`new-session` §6) unless the user has noted further work
  on it.
- Coordination is two-way in either mode: the spawned session reports when it
  reaches a blocked step or is ready, and the spawning session sends the signal
  as soon as the blocking condition clears. Also update any durable signal
  file; neither side should learn state changes only by polling.

## 3. Report and maintain the signal

- Report the launch as `new-session` §4 says.
- If a coordination signal exists: update it (status file / message)
  when the blocking work in this session finishes, so the waiting
  session can proceed.

## 4. Hands off after the handoff

The handoff transfers OWNERSHIP. The spawned session owns its branch
end to end — including reporting readiness to the user and running the
merge flow itself once the user authorizes it. By default the spawning session
does not shepherd, batch, or relay other sessions' merges, and does not
act as a standing manager or message hub for them — unless the handoff
itself assigns it a continuing role, which the prompt then states.
Otherwise coordinate only when
absolutely necessary: a shared-resource condition from the handoff
doc's Coordination section (GPU, live DB, services), or a direct conflict
between sessions. When a spawned session reports READY, relay that to
the user and stop — what happens next is between the user and that
session.

## 5. Reviving a closed session

Resume the original session as `new-session` §5 describes — never
spawn a fresh one to re-learn the work.

## 6. Receiving a routed question

**Rule a routed question OUT of your area before answering it inside
it.** A receiver who checks whether the question is even theirs, with
evidence, beats one who answers it well — an item routed as "a
question about your subsystem" has turned out to be a test defect, and
establishing that first is what made the fix small and correct.

