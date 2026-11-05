---
name: review-session
description: Run an independent review in a persistent agent session, optionally in another CLI, and exchange findings and revised commits until the current change reaches its stop level, judged as review-loop describes. Use when the author wants a reviewer to stay available across fix rounds. Use session-message for the communication channel.
---

# Review session

This skill coordinates the review loop. The spawned session performs each review, choosing its own method. The invoking session owns the loop and normally owns the change; if another session owns the change, findings route to it at the address step 2 of "Prepare the review" obtains for the selected channel. The reviewer is read-only. This differs from a `handoff`, which briefs a session to take on a work item.

The loop runs to a stop level: one pass, no real defects, or fully clean. When `review-loop` invokes this skill, use the level it passes; otherwise judge and state it as `review-loop` §1 does. Below, **clean** means the latest round met that level.

Read `new-session` for process launch, session naming, resume, and worktree
boundaries. Read `session-message` for the channel: selection and its
preflight fallback, registration, listeners, sends, acknowledgements, and
wakes.

## Prepare the review

1. Identify the author session and the change to review. Default the reviewer to this session's CLI; honor a different CLI or model the user names, and verify that its executable exists. Do not pick the reviewer's review skill or command for it: the reviewer chooses whatever its harness offers that best fits the change — a code-review skill for code; for prose, plans, or cross-document consistency, a skill made for that or a direct review against the criteria — and names its choice in each result. The method must examine the complete pinned change, not a single commit or the checkout's unrelated changes, and must run locally: a billed or cloud review, such as `/code-review ultra`, is the user's to start, never the reviewer's.
2. Select the channel before launch through `session-message`. Preserve any existing Relay slug assigned to this session. If the author is another session, get its exact Relay slug or reachable native or tmux address for the selected channel; do not guess it.
3. Pin an immutable target for each round as `review-loop` §0 does: the repository root, target kind, full base and tip commit IDs or review commit, and any user-supplied review criteria. The reviewer uses the pinned IDs rather than resolving moving branch names again.
4. Do not send the reviewer into the author's live worktree. A reviewer can inspect committed objects from the repository root. If its review method needs a checkout, it creates its own clean, detached worktree at the pinned tip with `git worktree add --detach`, at `<repo root>/.agents/worktrees/<descriptive-name>` (the directory `new-session` §2 names), never with a client's own worktree feature, and removes it after closure; the launch prompt in step 5 says so. For uncommitted work, the author must first provide an immutable review snapshot that includes staged, unstaged, and untracked intended changes; record what it contains and what it excludes. Do not claim a branch review covers changes outside that snapshot. Do not alter the author's index or branch merely to make a review target.
5. Launch a named, resumable reviewer session in its own tmux window using `new-session`. Keep its initial prompt short but explicit. It names:
   - the pinned target, as context;
   - the chosen channel and its exact addresses, as `session-message` directs, with an instruction to load `session-message` and follow it for its side of the channel;
   - the review-method rules from step 1, and the round protocol below;
   - where and how to make a checkout if its review method needs one, as step 4 says;
   - the repository's agent instructions and the user's global ones, by path, saying that they bind the reviewer and that the change is held to them;
   - an instruction to find and read the committed design documents relevant to the change.

   The prompt states the boundary. The reviewer is read-only: it never edits files, commits, merges, posts comments, or uses a review command's fix or post option. It reads or searches no linked worktree and nothing under `<repo root>/.claude/worktrees/` or `<repo root>/.agents/worktrees/` except its own checkout. It sends no final user recap while rounds remain. The prompt tells it to establish its side of the channel and wait for the first review request; the prompt itself is not a request. It reports every actionable finding through the channel and stays online awaiting another round until told to close. When the change needs durable context, write a handoff document as `handoff` §1 describes.

## Run rounds

- Send a review request through the selected channel with a round identifier, the exact base and tip commit IDs or immutable snapshot identifier, the scope, and the complete review criteria. For later rounds, include prior findings and the author's disposition of each. In Relay mode, the reviewer replies to the request with its result. In direct mode, follow `session-message` for each request and reply, and require a result explicitly naming the round so a submitted message is not mistaken for a completed review.
- The reviewer reviews the **whole pinned change**, not just the latest fix. It returns findings ordered by severity, each with a changed line and a demonstrated affected path, or `No findings.` It also names the exact target it inspected, the review method it used, relevant checks it ran, and material gaps. It sends that result through the selected channel and waits for another round.
- The author triages each finding as `review-loop` §3 describes, sending a dispute's code evidence back to this same reviewer for a ruling. It fixes accepted defects in the change's own worktree and sends a new immutable target. If the invoking session is not the author, route findings to the author at the address from step 2 and wait for its new target. Continue until the stop level is met.
- Staleness and the dispositions each stop level allows follow `review-loop` §1 and §3; re-run a stale result in full on the new target. A result is **clean** only when it meets the stop level, the reviewer completed the review with the method it named, and the author has independently verified three things: the reported IDs match the intended target, the target includes all intended changes, and the named method covered the whole pinned range. A test gap that is itself actionable is a finding; other gaps are reported as residual risk.

## Keep and close the session

Keep the reviewer process alive between rounds, and both sessions' listeners as `session-message` requires. While a round is out, watch the reviewer as `new-session` §7 describes; if it exits while work remains, resume **that session** as `new-session` §5 describes. A genuine blocker can pause fixes, but the reviewer remains available and the user sees the blocker.

Once the latest target is clean, send a close request through the selected channel naming the clean round and commit IDs. The reviewer replies that its result is final and it is ready to close, acknowledging the request only then in Relay mode. Verify the reply and the pinned tmux window identity before closing that window; remove only the reviewer's own temporary worktree or scratch artifacts. If the reviewer exits itself, verify its window is gone. Report the clean target, review scope, remaining test gaps, and that the reviewer session closed.
