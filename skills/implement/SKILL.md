---
name: implement
description: Implement an approved plan or design by first choosing how to execute it - in this session, in a subagent, in a separate session this one leads, across several sessions (optionally under a coordinator), or some other way - announcing the choice, then driving the result through review-loop. Use when a plan exists (from plan-upfront, a design doc, an issue, or the conversation) and the user has asked for it to be built.
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
  be a file in the main checkout (committed or not), in committed
  history, or a design `plan-upfront` published to a document tool,
  cited by its link; a file inside a worktree is off limits to other
  sessions. A
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
| **Separate session** (launched with `new-session`; this session leads it) | Long — hours or many commits; it must outlive this session; or a different CLI, model, or sandbox is wanted. |
| **Several sessions** | The plan splits into streams that can run in parallel. Use the `coordinator` skill when the streams have ordering dependencies, phase gates, shared live resources, or a design someone must hold them to. Use plain parallel separate sessions only when the streams are genuinely independent. |
| **Something else** | A step only the user can do (a login, a hardware action); a multi-agent workflow the user has explicitly opted into; a scheduled or cloud agent for work that must run later or elsewhere. Or no mode at all: the plan is not ready, and the right move is back to `plan-upfront`. |

When this session and a separate session both fit, prefer this session if the
user is steering in this conversation and its remaining context will
hold the whole build; otherwise launch a separate session.

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
| Separate session, or several sessions without a coordinator | The implementing session, on its own branch | Checks the first ready branch against the plan, before the independent review starts, so the reviewer does not spend rounds on work that misses the plan. Then a short sign-off on the final branch: only what changed since its check, and only where it touches the plan's decisions. |
| Under a coordinator | Each implementing session, on its own stream | The coordinator's own review is this role. |
| The design session has closed | Unchanged | The plan file stands in: `review-loop`'s reviewer is told to check the change against it as well. |

## 3. Run it

Rules that hold in every mode:

- **Every build happens in a worktree of its own**, created before
  the first edit by whoever builds — or, for a subagent, by this
  session for that subagent alone; `new-session` §2 has the rules,
  including which commit to base it on. Never build in the repo root,
  in a worktree someone else is building in, or in another live
  session's worktree. Other sessions may land on the branch this
  session sits on at any moment, and a commit made there races them.
- **A subagent's worktree passes to the owner when the subagent
  returns.** From then on it is not another session's worktree: the
  owner verifies it (§4) and makes review fixes there, as
  `review-loop` says.
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
- **The agent instructions bind everyone.** Implementers and
  reviewers alike follow the repository's agent instructions (its
  AGENTS.md, CLAUDE.md or equivalent) and the user's global ones.
  Every brief — subagent, separate session, reviewer — names those files by
  path and says they bind: a session in another CLI loads that CLI's
  global file, not this one's.

Per mode:

- **This session**: create its own worktree, implement there, commit,
  then §4.
- **Subagent**: brief it with the plan path, the branch to base its
  own new worktree on (or a worktree created for it alone — never this
  session's own worktree), what is in and out of scope, the verification list, and what to
  return (its worktree path, branch, commits, checks run with their numbers, anything
  skipped, the decisions it made that belong on the decisions list
  (§5), and its escalations, with the work that depends on them left
  unbuilt). Review is §4's job, not the subagent's.
- **Separate session**: launch it with `new-session`. This is not a
  `handoff`: the new session owns its branch, but this session keeps
  leading — it holds the plan, receives escalations, and gates the
  merge — and the prompt below says so. The two sessions communicate, so the prompt tells the
  new session to load `session-message` (`new-session` §1). Write these
  into the prompt as well:
  - The plan is approved: read the plan file and build it yourself, in
    your own worktree. Do NOT re-plan with `plan-upfront`, and do not
    choose an execution mode again. Before `review-loop`, verify the
    built result as `implement` §4 describes.
  - Escalations come here, not to the user, as `implement` §3's
    "Decide or escalate" describes: send each one as it arises, then
    build what does not depend on it; this session batches them for
    the user, even when the user also talks to you directly.
  - The continuing role this session keeps, by name: it answers design
    questions, checks the first ready branch against the plan, signs
    off on the final one, and closes the new session's window once
    its branch has landed (`implement` §6). Ask the new session to send its first
    ready branch here before starting `review-loop`, the final
    branch when the loop ends together with the decisions it made
    that belong on the decisions list (§5), and, after its branch has landed and
    its cleanup is done, a copy of the recap it gave the user.
  - The new session owns everything else: running `review-loop` on its
    own change, landing it, and its recap to the user. It lands only as
    `implement` §5's "Landing" describes, on this session's word —
    never on a clean review alone; a merge also waits until this
    session reports that the decisions list holds no major decisions
    without an alternative, or relays the user's approval of them. Once its branch lands, it cleans up as
    `new-session` §6 describes.
- **Several sessions**: one brief per stream, each with its own branch
  and worktree and the merge order between streams written into it.
  Under `coordinator`, this session takes that role from here. Without
  it, each stream is a separate session as above.

### Decide or escalate

The **leading session** holds the plan and speaks to the user: this
session, in every mode (under `coordinator`, as the coordinator).
Implementing sessions and subagents send their escalations to it, not
to the user. It answers what the plan already settles and batches the
rest, across every stream, for the user — also when the user steers
a separate session directly.

Every decision made during the build or the review falls on one side
of this line:

- **Escalate to the user** only a major decision with a real
  alternative: at least two viable options that give up different
  things the user would weigh. A decision is major when it changes
  the plan or design — adding, dropping, or reshaping a plan item, or
  reversing a decision the plan, a committed design, or the user has
  recorded — or when it touches product-visible behaviour, spend,
  safety or reversibility, performance the plan relied on, the user's
  personal setup or reference data, or complexity the plan did not
  budget for.
- **Decide and keep going** on everything else. Report on the
  decisions list (§5) a major decision with one clear answer — no
  alternative the user would plausibly pick instead, such as a plan
  item whose stated approach cannot work, where one replacement is
  clearly right — and a minor tradeoff. A minor decision with one
  clear answer needs no report.

Escalations are batched, the way `plan-upfront` batches its
questions:

- Do not stop at the first one. Record it, leave the work that
  depends on it unbuilt — never settle the question by building one
  side — and carry on with everything that does not depend on it.
- Ask when any one stream has no independent work left, or its
  review has met its level apart from the open escalations: send
  every escalation open at that moment, across all streams, in one
  round. Give each its options, the recommended one first, and what it
  changes in the plan — for a design amendment, the resulting text of
  the recommended option, and of any other option whose text the user
  could not infer from its one-line description, so the answer
  approves the amendment too.
  Aim for one round per plan. A later round only for questions that
  arose after the previous round went out, or that its answers
  created; never hold a question back to avoid one.
- Ask an escalation at once, unbatched, only when waiting would
  waste the work: most of the remaining work depends on its answer,
  or the plan's premise has turned out false in a way that leaves
  more than one way forward.

## 4. Verify, then review

Before `review-loop`, the owner of the change checks what was built,
not what was reported:

- `git status` and `git log` in the implementing worktree: the tree is
  clean, the commits exist, and the branch is the one the implementer
  reported (in this-session mode, the one this session created),
  starting from the base the brief named (in this-session mode, the
  base this session chose).
- The diff covers every plan item assigned to this branch (the whole
  plan, unless a stream or piece brief narrowed it) and nothing outside
  that assignment; an item left unbuilt for an open escalation is
  listed with it, and any other departure is justified in a commit
  message or raised now.
- The verification list was run, with numbers that match the stated
  expectations. A missing number is a gap, not a pass.

Then run `review-loop` on the pinned change (base and tip commit IDs),
with the plan path and anything a
reviewer must know that the plan does not say. For a separate session or several sessions, each implementing
session does this for itself.

## 5. Report

Tell the user: the mode used and why; the branch and commits; the
verification numbers; and the review outcome from `review-loop`
(level, reviewer, rounds, what was fixed, what was left and why). In a separate session or several sessions, each
implementing session sends that recap for its own change; this session
reports the mode it chose and the result of its plan check and
sign-off.

Once the change is clean — `review-loop` has met its level and any
sign-off has passed — the leading session (§3) also gives the user
**the decisions list**: the decisions §3 says to report, made by itself or by an implementer it accepted,
one line each saying what was decided, what it beat or why nothing
else was viable, and why. List the major decisions without an
alternative first, then the minor tradeoffs. Review findings
answered by adding complexity, and fixes declined as
overengineering, go in whichever group fits. Leave out what the plan itself decided and
mechanical choices. In a separate session or several sessions, compile it from
the decisions each session sent with its final branch and from this
session's own rulings. List the escalations the user already answered
separately, with their answers.

When the list holds major decisions without an alternative, the user
approves them before the change merges. Nothing else on the list
holds the merge: the escalations the user already answered need no
second approval, and the minor tradeoffs are for information. A standing merge permission given earlier ("merge when clean")
does not cover major decisions the user has not yet seen. Work that merges nothing —
a draft PR, the next phase, the next session — need not wait for the
approval.

### Landing

The same rule holds in every mode. The owner of the change (§2) lands
it. In a separate session or several sessions, the owner acts on this
session's word (under `coordinator`, the coordinator's): once the
change is clean, this session sends it which case below applies and,
for a merge, the user's merge instruction verbatim. **Clean** here means `review-loop` has met its
level and any sign-off has passed (under `coordinator`, the clean phase
review).

Which case applies follows how the repository lands changes: its agent
instructions first, then its history (pull-request merges, or PR
numbers in squashed subjects, mean pull requests). Where neither
settles it, this session asks the user, in the batched round of §3,
and passes the answer on with its word. Then, once clean:

- **Pull requests, no merge permission from the user**: publish the
  branch as a **draft PR**. The user's request to build the plan (§0)
  is the authorization's origin; cite it when relaying. Without CI, run
  the full suite once before publishing and put the count in the PR
  description.
- **Merge permission from the user** ("merge when clean" or similar)
  **and the major decisions approved** (above): submit to the
  repository's merger session where one exists (`merge-main`);
  otherwise rebase onto the trunk, run the full suite once, and
  fast-forward the trunk (`--ff-only`). Where the trunk lives on a
  remote, the fast-forward must reach it — by pushing the trunk, or by
  merging the PR without a merge commit — before anything counts the
  branch as landed. Cite the user's instruction verbatim when relaying
  it.
- **No pull requests and no merge permission**: report the branch ready
  to the user.
- **A branch built on another unlanded branch** (`new-session` §2)
  never merges before it. With pull requests, its draft PR targets
  that branch, not the trunk, and is retargeted to the trunk only after
  rebasing once that branch has merged.

Once the branch lands, whether in this turn or after a later merge
authorization, continue with §6 before reporting the work finished.

## 6. After landing

Once a branch has landed (it is an ancestor of the trunk, or its PR
shows merged after a squash or rebase merge), and unless
the user has said work continues on it:

- **Built by this session or a subagent**: this session cleans up as
  `new-session` §6 describes: it removes the worktree, deletes the branch,
  and drops the scratch databases and fixtures the build created.
- **Built by a separate session**: that session cleans up its own
  worktree and branch, as `new-session` §6 describes. This session then
  closes the window it spawned, once the branch has landed, its
  worktree and branch are both gone, and the copy of its recap has
  arrived here — checked against the trunk, `git worktree list` and
  `git branch --list <branch>`, not against the session's own
  summary.
- **Under a coordinator**: each implementing session cleans up as
  `new-session` §6 describes; the coordinator verifies that cleanup and
  closes windows as its own skill says.

Then tell the user what was removed, what was closed, and what was
kept.
