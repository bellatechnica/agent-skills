---
name: session-message
description: Set up two-way messaging between coding-agent sessions, using Agent Relay by default, an announced full-tmux preflight fallback when needed, and a tmux wake only when Relay reports no waiting recipient. Use when launching or coordinating persistent sessions; task ownership stays with the calling workflow.
---

# Message between sessions

This skill selects and maintains the communication channel between agent sessions. It does not launch a session or decide who owns the task. Read `agent-relay-message` for Relay registration, sends, replies, acknowledgements, listener behavior, and the wake helper. Read `tmux-message` before any full-tmux delivery or Relay wake. Those skills own the mechanics; do not implement a second sender or listener here.

## Choose one channel before launch

- **Agent Relay by default.** Confirm the native `agent_relay` MCP tools with a live call. Choose distinct, human-readable slugs, register the sending session, and give the new session its exact slug and the sender's slug. Record both sessions' tmux pane addresses as recovery addresses when they share a server. Relay carries every actionable payload; tmux hosting alone does not select tmux messaging.
- **Full tmux when explicitly requested or as an announced preflight fallback.** If Relay registration or its live preflight fails *before* launch, use full tmux only when both sessions are reachable through the same tmux server. Tell the user that Relay failed, why, that full tmux will carry the messages, and both pane addresses. Resolve and pin the panes as `tmux-message` directs. If tmux is unavailable too, report the blocker.

The `agent-relay-message` skill itself never substitutes tmux for a failed Relay call. The calling workflow may select the announced full-tmux fallback only at this preflight boundary. After Relay mode starts, a later failure does not change channels automatically: report the failed operation and preserve the inbox state. Never resend an ambiguously accepted Relay payload through tmux. A deliberate later channel change needs explicit direction and reconciliation of pending Relay messages.

## Operate Relay mode

Each participant registers its assigned slug, reads pending messages once, then maintains exactly one listener using its client's rule in `agent-relay-message`. The sender also maintains a listener so replies and blockers have a route back. Use `send_message` for a new thread and `reply_to_message` for a response. A successful send is durable acceptance, not recipient processing; acknowledge only after processing as `agent-relay-message` directs.

Inspect `recipient_waiting_at_send` on **every** successful send or reply:

- If true, Relay alone notified an active wait. Send no tmux notice.
- If false, the payload is still in Relay. When a verified tmux recovery address reaches the recipient, one wake notice may go through the `agent-relay-message` wake helper. The helper sends only the Relay message ID and an inbox/listener instruction through `tmux-message`; never put the actionable payload in the pane. Without a reachable pane, report that active wake-up is unverified.

An ambiguous send has no authoritative waiting result: do not retry it or send a wake. A listener result with no payload calls for an inbox read, not an assumption that nothing is pending. Keep the client-specific listener active or recover it according to `agent-relay-message` while the sessions still need each other.

## Operate full-tmux mode

Give both sessions their pinned pane addresses. Every payload and reply goes through `tmux-message`, including follow-up requests and readiness notices. A positive submit transition establishes delivery to the target composer, not that the target processed the request; wait for an explicit response before treating work as done. Follow `tmux-message`'s occupied-composer and unverified-delivery rules. Do not use Relay opportunistically in this mode or silently switch to another pane.

## Tell a new session how to respond

In the launch prompt, name the selected channel and the exact addresses. For Relay mode, give the child its slug and agent kind, the parent's slug, and both recovery pane addresses. Tell it to read `agent-relay-message`, register, process pending messages, maintain one listener with its own client's rule, reply to received messages, acknowledge only completed work, and apply the conditional wake rule after every successful send or reply. Tell the parent to start or restore its own listener after launch. For full-tmux mode, give both pane addresses, say that all actionable messages use `tmux-message`, and require replies to the parent's pane. Do not assume the child shares the parent's conversation context.
