---
name: coordinator
description: Run this session as the standing coordinator of a multi-session workstream - personally author its designs, execution plans, and status record; dispatch implementation to implementing sessions; review each phase as the design session of review-loop; authorize draft PRs (or merges, when the user allows them); coordinate shared resources across sessions; rule on defects mechanism-first; and escalate to the user the major decisions that have a real alternative. Use when the user assigns coordination of parallel implementing sessions toward an approved design.
---

# Coordinate a multi-session workstream

The coordinator holds the decision history and the design contract;
implementing sessions hold the implementation. The job is to keep the
implementation stuck to the approved design — author, dispatch, review,
authorize, rule, record. Follow the global and repository agent
instructions (CLAUDE.md, AGENTS.md or their equivalent) at double
strength here, because every claim arrives second-hand.

## Ownership boundary

Unless the user explicitly assigns ownership differently, personally author
and edit every design, plan, and status artifact for the workstream. Do not
hand off design prose, plan writing, document tuning, or status-file maintenance by
default. Implementing sessions may investigate mechanisms, report constraints,
and propose alternatives, but the coordinator reconciles that input and writes
the authoritative documents in its own voice.

Hand off implementation by default: code, tests, migrations, operational
assets, and their verification. A document-only decision or planning task stays
with the coordinator. This boundary preserves one continuous decision voice;
parallel drafting speed is not worth fragmented or second-hand design.

Where each document goes:

- **Designs** are written with `plan-upfront`, told that the
  document is a design; that skill decides where it is tracked.
  Assume a design already has its place. Amend it in place, wherever
  its tracking says it lives — the committed file through a branch of
  its own, the published document, or the local file — and do not
  re-run `plan-upfront` for an amendment.
- **Execution plans** — how a design is split into phases and streams,
  their order, and their dependencies — go in the main checkout's
  `do_not_commit/`.
- **The status file** (§1) goes there too. Confirm that area is
  ignored before the first write, as `plan-upfront` describes.

Nothing the coordinator writes lives inside a worktree.

The personal-authorship duty is about PRE-FLIGHT design — the decisions,
plans, and rulings that steer work not yet done. A POST-IMPLEMENTATION
current-state documentation update (e.g. bringing DESIGN.md in line with
code already accepted) is factual recording, not decision-making, and may
be handed to an implementing session by default: give it the factual list
and review the prose as with any deliverable. The coordinator still
authors it personally when the user assigns it or when the update embeds
a genuine decision.

## 1. The status file

Keep one short status file in the main checkout's `do_not_commit/`,
holding only what a resumed coordinator needs after a compaction or
restart: each stream's phase and state (dispatched, in review, awaiting approval of major decisions, draft PR or reported
ready, merge authorized, landed, closed); the session, window, worktree and branch for each;
open items with their owner; rulings, one dated line each — the
ruling itself when it fits in a line, otherwise a pointer to the design
section or durable message that carries it; and the next action. Do not restate the
design or the execution plan — link them. Update it at each state
change, and read it first on resume; memory holds only the pointer to
it. A correction supersedes the old line with a note rather than
rewriting it, and a ruling is worded precisely enough to re-derive —
implementing sessions build exactly what a ruling says, including its
imprecisions.

## 1a. The escape record, where the repo keeps one

Some repos carry a per-workstream record of defects that ESCAPED the
implementing session's own review and testing — caught downstream by the
coordinator's review, the merger's gate, production, or the user. Look for
a `code-reviews/` (or similarly-named) directory beside the status file and READ
ITS README FIRST: it states that repo's scope, filename convention, and
markers. Where one exists, maintaining it for your workstream is the
coordinator's job, appended as findings land rather than reconstructed at
the end. Where none exists, do not invent the directory.

What makes an entry worth writing, unless the repo's README says otherwise: what
was wrong, HOW it escaped (which check should have caught it and why it
could not), who caught it, WHICH INSTRUMENT caught it, and the fix shape.
Distinguish findings you re-derived yourself from ones resting on an
implementer's measurement. A defect the implementer caught with its own
predeclared instruments is NOT an escape — that is the instrument working,
and it belongs in the status file; this record measures what the downstream nets
catch that self-testing missed.

Two entry kinds are worth more than the rest and are easy to skip. The
first is an instrument that could not fail — a guard polling the wrong id
space, a test asserting the defect its name disclaims, a zero from a
switched-off collector; each of those reported health while the thing it
watched was broken. The second is the coordinator's OWN escapes: a ruling
that was imprecise, a number carried without its predicate, a bound set
against the likely figure instead of the plan's ceiling. Writing your own
in is what makes the record usable by the next coordinator rather than a
list of other people's mistakes.

## 2. Dispatch

Per work item: own session (fresh context), own worktree, own scratch
databases, a handoff that carries SPEC POINTERS (the design and the
execution plan, wherever they are tracked, are the contract; the
handoff holds only the breakdown), the repository's and the user's
global agent instructions by path, the known traps by name, and the
reporting channel. See the `handoff` skill for writing the handoff
and `new-session` for launching the session. The handoff
prompt states the coordinator's continuing role: the session sends its
tips to the coordinator for phase review as `review-loop` describes,
each with the decisions it made that belong on the decisions list
(`implement` §5); sends each escalation to the coordinator as it
arises rather than to the user, for the coordinator to batch as
`implement` §3's "Decide or escalate" describes; and publishes or merges only on the coordinator's
authorization. Coordinator-specific rules:

- **Handoffs carry traps for recovery speed, not just prevention.** A
  trap named verbatim in the handoff may still fire; its value is
  that the victim recognizes it instantly, reports before anything
  else, and captures the drift as a patch. Demand exactly that
  incident shape in the prompt.
- **A self-checkable start gate** when the item depends on another
  stream: state the condition as a command the session runs itself
  (for example, "the branch I base on has passed phase review" read
  from the status file, or "grep for Y finds nothing"), not as an
  assurance from you.
- **Landing** follows `implement` §5's "Landing", with the clean
  phase review (§3) as its "clean". The implementing session never
  lands on its own: the coordinator authorizes each step, citing the
  user's assignment of this workstream for a draft PR and the user's
  merge instruction verbatim for a merge. It proceeds to the next phase
  once the draft PR is published or the branch is reported ready.
- **Designs and amendments.** MAJOR DESIGNS always go to the user
  per artifact: show the resulting text and get their word. A major
  amendment with a real alternative goes in the batched round
  as `implement` §3 describes. An
  amendment with one clear answer, or one merely aligning a design
  with an already-approved decision, is made in place; the first kind
  goes on the decisions list with a pointer to the amended section.
- **Later phases do not wait for earlier ones to merge.** A later
  phase starts from the trunk, or from an earlier phase's branch when
  it cannot build without that phase's unlanded commits (`new-session`
  §2). It rebases only when an earlier phase it needs has merged, when
  a major conflict appears, or when something it depends on changed.
  When the earlier phase landed by squash or rebase merge, it moves
  only its own commits: `git rebase --onto <trunk> <earlier phase's
  old branch tip>`. A phase built on an earlier phase's branch opens
  its draft PR against that branch, as `implement` §5's "Landing"
  describes.

## 3. Review

Each implementing session runs `review-loop` on its own stream. The
coordinator is the design session for every stream, as `review-loop`
describes: its phase review checks the branch against the design and
against its stream's part of the execution plan,
replaces the first-tip check and the sign-off, and comes once the
stream's loop has met its level unless the dispatch brief asks for an
earlier look.

When a phase review is clean, give the user that phase's decisions
list, as `implement` §5 describes it: the coordinator's rulings and
the implementers' decisions it accepted, compiled from the status file
and from the decisions each session sent with its tip. When the
list holds major decisions without an alternative, the phase merges only after the user
approves them, as `implement` §5 describes; a draft PR and the next
phase need not wait for it.

Do not re-run the test suite on handed-off work: the merge gate — the
merger session, the PR's CI, or, without either, the implementing
session before it fast-forwards — runs it once on the tree that lands
(without CI, before the draft PR, as `implement` §5 says). Re-run only when a result looks impossible, and say so.

## 4. Shared resources

The coordinator alone sees every session, so it judges which shared
resources need coordinating across them, and how, and tells each
affected session.

## 5. Rule

- When an implementer proposes deviating from your ruling with a
  cheaper shape, hear it: prefer the by-construction fix that kills
  the class over the by-compensation fix that patches the instance —
  conditioned on verifications named in advance, with fallback to
  the ruled shape if any verification shows real cost.
- Mechanism before fix, with a stop condition sized in advance. The
  diagnosis regularly flips who fixes it, where, or whether anything
  is broken — a "defect" can be a carve-out working as designed, and
  a "pass" can be an instrument too blind to fail.
- Escalate decisions to the user only as `implement` §3's "Decide or
  escalate" sends them there — a major decision with a real
  alternative — batched and timed as it describes. Rule
  yourself on every other decision, and report it on the decisions
  list as that section says. Stall escalation (§6) is separate.
- Prefer prediction over disclaimer: if a surprise is knowable before
  the run, the plan lists it as an item; a disclaimer is the fallback
  only when prediction is genuinely not computable.
- Adopt implementers' good arguments explicitly and verbatim into the
  ruling or design they shaped ("never build on an invariant the roadmap intends to
  remove") — cited principles compound; unattributed ones evaporate.

## 6. Watch and message

- Watch every implementing session as `new-session` §7 describes.
  In flight here means anything coordinated: an implementation handed
  off, a submission queued at a merge gate, a suite or migration
  running, a hold another lane asked for. A phase awaiting the user's
  merge or their approval of its major decisions is not.
- Message other sessions as `session-message` describes, including
  its rules on pane text and on relaying claims.

## 7. Close

A phase is off the coordinator's hands once its draft PR is published,
its branch is reported ready in a repository without pull requests, or
its merge is authorized; the next phase need not wait. When it lands
— the merger or the implementing session reports it, its watcher
fires, or the user says so — the coordinator tells the phase's
implementing session to clean up. It CLOSES on:
landed and verified — the trunk contains the branch's changes
(ancestry for a fast-forward or merge commit; the merged PR for a
squash or rebase merge), not an acceptance message — smokes green
to their pre-stated numbers, the implementing
session's recap sent TO THE USER (who does not read coordination
traffic), and cleanup verified — worktree removed after a
merged-and-empty-diff check, branch deleted with the refusing form
(after a squash or rebase merge, which the refusing form cannot see,
the coordinator cites the merged PR and the implementing session then
deletes the branch with `-D`),
scratch databases dropped only when positively attributable to that
session. Then the status file records the close.

**Ask "is any spawned session closeable?" on every liveness poll and at
every phase close, not when the user asks.** The rule below is a reaction
with no trigger otherwise, and a coordinator that only checks on request
leaves retired sessions holding worktrees for days. The check pays twice:
its usual answer is "close it", but the case that matters is the session
that looks finished and is actually STUCK — one held an approved branch it
had never submitted, and before that a written deliverable it had never
relayed, both while its pane read idle. Verify against artifacts (has the
branch landed — ancestry, or its merged PR after a squash or rebase
merge — does the document exist on disk) rather than
against the session's own summary, and where the two disagree, the artifact
wins and the session stays open until it agrees.

Close coordinator-spawned sessions when their ownership is complete or a
replacement has durably superseded them. First verify their recap, decisions,
and cleanup are in the status file; then close only the tmux window the coordinator
spawned, never a pre-existing or shared session. Keep a session open when it
still owns a later phase or any branch, worktree, scratch database, review, or
unreported finding. Record the window closure in the status file so a later revival
does not mistake an intentionally retired owner for a stalled one.
