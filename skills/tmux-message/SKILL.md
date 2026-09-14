---
name: tmux-message
description: Deliver one message to a Claude Code, Codex, Antigravity CLI, or OpenCode tmux pane through a fail-closed sender that pins the pane, classifies its composer, uses bracketed paste, and verifies a positive submit transition. Use whenever pinging, replying to, or handing something to a session in another tmux pane, including merge requests, verdicts, handoff prompts, status pings, and Agent Relay wake notices.
---

# Message another session through tmux

Keystrokes injected into another pane are indistinguishable from its operator
typing them. Deliver each message through
[`scripts/tmux_send.py`](scripts/tmux_send.py). Never replace it with a separate
inspection followed by raw paste commands: the pane can change between them.

A normal message is **not guaranteed to be idempotent**. A second submission may
repeat a merge, reply, request, or other action. The result rules below therefore
distinguish a confirmed pre-send refusal from an uncertain attempt.

## Address and identify the session

- Address a single-pane window as `<session>:<window>` and a specific pane as
  `<session>:<window>.<pane>`. Session and window names or indices must match an
  enumerated tmux address exactly; tmux's fuzzy target fallback is never used.
  Omitting the pane index is valid only when that exact window has one pane.
- The script resolves that exact address once to tmux's stable `%pane_id` and
  uses the pane ID for every capture, paste, and key command. It rejects a name
  versus index collision as ambiguous and reports the tmux socket in
  diagnostics.
- Include the sender in every ordinary message:

      From <session>:<window>.<pane> (<short role>):

  Agent Relay wake notices are the only exception. They carry no payload or
  authority and use the fixed format in the `agent-relay-message` skill.
- A busy session is valid only when its structurally recognized composer is
  still visible. Activity text without a composer is `UNKNOWN layout`, not
  permission to type.
- OpenCode interprets Enter in a visible composer during an active response as
  a steering message. The sender uses the client's ordinary Enter action; it
  does not change that message into OpenCode's separately queued Alt+Enter
  action.

## Supply the exact message

Use a uniquely named UTF-8 file under `/tmp` for arbitrary, multiline,
sensitive, or otherwise exact content. Create it with the current client's safe
file-writing facility; for Codex, use `apply_patch`. Other clients need not have
that tool.

Use `--stdin` to read UTF-8 from stdin. Use this only when the caller has
established that its stdin producer is shell-safe, emits the intended trailing
LF, exposes no sensitive content, and leaves the exact input reproducible after
a non-`SENT` result. A simple `echo 'literal'` pipeline may qualify; it is the
caller's decision, not a guarantee made by this script.

Use `--shell-safe-text <text>` only for non-sensitive text whose shell parsing,
argument-size, and exact resulting value the caller has reviewed. The flag
records that judgment; the script cannot validate it. Because the text appears
in process arguments and the calling command, this mode is not suitable for
sensitive content.

Do not rewrite or truncate a message for transport. Avoid command substitution,
JSON serialization, or shell interpolation that changes real LF characters or
interprets message text.

The sender refuses a message with no visible substance, including empty,
whitespace-only, and format-character-only input. It also refuses every Unicode
control character except line feed (`LF`) before resolving or mutating a tmux
target. In particular, an embedded escape character could otherwise end
bracketed paste early and turn the remaining bytes into live keystrokes.

## Invoke the guarded sender

Resolve the script path relative to this `SKILL.md`, then run:

    python3 <tmux-message-skill>/scripts/tmux_send.py <target> --file /tmp/<message-file>

or:

    <safe-stdin-producer> | python3 <tmux-message-skill>/scripts/tmux_send.py <target> --stdin

or:

    python3 <tmux-message-skill>/scripts/tmux_send.py <target> --shell-safe-text '<reviewed-text>'

The stdout line is the stable result token and is written only after the outcome
is decided. Some failures add a stable class or stage after it:

- `SENT`, exit `0`: after paste, the script observed a recognized non-empty
  composer, issued one Enter, and then observed that composer clear.
- `OCCUPIED`, exit `1`: an ordinary draft is present; nothing was sent.
- `DIALOG`, exit `2`: a dialog or other non-composer interface owns the pane;
  nothing was sent.
- `UNKNOWN <class>`, exit `3`: nothing was sent. Classes are:
  - `server`: tmux or its socket could not be reached;
  - `target`: tmux answered, but the requested or pinned pane did not;
  - `layout`: the pane was captured, but its shape was not recognized;
  - `buffer`: tmux could not prepare the exact message buffer;
  - `interrupted` or `internal`: execution stopped before paste was issued.
- `DELIVERY_UNVERIFIED <stage>`, exit `4`: at least one paste or key command may
  have reached the pane, but the result is uncertain. Stages are exactly
  `paste-failed`, `paste-not-observed`, `enter-failed`, `not-cleared`,
  `interrupted-before-enter`, `interrupted-after-enter`, and `internal-error`.
- Exit `64`: invalid arguments, message source, or message content; nothing was
  sent.

Exit `0` is reserved for `SENT`; `--help` is an invocation result and exits 64.
The token and exit status must agree. A missing token, multiple tokens, or any
token/status disagreement is treated as `DELIVERY_UNVERIFIED` unless the only
output is the documented exit-64 invocation error before a target was resolved.

The script never prints its pane capture, composer text, or transcript. Stderr
contains the target, pinned pane where available, socket, state explanation, and
tmux's own error text.

Direct inspection means the caller itself reading pane or tmux state outside the
sender scripts, such as its own `tmux capture-pane` or a tmux listing. It is
allowed read-only by default and forbidden only when a separate instruction
explicitly disallows direct inspection. The captures and pane enumeration that
`tmux_send.py` and the Relay wake helper perform internally are part of sending,
print no pane content, and are not direct inspection; an instruction disallowing
direct inspection does not restrict them.

Remove a message file only after `SENT`. Retain it after every other result.
For stdin, retain the exact reproducible source instead. Never clean message
files with a glob.

## Respond to a result

For `OCCUPIED`, `DIALOG`, or `UNKNOWN layout`, retain the exact message source
and retry the same guarded command after roughly 5 seconds, 15 seconds, 45
seconds, and 2 minutes. Each invocation classifies the pane again immediately
before any paste, so it sends only after the pane becomes safe. Stop the schedule
on `SENT` or any result other than `OCCUPIED`, `DIALOG`, or `UNKNOWN layout`. If
all four retries still refuse, postpone the message and start the same schedule
again at the caller's next natural work turn or after an external notification;
escalate only when delivery blocks progress.

Both the timed and postponed retries are permitted only when no attempt of that
same retained message, before or during the schedule, returned
`DELIVERY_UNVERIFIED`, produced no result token, or produced a token/status
disagreement. A message with any such attempt in its history never re-enters
either retry; only the interrupted-send exception below may act on it.

### `OCCUPIED`

Do not directly inspect, press Enter, paste, or clear the ordinary draft. Unless
the interrupted-send exception below applies, let the guarded retry schedule
reclassify the pane and send only after the operator or target session
independently clears the composer.

One caller-side exception exists only after a new invocation returns `OCCUPIED`
and that caller's immediately preceding attempt of the same retained message
returned `DELIVERY_UNVERIFIED interrupted-before-enter`. A no-token run does not
qualify because the caller cannot know whether Enter was issued. Unless direct
inspection was separately disallowed, the caller may resolve the reported pane
to the same `%pane_id`, inspect it directly and read-only, and judge whether the
entire non-dim composer is exactly the retained message. If it is, the permitted
action is exactly one `tmux send-keys -t <reported-%pane_id> Enter`; do not
paste or rerun the sender. Observe the pane afterwards, but do not relabel the
script's earlier result as `SENT`. If complete ownership is not evident, send no
key. The script records no attempts and performs no recovery.

`DELIVERY_UNVERIFIED interrupted-after-enter` never qualifies because the first
Enter may still be pending. The interrupted-send exception deliberately leaves
the final judgment and the capture-to-Enter race with the caller; it must not be
used when that tradeoff is unacceptable.

The `agent-relay-message` helper performs a separate automatic exception for an
already occupied, complete Relay wake notice. Wake notices are idempotent;
normal messages are not.

### `DIALOG`

Send no key, including Esc. The operator owns the dialog. Let the guarded retry
schedule detect when the operator independently closes it; do not dismiss it to
make delivery possible.

### `UNKNOWN`

- `UNKNOWN server`: correct the tmux socket or server selection before another
  attempt. Do not back off blindly.
- `UNKNOWN target`: a tmux listing to re-resolve the window by stable name is
  permitted only when direct inspection is allowed and the target window appears
  to have moved; list once. If either condition fails, or the window remains
  absent, escalate rather than guessing another pane. This condition covers
  recovery from this result only; it does not restrict how other workflows
  obtain an address in the first place.
- `UNKNOWN layout`: retain the message and wait for a recognized composer. Do
  not loosen the classifier from one unfamiliar capture. Let the guarded retry
  schedule detect whether a transient client screen returns to a recognized
  composer.
- `UNKNOWN buffer`, `UNKNOWN interrupted`, or `UNKNOWN internal`: fix or report
  the stated local failure before retrying.

### `DELIVERY_UNVERIFIED`

The message may be absent, stranded in the composer, or already submitted.
Never rerun the ordinary send automatically: it may duplicate a completed
delivery. Send no Enter, Esc, `C-u`, or other key automatically.

Read-only direct inspection is allowed unless separately disallowed. It may
inform the caller or operator, but a clear composer alone and message text
anywhere on screen do not prove delivery. Out-of-band evidence such as the
recipient's reply may.

Retain the exact message file or reproducible stdin source. Escalate to the
operator of the calling session; for a handoff, also notify the counterpart
through Agent Relay. Report the target, UTC time, retained source, result stage,
and stderr diagnostic. Never include pane contents in a report, record, or
Relay message.

If the message was only a Relay wake, report that Relay accepted the durable
payload but active wake-up is unverified. Do not resend the Relay payload.

A run that produces none of the documented stdout results—because of SIGKILL, a
host crash, or a caller-side timeout—is treated as
`DELIVERY_UNVERIFIED` and never qualifies for the interrupted-send Enter
exception. A timeout wrapper must allow longer than the two
3.15-second verification windows plus tmux command time.

## Classifier and verification contract

The script captures ANSI attributes and joins soft-wrapped terminal rows:

    tmux capture-pane -p -e -J -t <pinned-pane-id>

It recognizes only anchored Claude Code, Codex, Antigravity CLI, and OpenCode
composer regions. The Antigravity CLI 1.1.27 and OpenCode 1.18.31 shapes were
live-checked on 2026-09-14:

- Claude Code requires full-width top and bottom borders and one column-zero
  `❯` prompt inside them, followed immediately by its bottom status row.
- Codex requires one column-zero `›` prompt followed by its structural spacer
  and bottommost footer. The footer is either the model/directory summary or
  the full-width, entirely dim editing status line used while a draft is
  present; a short dim row or later nonblank output fails closed.
- Antigravity CLI requires full-width top and bottom borders, one column-zero
  `>` prompt, two-column continuation indentation, and the model-and-effort
  footer immediately below the lower border. Its `!` shell mode does not match
  that structure and is `UNKNOWN layout`.
- OpenCode requires the bottommost `┃` input box and its `╹▀` lower border. The
  terminal cursor must be inside the box's text area; a command palette or
  another overlay leaves the box rendered behind it but moves the cursor, so
  that state is `DIALOG`. A positive `ctrl+p commands` hint must also follow the
  box, so OpenCode's `!` shell mode is `DIALOG` and sender input cannot execute
  as a shell command. On the home screen, only an exact built-in `Ask anything`
  prompt, with either the ASCII or Unicode ellipsis and the same foreground
  color as the muted `commands` hint, is replaceable. The same words in the
  normal input color are a real draft. `Run a command` is never replaceable.
- Continuation rows require the clients' two-column continuation indentation.
  Quoted or pasted prompt and border glyphs inside a draft do not become
  structural markers.
- Bare composers and entirely SGR-dim suggestions are `CLEAR`. A native paste
  placeholder anywhere in the composer is `OCCUPIED` regardless of styling,
  because it represents stored input rather than a replaceable suggestion.
- Any dialog marker, mixed plain-plus-dim text, malformed region, or absent
  composer fails closed as `DIALOG`, `OCCUPIED`, or `UNKNOWN layout`.

Before Enter, the script waits until one capture shows non-empty composer text
after the successful paste command. A changed all-dim suggestion remains
`CLEAR` and does not establish that the paste was processed. A native Claude
Code or Antigravity CLI `Pasted text` or `Truncated text`
placeholder, Codex `Pasted Content` placeholder, or OpenCode `Pasted ~N lines`
placeholder is always content and therefore `OCCUPIED`; because the initial
composer had to be clear, its appearance after paste proves processing.
A stale clear frame does not qualify. If every capture in the 3.15-second window
stays clear or unrecognized, the script produces `DELIVERY_UNVERIFIED
paste-not-observed` and sends no Enter.

After one Enter, the script polls on the approved exponential schedule of 50,
100, 200, 400, 800, and 1600 ms. `SENT` requires a non-placeholder `CLEAR`
composer different from the processed-paste observation. It never sends a
recovery Enter. The same dim placeholder or suggestion cannot satisfy both
halves of the transition.

Bracketed paste is used for every supported client. Literal `send-keys` can
trigger a client's paste-burst handling, collapse multiline input, or strand raw
text instead of preserving the intended message as one paste operation.

The check and paste remain separate tmux commands, so the script cannot
attribute content that another writer places in the composer concurrently. That
operator race is an explicit residual limitation.
