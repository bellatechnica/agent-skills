# Reviewer routing

Select a skill in the target harness before launch. These are distinct review implementations; each must inspect the pinned target named in the Relay request. Check the target harness's current command list or skill registry rather than assuming the local installation matches this list. If its review command only sees the active checkout, give the reviewer its own detached checkout at the pinned tip and verify the command's actual diff before accepting the result. Never point it at the author's worktree.

| Harness | Review skill to invoke | Boundary to check |
| --- | --- | --- |
| Codex | `$review-agent` when installed; otherwise built-in `/review` or `codex review`. | Confirm the selected review method examines the complete pinned diff. `codex review --commit` covers one commit; for a multi-commit change, use `--base` from a detached checkout at the pinned tip or an installed skill that accepts explicit base and tip IDs. |
| Claude Code | Bundled `/review` (alias of `/code-review`) with `--max-findings all`, or a more specific installed review skill the user named. | Use local review, not `ultra`; omit `--fix` and `--comment`. Claude Code may run the bundled review in a forked subagent; the hosting reviewer session stays alive for the next Relay request. |
| Cursor Agent | Built-in `/review`, or an installed review skill the user named. | Confirm the selected review agent examined the requested complete diff rather than the checkout's unrelated changes. Do not use a mode that posts findings or applies fixes. |
| OpenCode | An installed `review-agent` skill or a review command that invokes an explicitly read-only review agent. | A custom `/review` command is just a prompt and normally runs in the current session unless configured for a child; verify its definition and target selection. |
| Antigravity CLI (`agy`) | An installed `review-agent` skill, invoked as `/review-agent`, or another installed read-only review skill. | `/diff` is a viewer, not a review agent. Confirm that the skill is loaded and that its result covers the pinned change. |

For OpenCode or Antigravity CLI, a review skill in another harness's private system directory is not automatically available. If the selected harness lacks one, expose the existing `review-agent` skill through its supported skill directory when filesystem permissions allow, and verify that the target session discovers it. If setup is blocked, report the blocker before launching. Do not copy its instructions into a generic prompt and call that a skill invocation.
