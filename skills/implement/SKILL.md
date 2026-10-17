---
name: implement
description: Implement an approved plan or design by first choosing how to execute it - in this session, in a subagent, in a handed-off session, across several sessions (optionally under a coordinator), or some other way - announcing the choice, then driving the result through review-loop. Use when a plan exists (from plan-upfront, a design doc, an issue, or the conversation) and the user has asked for it to be built.
argument-hint: <plan path or description>
---

Turn an approved plan into a reviewed change: pick the execution mode,
run it, verify what was built, and hand it to `review-loop`. The mode
choice is the part this skill exists for. The wrong mode costs in both
directions: a large job done in one overloaded session loses its
context midway, and a small job split across sessions spends more on
briefing than on building.

## 0. Preconditions

- **A plan, located.** A plan file from `plan-upfront`, a committed
  design document, an issue, or a plan agreed in this conversation.
  Refer to it by path from here on. A plan that will be read outside
  this session — by a subagent, another session, or a reviewer — must
  be a file in the main checkout (committed or not) or in committed
  history; a file inside a worktree is off limits to other sessions. A
  plan that lives only in this conversation is written to the main
  checkout's uncommitted area (its `do_not_commit/`); a plan file
  inside a worktree is moved, not copied, to the same relative path in
  the main checkout, so only one version exists. Every brief cites that
  one path.
- **Authorization to build.** `plan-upfront` stops after saving the
  plan; the user's request to build is the authorization.
- **The plan still holds.** Re-read it against the current code. If
  the trunk moved under it or a premise is now false, say so and fix
  the plan with the user first; no mode rescues a stale plan.

## 1. Choose the execution mode

Answer these from the plan and the repo, not by asking:

- **Size**: how many commits, hours, files?
- **Context**: how much of what makes the work go right exists only
  in THIS session (rejected alternatives, the user's remarks, a
  diagnosis)? How much room is left here?
- **Steering**: will the user want to watch and steer the build, or
  only see the result?
- **Shape**: does the plan split into pieces with separate files that
  can land in any order, or is it one sequence where each step
  depends on the last?
- **Shared resources**: live databases, services, GPUs, long-running
  jobs that two implementers could collide on?
- **Agent**: does the plan or the user call for a different CLI,
  model, or sandbox than this session's?

Then take the cheapest mode that fits. These are defaults, not rules.

| Mode | Fits when |
| --- | --- |
| **This session** | Small or medium; context here matters; the user is steering here; room is left in context. |
| **Subagent** | A bounded, self-contained piece that needs no steering from the user; or keeping this session's context free for review or coordination. Fork when this session's context matters; a fresh agent with a full brief when it does not. Several in parallel only when their files do not overlap. A subagent reports to this session, not the user, and cannot stop to ask the user. |
| **Handoff** (`handoff` skill) | Long — hours or many commits; the user will steer it directly in its own session; it must outlive this session; or a different CLI, model, or sandbox is wanted. |
| **Several sessions** | The plan splits into streams that can run in parallel. Use the `coordinator` skill, where installed, when the streams have ordering dependencies, phase gates, shared live resources, or a design someone must hold them to. Use plain parallel handoffs only when the streams are genuinely independent. |
| **Something else** | A step only the user can do (a login, a hardware action); a multi-agent workflow the user has explicitly opted into; a scheduled or cloud agent for work that must run later or elsewhere. Or no mode at all: the plan is not ready, and the right move is back to `plan-upfront`. |

When this session and a handoff both fit, prefer this session if the
user is steering in this conversation and its remaining context will
hold the whole build; otherwise hand off.

Mixed modes are normal — this session builds the core change while a
subagent writes test fixtures. Name each piece's mode.

**Announce, do not ask.** If the user already named a mode, use it.
Otherwise state the mode and its deciding reason in one line and
start. The user overrides by replying.

## 2. Two review roles

The finished change is examined in two different ways, by two
different parties:

- **The design session** — the session that holds the plan, usually
  the one running this skill. It checks that the change builds what
  the plan says, that every departure from the plan is justified, and
  that questions the plan decided were not reopened. It does this by
  re-deriving claims against the code, not by hunting bugs. It also
  answers design questions while the build runs.
- **The independent reviewer** — hunts for defects inside
  `review-loop`, at the depth `review-loop` chooses.

Who does what depends on the mode:

| Mode | Owns the change and runs `review-loop` | Design session's role |
| --- | --- | --- |
| This session or a subagent | This session | The plan check is §4's verify step. This session is not independent of its own work, so `review-loop` always uses at least one reviewer other than itself. |
| Handoff, or several sessions without a coordinator | The implementing session, on its own branch | Checks the first ready branch against the plan, before the independent review starts, so the reviewer does not spend rounds on work that misses the plan. Then a short sign-off on the final branch: only what changed since its check, and only where it touches the plan's decisions. |
| Under a coordinator | Each implementing session, on its own stream | The coordinator's own review is this role. |
| The design session has closed | Unchanged | The plan file stands in: `review-loop`'s reviewer is told to check the change against it as well. |

## 3. Run it

Rules that hold in every mode:

- **Edits by a subagent or another session happen in a worktree of
  their own**, never in the repo root or in another session's
  worktree; `handoff`'s sizing section has the rules. This session
  edits where it already works unless another session shares that
  checkout; fixes to a branch a subagent built are made in that
  branch's worktree, as `review-loop` says.
- **Nothing writes to a live system** — a production database, a
  deployed service, a published release — until `review-loop` has met
  its level on the code that does the writing.
- **The plan's verification list travels with the work.** Whoever
  implements gets the plan path and its verification section, and
  states expected numbers before running checks.
- **Commit order follows the repo**: where it keeps requirement or
  design documents, the doc commit lands before the code commit that
  implements it.
- **Run targeted tests while iterating**; the full suite belongs to
  the merge gate.

Per mode:

- **This session**: implement, commit, then §4.
- **Subagent**: brief it with the plan path, the worktree or branch,
  what is in and out of scope, the verification list, and what to
  return (branch, commits, checks run with their numbers, anything
  skipped). Review is §4's job, not the subagent's.
- **Handoff**: follow `handoff`, and write these into the prompt:
  - The plan is approved: read the plan file and build it yourself, in
    your own worktree. Do NOT re-plan with `plan-upfront`, and do not
    choose an execution mode again. Before `review-loop`, verify the
    built result as `implement` §4 describes.
  - The continuing role this session keeps, by name: it answers design
    questions, checks the first ready branch against the plan, and
    signs off on the final one. Ask the new session to send its first
    ready branch here before starting `review-loop`, and the final
    branch when the loop ends. Without this assignment `handoff`'s
    default applies and this session would stay out.
  - The new session owns everything else: running `review-loop` on its
    own change, the merge, and its recap to the user.
- **Several sessions**: one brief per stream, each with its own branch
  and worktree and the merge order between streams written into it.
  Under `coordinator`, this session takes that role from here. Without
  it, each stream is a handoff as above.

## 4. Verify, then review

Before `review-loop`, the owner of the change checks what was built,
not what was reported:

- `git status` and `git log` in the implementing worktree: the tree is
  clean, the commits exist, the branch is the one named.
- The diff covers every plan item assigned to this branch (the whole
  plan, unless a stream or piece brief narrowed it) and nothing outside
  that assignment; any departure is justified in a commit message or
  raised now.
- The verification list was run, with numbers that match the stated
  expectations. A missing number is a gap, not a pass.

Then run `review-loop` on the pinned change (base and tip commit IDs),
with the plan path and anything a reviewer must know that the plan
does not say. For a handoff or several sessions, each implementing
session does this for itself.

## 5. Report

Tell the user: the mode used and why; the branch and commits; the
verification numbers; the review outcome from `review-loop` (level,
reviewer, rounds, what was fixed, what was left and why); and any
departure from the plan. In a handoff or several sessions, each
implementing session sends that recap for its own change; this session
reports the mode it chose and the result of its plan check and
sign-off. Do not merge or publish without an
authorization that originates with the user, given directly or
relayed (including a coordinator's standing grant), as `handoff`
describes.
