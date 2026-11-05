---
name: plan-upfront
description: Plan a task before implementation - explore, surface the requirements upfront (with enumeration artifacts for subsystems whose promises span time or failures), ask few but sufficient question rounds, drafting the plan in its file from the start (docs/do_not_commit/plans/ or designs/ unless the repository keeps them elsewhere). Use when the user wants a written plan before any implementation.
argument-hint: <task to plan>
---

Produce a written plan for the task the user described. Works for both
project-level plans and small ones. This skill does NOT use Plan Mode —
the flow writes markdown (the plan file, enumeration artifacts) — so the
guard is discipline, not the mode: write nothing except those planning
documents, and implement nothing until the user asks for it to be built.

## 0. Start the plan file

Create the plan file first and draft in it from then on: findings, the
questions and their answers, and the plan itself all go into the file
as they arise, revised in place rather than presented in the
conversation and written out at the end.

- **A design** — when the user or the calling skill calls the document
  one — goes to `docs/do_not_commit/designs/YYYY-MM-DD-<slug>.md` in the
  main checkout; **a plan** goes to
  `docs/do_not_commit/plans/YYYY-MM-DD-<slug>.md`. Where the repository
  already keeps uncommitted plans or designs elsewhere, follow its
  convention instead; a committed plans folder is not a draft's home.
- Never inside a worktree: other sessions cannot read it there, and it
  is deleted with the worktree.
- Before the first write, confirm the file is ignored with
  `git check-ignore -v <path>`. Where it is not, add the uncommitted
  area that holds it (`docs/do_not_commit/`, or the repository's own
  equivalent) to `.git/info/exclude`, never to the tracked
  `.gitignore`, and check again; a tracked rule outranks that file, so
  if it is still not ignored, ask the user where to put it.
- Never overwrite an existing file — if the name collides, add a `-2`
  style suffix.

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
before implementation. Most acceptance cases are statable from the
product pains alone, before any design exists; spend foresight here and
save review depth for the design-specific residue.

- **A behavioral acceptance list**, design-agnostic, written BEFORE a
  design is chosen — statable from the product pains and the cost
  envelope. It becomes the verification list at the end.
- **The state machine as a drawn diagram**, never only a prose arrow
  list — drawing forces the state × event enumeration prose skips.
- **An interference matrix**: everything that writes × everything
  holding a plan or snapshot in flight, each cell naming its guard.
- **A toy simulator** for protocol designs, run against adversarial
  scenarios.
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
would change the plan and ask them all together (Claude Code's
AskUserQuestion where available, in consecutive calls in the same round
if more than 4). Give each
question a recommended default, listed first and marked
"(Recommended)". Decisions too minor for a question go in the plan's
**Assumptions** section, where the user can veto them.

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

## 4. Write the plan

Write it into the plan file, replacing the working notes it has
collected. Carry every answer into Key decisions or Assumptions, and
keep any text the user wrote in the file. Focus on high-level ideas and non-obvious decisions — not
mechanical steps. Keep it as concise as reasonable for the size of the
task; small tasks get small plans, and sections that don't apply are
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
  forced by dependencies vs. chosen for risk reduction.
- **Verification** — how we'll know it worked, especially manual or
  hard-to-automate checks. Where §2 triggered, this is the acceptance
  list.
- **Risks / open questions** — known unknowns that may surface during
  implementation.

## 5. Hand it over

Tell the user where the plan file is, then **stop**, and ask nothing:
the user reviews the file in their own time, and questions, comments
and edits all go into the same file. Do not begin implementing unless
the user explicitly asks; that request accepts the plan as it then
stands, and the `implement` skill takes it from there.

Once the user has accepted a design (says it is done, or asks for it
to be built), ask where it should live beyond the local file: committed
to the repository's design-docs folder (`docs/designs/` where there is
none), published to a document tool the user names, or kept local. To
commit it, move the file (do not copy it) on a branch and worktree of
its own and land it through the repository's usual merge flow; the
user's choice is the authorization, and later revisions land the same
way. To publish it, put the link at the top of the local file and amend
the published copy from then on. Otherwise write "stays local" at the
top.
