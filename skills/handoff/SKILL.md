---
name: handoff
description: Hand a work item and its context to a new parallel agent session - decide between a prompt and a handoff doc in docs/do_not_commit/handoffs/, write the doc (spec pointers, binding versus advisory requirements, ruled-out options, coordination constraints when shared resources demand them), tell the session how to involve the user, and launch it with new-session. By default the new session owns the item and answers to the user; a calling workflow may keep leading it instead. Use when the user wants work handed to another session, or a workflow (implement, coordinator) briefs and launches a session to build something.
---

# Hand off work to a parallel session

A handoff transfers a work item and its context to a new session.
Who owns the work afterwards is §4's setting: the new session by
default, or the sender when a calling workflow keeps leading.
`new-session` launches it: the agent and model, the message channel,
the repo root or its own worktree and the base commit, the tmux window,
resume, and cleanup once its branch has landed. This skill decides what
the new session is given and how it involves the user.

## 0. Prompt or handoff doc?

Write a handoff doc only when the handoff carries more than fits
comfortably in a prompt, or the content must outlive the first message
(the session re-reads it; other sessions can see it). Such content
includes multi-step implementation breakdowns, design notes and
decisions it must respect, spec pointers, consumer and call-site
inventories, traps, commit order, and coordination conditions.
Otherwise put the whole task in the launch prompt and skip section 1.

Whether the session works at the repo root or in its own worktree, and
on which base commit, is `new-session` §2.

## 1. Write the handoff doc first (when the size warrants one)

Into `docs/do_not_commit/handoffs/handoff-<date>-<slug>.md` in the MAIN
checkout (visible to every session regardless of worktree), unless the
repository already keeps handoff docs elsewhere. The `handoff-` prefix
is what distinguishes it from a session's own working plan for the
same subject.

The doc is best-effort context, not a self-sufficient brief: carry what
the receiver could not reconstruct or think to ask about, and leave the
rest to the reply channel (section 2).

- **Spec pointers, not spec — required, every handoff.** The design
  and plan documents are the spec. List exactly which files and
  sections apply (committed, in the main checkout's
  `docs/do_not_commit/`, or published and cited by link), or state
  that none apply. Name them as candidates to rule in or out, not as
  assertions ("plausibly relevant, not checked" is honest and useful).
  The handoff doc holds the breakdown.
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
  also name the coordination channel and both sessions' addresses, as
  `session-message` describes.
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
  sender before anything else and preserves what the trap changed in
  its work, so the change can be inspected and undone.
- Tell the session how to involve the user. It starts directly and
  judges for itself when the work is worth stopping, and which skills
  to use. When the sender wants a plan reviewed by the user before
  building, the task says so, and the session plans first and builds
  once the user approves the plan. The moment it turns up a real
  decision, it pauses and asks instead of guessing: gaps in the handoff
  itself go to the sender (the context holder) at the address the
  prompt gives; calls the sender cannot settle — product-visible
  behavior, revising a committed decision — go to the user. Work that
  never surfaces one runs straight through. It ends with a short RECAP
  to the user — what changed, key decisions, how it was verified,
  anything pending. The user does not read the handoff doc; the recap
  is their record.
- Coordination is two-way in either mode: the spawned session reports when it
  reaches a blocked step or is ready, and the spawning session sends the signal
  as soon as the blocking condition clears. Also update any durable signal
  file; neither side should learn state changes only by polling.

## 3. Report the launch

Report the launch as `new-session` §4 says.

## 4. Ownership

**By default the handoff transfers ownership.** The spawned session
owns its branch end to end — including reporting readiness to the user
and running the merge flow itself once the user authorizes it. The
spawning session does not shepherd, batch, or relay other sessions'
merges, and does not act as a standing manager or message hub for them.

**A calling workflow may keep leading instead** (`implement`'s
separate-session mode, `coordinator`). Its prompt then states the
leading terms: who receives escalations, who checks and signs off on
the branch, whose word it lands on, and what the session sends back.
Those terms replace the defaults here and in §2 wherever they differ:
escalations that §2 would send to the user go to the leader, which
batches them for the user. Whatever the terms leave unstated keeps its
default; in particular the recap still goes to the user.

Under the default, coordinate only when
absolutely necessary: a shared-resource condition from the handoff
doc's Coordination section (GPU, live DB, services), or a direct conflict
between sessions. When a spawned session reports READY, relay that to
the user and stop — what happens next is between the user and that
session.
