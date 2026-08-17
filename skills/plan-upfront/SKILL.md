---
name: plan-upfront
description: Plan a task before implementation - explore, surface the requirements upfront (with enumeration artifacts for subsystems whose promises span time or failures), ask few but sufficient question rounds, then save the approved plan to plans/YYYY-MM-DD-<slug>.md. Use when the user wants a written plan before any implementation.
argument-hint: <task to plan>
---

Produce a written, approved plan for the task the user described. Works
for both project-level plans and small ones. This skill does NOT use
Plan Mode — the flow may write markdown (the plan file, enumeration
artifacts) — so the guard is discipline, not the mode: until the user
approves the plan, write nothing except those planning documents, and
do not implement anything unless the user explicitly says to after
approval.

## 1. Explore first

Read the relevant code, docs, and history before asking the user
anything. Never ask a question the codebase can answer. If the repo
keeps requirement/design documents, name the ones this task touches —
as candidates to rule in or out, not assertions — or state that none
apply; the expensive planning failure is recommending something a
design already forbids in as many words.

## 2. Surface the requirements before the design

**The trigger: does what's being built make promises across time or
failures — is "what holds after a crash mid-run, a retry, or a stale
read" part of its spec?** (Schedulers, billing, sync/replication,
incremental caches.) If no — UI, prompt work, content surfaces — skip
this section entirely; the trigger is the promises, not the size.

If yes, the enumeration artifacts are PLAN DELIVERABLES, produced
before implementation. Each costs about an afternoon and replaces weeks
of incident-driven discovery; in one real project's replay, roughly
three-quarters of the eventual acceptance cases were statable before
any design existed, from the product pains alone — the rest are
design-specific interactions that only review contact finds, so spend
foresight here and save review depth for that residue.

- **A behavioral acceptance list**, design-agnostic, written BEFORE a
  design is chosen — statable from the product pains and the cost
  envelope. It becomes the verification list at the end.
- **The state machine as a drawn diagram**, never only a prose arrow
  list — drawing forces the state × event enumeration prose skips.
- **An interference matrix**: everything that writes × everything
  holding a plan or snapshot in flight, each cell naming its guard.
- **A toy simulator** for protocol designs: ~100 lines over a
  five-node example finds ordering-defect classes in an afternoon that
  otherwise surface one production incident at a time.
- **A test-double fidelity review**, once per double: list the
  properties the double has that production lacks (determinism, speed,
  availability, zero cost) and ask which mechanisms silently depend on
  each.
- **An adversarial fixture corpus with replay**: late arrivals,
  mid-window revisions, oversized items, quiet periods — so every hard
  scenario is executable offline in seconds instead of first executed
  by reality.

## 3. Clarifying questions — few rounds, shaped by the task

**Default: ONE round, up front.** Collect every question whose answer
would change the plan and ask them all together via AskUserQuestion
(consecutive calls in the same round if more than 4). Give each
question a recommended default, listed first and marked
"(Recommended)". Decisions too minor for a question go in the plan's
**Assumptions** section, where the user can veto them at approval.

More rounds are allowed only when the task genuinely creates them:

- **A requirement round then a design round**, when requirement
  answers would change WHICH design questions exist — asking both at
  once wastes the design questions the moment a requirement answer
  moves the ground.
- **A further requirement round**, only when an answer opened new
  requirement questions that could not have been asked earlier AND
  whose answers would change the plan.

The bar for every round after the first: its questions must have been
CREATED by the previous round's answers, not merely deferred from it.
After the last round, do not ask again unless an answer genuinely
invalidates the premise of the task.

## 4. Draft the plan

Focus on high-level ideas and non-obvious decisions — not mechanical
steps. Keep it as concise as reasonable for the size of the task;
small tasks get small plans, and sections that don't apply are
omitted. Concrete `file:line` references are encouraged; step-by-step
edit instructions are not.

Cover, where applicable:

- **Goal** — what done looks like, in a sentence or two.
- **Non-goals** — what is explicitly out of scope.
- **Key decisions** — each significant choice (implementation
  approach, technology, design), with rejected alternatives and why
  they lost, about one line each. State decided-but-undocumented
  answers explicitly: silence on a decided question reads exactly like
  silence on an open one, and recruits the next reader into
  re-deciding it.
- **Assumptions** — everything decided without asking.
- **Enumeration artifacts** (when §2 triggered) — the acceptance list
  and diagrams themselves, or where they will live.
- **Sequencing** — the order of work and *why*: which orderings are
  forced by dependencies vs. chosen for risk reduction. If the repo
  maintains requirement/design docs, the doc commit lands before the
  code that implements it.
- **Verification** — how we'll know it worked, especially manual or
  hard-to-automate checks. Where §2 triggered, this is the acceptance
  list.
- **Risks / open questions** — known unknowns that may surface during
  implementation.

## 5. Get approval

Present the full plan in the conversation and ask the user to approve
it. If the user requests revisions or edits the plan, incorporate
them — the approved version is the plan.

## 6. Save the approved plan

Immediately after approval:

1. Write the final approved plan (including any revisions and edits
   from the approval step) to `plans/YYYY-MM-DD-<slug>.md` at the
   project root — unless the repo has a standing plans location or
   naming convention, which wins. Create the directory if needed.
   Never overwrite an existing plan file — if the name collides, add a
   `-2` style suffix.
2. Tell the user where the plan was saved, then **stop**. Do not begin
   implementing unless the user explicitly asks.
