---
name: session-message
description: Set up two-way messaging between coding-agent sessions, using Agent Relay by default, native client delivery when reachable, and guarded tmux fallback. Use when launching or coordinating persistent sessions; task ownership stays with the calling workflow.
---

# Message between sessions

This skill selects and maintains the communication channel between agent sessions. It does not launch a session or decide who owns the task. Read `agent-relay-message` for Relay registration, sends, replies, acknowledgements, listener behavior, and when a wake notice is permitted. Read the `wake.md` in that skill's directory for how to send one. Read `tmux-message` before any guarded tmux delivery. The shared Codex routing script in this skill attempts the native queue and uses that guarded sender only after definite pre-attempt unavailability.

## Choose one channel before launch

- **Agent Relay by default.** Confirm the native `agent_relay` MCP tools with a live call. Choose distinct, human-readable slugs, register the sending session, and give the new session its exact slug and the sender's slug. Exchange exact native recipient addresses when reachable: a Codex thread UUID or exact session name, or a Claude Code session name for a Claude Code sender. Also exchange both tmux pane addresses when the sessions share a server. A session with neither kind of address need not invent one. Relay carries every actionable payload; tmux hosting alone does not select tmux messaging.
- **Direct messaging when explicitly requested or as an announced preflight fallback.** If Relay registration or its live preflight fails *before* launch, use direct messaging only when the sessions have a reachable native client or share a tmux server. Tell the user that Relay failed, why, which direct route can carry messages, and the exact recipient and reply addresses. If neither route is reachable, report the blocker.

The `agent-relay-message` skill itself never substitutes direct messaging for a failed Relay call. The calling workflow may select the announced direct fallback only at this preflight boundary. After Relay mode starts, a later failure does not change channels automatically: report the failed operation and preserve the inbox state. Never resend an ambiguously accepted Relay payload through another channel. A deliberate later channel change needs explicit direction and reconciliation of pending Relay messages.

## Operate Relay mode

Each participant registers its assigned slug, reads pending messages once, then maintains exactly one listener using its client's rule in `agent-relay-message`. The sender also maintains a listener so replies and blockers have a route back. Use `send_message` for a new thread and `reply_to_message` for a response. A successful send is durable acceptance, not recipient processing; acknowledge only after processing as `agent-relay-message` directs.

Inspect both `recipient_waiting_at_send` and
`recipient_wake_watching_at_send` on **every** successful send or reply. The
second field reports a recipient using Relay's content-free wake watcher
instead of an MCP wait:

- If either is true, Relay observed a listener. Send no extra notice.
- If both are false, the payload is still in Relay. Before sending any wake notice, read the `agent-relay-message` skill's `wake.md` in full; then send one content-free notice by the route `wake.md` gives. For a reachable Codex thread, run the `send_relay_wake.py` command `wake.md` gives, with the Codex address and `session-message`'s own `scripts/send_native_or_tmux.py` as its native sender; `send_relay_wake.py` tries `codex queue` first through it and falls back to guarded tmux only when no queue attempt started. A Claude Code sender may use `SendMessage` for a reachable Claude Code recipient. If that tool is unavailable before an attempt, or the recipient has no usable native address, use the guarded tmux wake if its pane is reachable. An uncertain native result forbids a second wake. Without a reachable route, report that active wake-up is unverified. The notice contains only the Relay message ID and inbox/listener instruction; the payload stays in Relay.

An ambiguous send has no authoritative waiting result: do not retry it or send a wake. A listener result with no payload calls for an inbox read, not an assumption that nothing is pending. Keep the client-specific listener active or recover it according to `agent-relay-message` while the sessions still need each other.

## Operate direct mode

Give both sessions the exact native and tmux addresses each can reach. A Claude Code sender uses `SendMessage` for a Claude Code recipient when available. For a reachable Codex recipient, use `scripts/send_native_or_tmux.py --tmux-sender <tmux_send.py> --codex-thread <thread> --shell-safe-text <reviewed-message>`, adding `--tmux-target <pane>` when reachable. The script prints `QUEUED` only after positive Codex queue acceptance; a definite process-start failure selects the guarded tmux sender. Once a queue process starts, an uncertain result prints `DELIVERY_UNVERIFIED native-queue` and must not trigger tmux. The message appears in process arguments: file-sourced, sensitive, or otherwise unsafe text goes through `tmux-message` with its UTF-8 file input. Every ordinary message retains the sender prefix specified by `tmux-message`, even on native transport. A Claude Code sender may select guarded tmux only when `SendMessage` was unavailable before any attempt; an uncertain tool result forbids a second send. A non-Claude sender reaches Claude Code through guarded tmux when available. A positive queue receipt or tmux submit is delivery, not processing; wait for a reply before treating work as done. Do not use Relay opportunistically in this mode or guess a replacement address.

## Tell a new session how to respond

In the launch prompt, tell the new session to load this skill and follow it for its side of the channel, then name the selected channel and exact addresses. For Relay mode, give the child its slug and agent kind, the parent's slug, and each reachable native or tmux recovery address. Tell it to read `agent-relay-message`, register, process pending messages, maintain one listener with its own client's rule, reply to received messages, acknowledge only completed work, and apply the conditional wake rule after every successful send or reply. Tell the parent to start or restore its own listener after launch. For direct mode, give both sessions their usable native and pane addresses, specify the route above, and require replies to the parent's address. Do not assume the child shares the parent's conversation context.
