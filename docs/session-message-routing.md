# Direct delivery routing in session-message

Maintainer notes for the order in which the `session-message` skill delivers a
direct message or a content-free Relay wake to another session. The skill
states the rule; this file records why the order is what it is. The Relay wake
side of the same design, with its state machine and interference matrix, is
`docs/designs/native-session-wake.md` in the agent-relay repository
(https://github.com/bellatechnica/agent-relay).

## Rule

When a recipient has both a reachable tmux pane and a native route (`codex
queue` for Codex, the `SendMessage` tool for a Claude Code recipient of a Claude
Code sender), the guarded tmux sender from the `tmux-message` skill goes first.
The native route is used only when no pane is reachable, or when the tmux sender
reported that it typed nothing: `OCCUPIED`, `DIALOG`, or `UNKNOWN <class>`
other than `UNKNOWN interrupted`. A result that may have reached the recipient
(`DELIVERY_UNVERIFIED`, a missing result token, or a token that disagrees with
the exit status) never triggers the other route. Neither does an invalid
request (exit 64) or an interrupted send, which are reported to the caller.

## Why tmux goes first

**Delivery timing must not depend on which route worked.** A message to a busy
recipient should reach its running turn, so that "stop, that is the wrong file"
arrives while it still matters. As of 2026-10-31 every other route that was
checked does this:
tmux Enter steers a running Codex, OpenCode or Muse Code turn; Claude Code
shows input typed during a turn, and the completion of a background listener
subagent, inside that turn; a Codex Relay listener keeps its parent's turn open
while it waits. `SendMessage` into a busy session was not tested. Cursor CLI is
the exception — it queues input typed during a turn — and has no native route
here.

**`codex queue` waits for the turn to end.** Observed 2026-10-31 on Codex CLI
0.163.0: a message queued 37 seconds into a two-minute turn was not seen by that
turn; when the turn completed, the queued text started a new turn. A session
attached to the shared app-server daemon (`codex --remote unix://`) behaved the
same. For an idle recipient `codex queue` starts a turn at once, which is why it
remains useful: it reaches a session whose composer holds someone's draft
without touching that draft.

**The app-server steer request does not reach these sessions.** The app-server
protocol's `turn/steer` request delivers into a running turn and refuses a stale
turn id with a definite error, so it would be a clean native steer. Observed
2026-10-31: it worked against a daemon-attached session, but a normally launched
Codex session runs its own in-process server, and the daemon answered
`thread not found` for it. No skill in this repository launches daemon-attached
sessions, so the steer request is not used. Revisit if the launch skills start
attaching sessions to the daemon.

**`SendMessage` addresses are the less stable address.** The user has observed
Claude Code session names change when a session restarts; a tmux pane address
survives a restart in the same pane. This was not reproduced separately. Open
question: whether `SendMessage` to a stale name fails cleanly or could reach a
different session that now holds the name. Under tmux-first it matters only when
no pane is reachable.

## Why only "typed nothing" falls back

The tmux sender's result contract distinguishes refusals made before any paste
from outcomes after a paste or Enter may have reached the pane. Only the first
kind is safe to follow with a second route: messages are not assumed
idempotent, and a duplicate instruction can be acted on twice.
`UNKNOWN interrupted` is excluded because an interrupt is a request to stop.

## One router

The route order is implemented once, in
`skills/session-message/scripts/send_native_or_tmux.py`. The Relay wake helper
in the agent-relay repository calls that router with its own tmux attempt (the
wake sender, which can submit an already-composed wake) rather than keeping a
second copy of the order. The router runs each tmux attempt as a child process,
captures its result token, and prints exactly one final token, so a caller never
sees a tmux refusal and a native acceptance from one send.
