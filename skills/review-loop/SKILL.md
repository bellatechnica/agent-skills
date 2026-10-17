---
name: review-loop
description: Iterate on a finished change with an independent reviewer until it is good enough for the cost of a mistake in it - judging the stop level (one pass, no real defects, or fully clean) from the change's circumstances, choosing the reviewer (a review subagent, a persistent review-session, or something else), triaging each finding, and stopping on the stated level. Use after implementing a change, including at the end of the implement skill.
argument-hint: <change to review, e.g. base..tip or branch> [plan path]
---

Get a finished change to the point where another review round is no
longer worth its cost, and say honestly where that point was. This
skill makes two choices — HOW FAR to go (§1) and WHO reviews (§2) —
and then runs the same loop for every reviewer (§3).

The owner of the change runs this loop: the session that implemented
it; when a subagent built it, the session that dispatched the
subagent; or the session that took ownership through a handoff. The
owner makes the fixes, in the change's own worktree. The reviewer is
read-only and never fixes anything.

## 0. Pin the target

- Commit the work first. A review of a moving working tree reviews
  nothing in particular.
- Resolve the change to full commit IDs: the base (the merge base with
  the branch it will land on, not its own upstream) and the tip. Each
  branch gets its own loop; several branches built in parallel are
  several loops.
- Gather what the reviewer is measured against: the plan or design
  path, the user's review criteria, and the decisions a reviewer would
  otherwise re-litigate (rejected alternatives, deliberate trade-offs).
- **The design session.** Where the change implements a plan held by
  a session other than the owner, that design session checks the
  first ready tip against the plan before round one, and signs off on
  the final tip; `implement` describes the role. Its findings travel
  through the handoff's message channel and are triaged like any
  other (§3). Under a coordinator, the coordinator's phase review
  replaces both the first-tip check and the sign-off: send tips to it
  when its dispatch brief says to, and otherwise once the loop has met
  its level. If the design session has closed, tell the reviewer to check
  the change against the plan file as well.

## 1. Judge the stop level

There are three levels:

- **One pass** — one review round; accepted findings fixed and checked
  by the owner; no re-review unless a fix was non-trivial.
- **No real defects** — iterate until the latest round, on the whole
  change, reports nothing the owner accepts as a real defect. Nits and
  preferences may be declined with a one-line reason each.
- **Fully clean** — iterate until the latest round, on the whole
  change, reports no findings at all. A finding the owner would
  decline goes back to the reviewer with evidence until the reviewer
  withdraws it or the user rules on it.

Pick the level from how costly a defect that survives this review
would be. Judge it from the change's own circumstances, not from what
kind of change it is:

- **Blast radius** — what would a defect damage, and whose?
- **Reversibility** — is undoing it a revert, or something that cannot
  be taken back: data written, messages sent, money spent, a published
  release?
- **Later catch** — if a defect slipped past this review, would
  anything after it (the merger's full suite, the first real use)
  expose it quickly, or would it stay silent and be built on? This is
  about the defects the reviewers have NOT found; every reported
  finding is triaged in §3 regardless of level.
- **Dependency** — how much later work will rest on this before anyone
  looks at it again?

Weigh them; they rarely all point one way. The ends are clear: a
defect that would be both hard to undo and silent calls for **fully
clean**; one that is cheap on every count calls for **one pass**.
Everything between is **no real defects**. A one-line README fix is
cheap on every count. A change that writes rows nobody will re-read
for months is expensive even if it is small. A large refactor under a
thorough test suite can be cheaper than its size suggests.

State the level and the one or two circumstances that decided it, then
start. Do not ask; the user overrides when they disagree. The user's
explicit choice always wins.

## 2. Choose the reviewer

The author of a change is never its independent pass — and in
this-session or subagent mode, the session running this loop is the
author for this purpose, since it planned and directed the build.

| Reviewer | Fits when | Watch for |
| --- | --- | --- |
| **Review subagent** — `/code-review` in Claude Code (local levels only; never `--fix` or `--comment`), or the harness's equivalent from `review-session`'s reviewer-routing table | The default: fresh eyes, cheap, no setup. Raise the effort level with the stop level. | It starts from nothing each round, so it does not know the plan or why things were decided. `/code-review` hunts bugs in a diff; where the defects that matter are elsewhere — conformance to a plan, ambiguous instructions in prose, contradictions between documents — brief a general-purpose subagent instead, or as well, with the plan path, the pinned IDs, what to look for, and the read-only rule. |
| **Persistent reviewer** (`review-session` skill) | Many rounds are expected; the change is large enough that rebuilding context every round is the main cost; the subagent's findings keep failing for lack of context (re-raising settled decisions, misreading the design); a reviewer from another model family is wanted, since it catches different defects; or the user wants to watch the reviewer. | Setup cost, and a session to close afterwards. `review-session` runs the rounds and the close-out; pass it the stop level from §1, and put the plan path and any prose, plan-conformance, or cross-document concerns into its review criteria — its reviewer reads only committed design documents on its own. Its reviewer runs a review skill, which hunts code bugs; for a prose-only change, prefer a briefed subagent. |
| **Something else** | Security-sensitive code: add `/security-review` in Claude Code. A workstream under a coordinator: its phase review comes on top of this loop. Product or UX judgement no tool can make: ask the user to review that part. A deep multi-agent cloud review (`/code-review ultra`) is user-triggered and billed — suggest it, never launch it. | These add to an independent reviewer; none replaces one. One exception: at the one-pass level, when a handed-off or separate session wrote the code, the design session's plan check may be the single pass. |

Switch reviewers when the rounds say to: after two rounds where most
findings were refuted by context the reviewer lacked, and briefing it
with the settled decisions did not stop it, move from a subagent to a
persistent reviewer; when a reviewer reported clean and a defect
surfaced anyway, add one from another model family. Say when and why
you switched.

## 3. Run rounds

Each round:

1. **Review the whole pinned change**, not only the latest fix — fixes
   break things outside themselves. Give the reviewer the pinned IDs,
   the criteria from §0, and, after the first round, each earlier
   finding with its disposition and evidence, so settled points stay
   settled. A subagent remembers nothing between rounds; this brief is
   its only memory.
2. **Triage every finding**, re-deriving its load-bearing claim from
   the code before acting — a finding is a report, not a fact. Each
   gets exactly one disposition:
   - **Fix** — a real defect. Fix it, run the targeted tests, commit.
   - **Dispute** — wrong, with evidence (code path, test, design
     section). The reviewer rules on the evidence: a persistent
     reviewer directly, a subagent in the next round's brief.
   - **Decline** — real but not worth fixing here: a nit, a
     preference, out of scope. One-line reason.
   - **Defer** — real and worth doing, but not in this change. Record
     where it is tracked and tell the user.

   At the fully-clean level, a decline or a deferral needs the
   reviewer's agreement (given the same way as a dispute ruling) or
   the user's.
   - **Escalate** — a product or design decision. Ask the user (or the
     design session, for a question the plan should have settled); do
     not decide it by implementing one side.
3. **Re-pin** the new tip and check §1's level. A result about an older
   tip, or reviewed under different criteria, is stale: re-run it. The
   one exception is the one-pass level, where the owner's own check of
   a trivial fix lets the round's result stand for the new tip.

The level is met only by the independent reviewer's latest round,
except where §2's one-pass exception makes the design session the
single pass. A fix prompted by the design session's final sign-off
makes a new tip: handle it as §1's level handles any fix — at one pass
the owner checks it and only a non-trivial fix gets another round;
above one pass, run another round. Report only after the sign-off
passes. When the design session's plan check was the single pass,
that check is also the sign-off.

Impose no fixed round count, but watch the shape of the rounds. Real
findings shrinking in severity round by round are a loop converging.
Real findings of the same class in new places each round, or fixes
that keep causing new findings, mean the problem is upstream of the
code — stop, say so, and take it back to the plan or the user rather
than patching another round.

## 4. Report

Tell the user, in this order: whether the stop level was met, and if
not, why the loop stopped; the level and the circumstances that set
it; the reviewer, with any switch and its reason; the final pinned
commit IDs; what was fixed; what was declined, deferred, or escalated,
each with its one-line reason; and residual risk — what no reviewer
examined. Close any persistent reviewer session as `review-session`
directs. Do not merge or publish without an authorization that
originates with the user, given directly or relayed (including a coordinator relaying the user's merge
permission), as `handoff` describes.
