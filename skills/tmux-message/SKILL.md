---
name: tmux-message
description: Deliver one non-idempotent message to a Claude Code or Codex tmux pane through a fail-closed sender that pins the pane, classifies its composer, uses bracketed paste, and verifies a positive submit transition. Use whenever pinging, replying to, or handing something to a session in another tmux pane, including merge requests, verdicts, handoff prompts, status pings, and Agent Relay wake notices.
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

Remove a message file only after `SENT`. Retain it after every other result.
For stdin, retain the exact reproducible source instead. Never clean message
files with a glob.

## Respond to a result

### `OCCUPIED`

Do not inspect-and-retry an ordinary message, even when inspection is generally
allowed. The composer might hold an earlier copy whose submission would make a
later retry a duplicate. Do not press Enter, paste, clear, or poll for a change.
Retain the message file and postpone or escalate the delivery. A later normal
invocation is permitted at the caller's next natural work turn or after an
external notification, but only when no earlier attempt of that same retained
message returned `DELIVERY_UNVERIFIED` or produced no token. This is not a
timer-driven retry loop.

One caller-side exception exists only after a new invocation returns `OCCUPIED`
and that caller's immediately preceding attempt of the same retained message
returned `DELIVERY_UNVERIFIED interrupted-before-enter`. A no-token run does not
qualify because the caller cannot know whether Enter was issued. Unless
inspection was separately disallowed, the caller may resolve the reported pane
to the same `%pane_id`, inspect it read-only, and judge whether the entire
non-dim composer is exactly the retained message. If it is, the permitted action
is exactly one `tmux send-keys -t <reported-%pane_id> Enter`; do not paste or
rerun the sender. Observe the pane afterwards, but do not relabel the script's
earlier result as `SENT`. If complete ownership is not evident, send no key. The
script records no attempts and performs no recovery.

`DELIVERY_UNVERIFIED interrupted-after-enter` never qualifies because the first
Enter may still be pending. The interrupted-send exception deliberately leaves
the final judgment and the capture-to-Enter race with the caller; it must not be
used when that tradeoff is unacceptable.

The `agent-relay-message` skill defines a separate caller-side exception for an
already occupied, complete Relay wake notice. Wake notices are idempotent; normal
messages are not.

### `DIALOG`

Send no key, including Esc. The operator owns the dialog. A later invocation is
allowed only after the operator independently closes it; do not dismiss it to
make delivery possible.

### `UNKNOWN`

- `UNKNOWN server`: correct the tmux socket or server selection before another
  attempt. Do not back off blindly.
- `UNKNOWN target`: re-resolve the window by stable name once. If it remains
  absent, escalate rather than guessing another pane.
- `UNKNOWN layout`: retain the message and wait for a recognized composer. Do
  not loosen the classifier from one unfamiliar capture.
- `UNKNOWN buffer`, `UNKNOWN interrupted`, or `UNKNOWN internal`: fix or report
  the stated local failure before retrying.

### `DELIVERY_UNVERIFIED`

The message may be absent, stranded in the composer, or already submitted.
Never rerun the ordinary send automatically: it may duplicate a completed
delivery. Send no Enter, Esc, `C-u`, or other key automatically.

Read-only inspection is allowed by default. It is forbidden only when a separate
instruction explicitly disallows inspection. Inspection may inform the caller
or operator, but a clear composer alone and message text anywhere on screen do
not prove delivery. Out-of-band evidence such as the recipient's reply may.

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

It recognizes only anchored Claude Code and Codex composer regions:

- Claude Code requires full-width top and bottom borders and one column-zero
  `❯` prompt inside them, followed immediately by its bottom status row.
- Codex requires one column-zero `›` prompt followed by its structural spacer
  and bottommost footer. The footer is either the model/directory summary or
  the full-width, entirely dim editing status line used while a draft is
  present; a short dim row or later nonblank output fails closed.
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
Code `Pasted text` or `Truncated text` placeholder, or native Codex `Pasted
Content` placeholder, is always content and therefore `OCCUPIED`; because the
initial composer had to be clear, its appearance after paste proves processing.
A stale clear frame does not qualify. If every capture in the 3.15-second window
stays clear or unrecognized, the script produces `DELIVERY_UNVERIFIED
paste-not-observed` and sends no Enter.

After one Enter, the script polls on the approved exponential schedule of 50,
100, 200, 400, 800, and 1600 ms. `SENT` requires a non-placeholder `CLEAR`
composer different from the processed-paste observation. It never sends a
recovery Enter. The same dim placeholder or suggestion cannot satisfy both
halves of the transition.

Bracketed paste is required for Codex. Literal `send-keys` can trigger its
paste-burst detector and strand raw text or a `[Pasted Content ...]` placeholder.

The check and paste remain separate tmux commands, so the script cannot
attribute content that another writer places in the composer concurrently. That
operator race is an explicit residual limitation.
