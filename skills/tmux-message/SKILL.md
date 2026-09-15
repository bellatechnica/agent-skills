---
name: tmux-message
description: Deliver one message to a Claude Code, Codex, Antigravity CLI, or OpenCode tmux pane through a fail-closed sender that pins the pane, classifies its composer, uses bracketed paste, and verifies a positive submit transition. Use whenever pinging, replying to, or handing something to a session in another tmux pane, including merge requests, verdicts, handoff prompts, status pings, and Agent Relay wake notices.
---

# Message another session through tmux

Keystrokes injected into another pane are indistinguishable from its operator
typing them. Deliver each message through
[`scripts/tmux_send.py`](scripts/tmux_send.py). A caller permitted to inspect the
pane may use the documented inspection-authorized fallback after a sender
refusal; otherwise do not replace the script with separate inspection and raw
paste commands because the pane can change between them.

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
  still visible. Activity text without a composer is `UNKNOWN layout`; only the
  inspection-authorized fallback can permit delivery on that refused shape.
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

When direct inspection is allowed, the caller may quote or summarize the pane
content needed to explain its finding in a report, record, or Relay message.
Do not expose unrelated transcript content or sensitive information.

### Inspection-authorized fallback after a refusal

The result-specific rules below decide when an inspection-capable caller may
start this fallback. At that point, the script's refusal does not overrule a
caller that positively identifies the intended agent's ordinary, clear message
composer and judges the pane safe. A real draft, dialog, overlay, shell mode,
permission prompt, or composer addressed to another agent is not safe; wait
instead. A client-native paste placeholder (`[Pasted text #N …]`, `[Pasted
Content N chars]`, or `[Pasted ~N lines]`) is a real draft even when dim, and
typed text followed by a dim completion is a real draft. Only a composer whose
entire visible content is empty, or is a dim suggestion with no typed
characters, is clear.

Before starting the fallback, cancel any remaining retries for that message and
confirm that no guarded invocation for it is still running. Once the fallback
issues its paste, the message never returns to the retry path. Pin the
`%pane_id` printed in the refused invocation's stderr diagnostic (`pane %N`) and
inspect that pane immediately before mutation. Preserve ANSI attributes during
inspection so dim suggestions remain distinguishable from plain drafts; query
the terminal cursor as a second signal when styling is ambiguous. A passive
notice above an independently clear composer does not need to be dismissed
before delivery. Finish and read the inspection before starting any mutation;
do not pipe a capture into the paste operation. Deliver only the exact retained
source that invocation already accepted, so the empty-message and control-
character checks have run:

    tmux load-buffer -b <unique-name> <retained-file>
    tmux paste-buffer -p -r -d -b <unique-name> -t <%pane_id>

For retained stdin or `--shell-safe-text`, feed the exact retained bytes to
`tmux load-buffer -b <unique-name> -` without shell interpolation. The `-r`
preserves literal LF characters and `-d` deletes the unique buffer. Never
retype, reconstruct, or use `send-keys -l` for the message. Submit with a
separate `tmux send-keys -t <%pane_id> Enter` call. If `paste-buffer` fails after
`load-buffer` succeeded, run `tmux delete-buffer -b <unique-name>` and treat the
attempt as uncertain.

Inspect again after paste. Issue exactly one Enter only when the intended
unsubmitted draft, including a client-native paste placeholder, owns the same
ordinary composer. If the caller's own paste raised an input-mode suggestion
dialog, it may issue one Esc before Enter only after an inspection immediately
before Esc shows that same suggestion dialog still open, and only when the
dialog appeared in direct response to that paste, describes an input-mode
suggestion rather than an operator question, and the intended draft remains in
the composer after Esc. Stop without another key when the pane, ownership, or
dialog provenance is uncertain.

After Enter, verify the composer's positive transition to empty; the message
appearing in the transcript does not prove submission. Once the direct paste is
issued, end every guarded retry schedule for that message. An observed clear
composer means the message was delivered and no further attempt is made. Any
other outcome is uncertain: treat it as `DELIVERY_UNVERIFIED` and never paste
the message again. A direct attempt that pasted and certainly issued no Enter
may use the one-Enter completion below, as if its stage were
`paste-not-observed`. A direct attempt that issued an Enter, or where it is not
known whether an Enter was issued, never qualifies. Report an inspection-
authorized direct delivery, not `SENT`; `SENT` remains the guarded script's
result.

Remove a message file after `SENT` or after an inspection-authorized delivery
whose cleared composer was observed. Retain it after every refusal or uncertain
attempt. For stdin, retain the exact reproducible source instead. Never clean
message files with a glob.

## Respond to a result

Retain the exact message source while a pre-send refusal remains unresolved.
The ordering depends on the result and the caller's inspection permission:

- After `OCCUPIED` or `DIALOG`, retry the same guarded command after roughly 5
  seconds, 15 seconds, 45 seconds, and 2 minutes. Only after all four retries
  still return `OCCUPIED` or `DIALOG` may an inspection-permitted caller start
  the inspection-authorized fallback. A caller not permitted to inspect instead
  postpones the message and starts the same schedule again at its next natural
  work turn or after an external notification.
- After `UNKNOWN layout`, an inspection-permitted caller skips the retry
  schedule and starts the inspection-authorized fallback immediately. A caller
  not permitted to inspect uses the guarded retry schedule above.

Each retry classifies the pane again immediately before any paste, so it sends
only after the pane becomes safe. Handle every new result by its own rule: in
particular, an inspection-permitted caller stops an `OCCUPIED` or `DIALOG`
schedule and inspects immediately if a retry returns `UNKNOWN layout`. Stop the
schedule on `SENT` or any result other than `OCCUPIED`, `DIALOG`, or `UNKNOWN
layout`. If an authorized inspection does not positively identify a safe clear
composer, issue no paste, retain the message, and postpone it. At the caller's
next natural work turn or after an external notification, start again with a
fresh guarded invocation and handle the result under its own rule. Escalate only
when delivery blocks progress.

Both the timed and postponed retries are permitted only when no attempt of that
same retained message, before or during the schedule, returned
`DELIVERY_UNVERIFIED`, produced no result token, or produced a token/status
disagreement, and no inspection-authorized direct paste was issued. A message
with any such attempt in its history never re-enters either retry; only the
one-Enter completion under `DELIVERY_UNVERIFIED` may act on it.

### `OCCUPIED`

An ordinary draft is not safe: do not append to it, submit it, clear it, or
dismiss it. For an ordinary message, always begin with the guarded retry
schedule. Only after its four retries are exhausted may an inspection-permitted
caller check whether the result was a misclassified clear composer and, if so,
use the inspection-authorized fallback. Otherwise wait for the operator or
target session to clear the composer independently.

The `agent-relay-message` helper performs a separate automatic exception for an
already occupied, complete Relay wake notice. Wake notices are idempotent;
normal messages are not.

### `DIALOG`

A real dialog belongs to the operator: send no key, including Esc, and always
begin with the guarded retry schedule. Only after its four retries are exhausted
may an inspection-permitted caller check whether the result was a misclassified
ordinary clear composer and, if so, use the inspection-authorized fallback. Its
separate Esc rule covers only an input-mode suggestion raised by the caller's
own direct paste.

### `UNKNOWN`

Read-only direct inspection is allowed unless separately disallowed. For
`UNKNOWN layout`, it may distinguish a transient client screen from a newly
unsupported shape and may share the content needed to explain that finding.
Inspection does not by itself relabel the sender's result.

- `UNKNOWN server`: correct the tmux socket or server selection before another
  attempt. Do not back off blindly.
- `UNKNOWN target`: a tmux listing to re-resolve the window by stable name is
  permitted only when direct inspection is allowed and the target window appears
  to have moved; list once. If either condition fails, or the window remains
  absent, escalate rather than guessing another pane. This condition covers
  recovery from this result only; it does not restrict how other workflows
  obtain an address in the first place.
- `UNKNOWN layout`: do not loosen the classifier from one unfamiliar capture.
  An inspection-permitted caller inspects immediately and may use the fallback
  when it positively judges the actual composer safe; it does not run the
  guarded retry schedule before that inspection. A caller not permitted to
  inspect uses the guarded retry schedule to detect whether a transient client
  screen returns to a recognized composer.
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

After `DELIVERY_UNVERIFIED paste-not-observed` or `interrupted-before-enter`, and
unless direct inspection is disallowed, the caller may issue exactly one
`tmux send-keys -t <reported-%pane_id> Enter`, without running the sender again,
when an inspection immediately before the key shows both of these: the intended
agent's own ordinary message composer, not a dialog, overlay, shell mode,
permission prompt, or a view addressed to another agent; and a draft that is
entirely the retained message, or entirely one client-native paste placeholder,
attributable to that attempt. Stop without a key if the pane or ownership
changed or is uncertain. Never paste the message again. This never applies after
an Enter may already have been issued (`enter-failed`, `not-cleared`,
`interrupted-after-enter`, `internal-error`) or after a run with no result token.
If the composer does not clear after that Enter, send nothing further. Report
the completion separately; do not relabel the earlier result as `SENT`.

Retain the exact message file or reproducible stdin source. Escalate to the
operator of the calling session; for a handoff, also notify the counterpart
through Agent Relay. Report the target, UTC time, retained source, result stage,
stderr diagnostic, and relevant inspection findings.

If the message was only a Relay wake, report that Relay accepted the durable
payload but active wake-up is unverified. Do not resend the Relay payload.

A run that produces none of the documented stdout results—because of SIGKILL, a
host crash, or a caller-side timeout—is treated as
`DELIVERY_UNVERIFIED` and never qualifies for the inspected one-Enter
exception. A timeout wrapper must allow longer than the two
3.15-second verification windows plus tmux command time.

## Classifier and verification contract

The script captures ANSI attributes and joins soft-wrapped terminal rows:

    tmux capture-pane -p -e -J -t <pinned-pane-id>

When tmux marks a pane-width Claude Code or Antigravity CLI border as soft
wrapped into the following prompt row, the script separates that exact
border-plus-prompt boundary before classification. Other overlong rows remain
unchanged.

It recognizes only anchored Claude Code, Codex, Antigravity CLI, and OpenCode
composer regions. The Antigravity CLI 1.1.27 and OpenCode 1.18.31 shapes were
live-checked on 2026-09-14:

- Claude Code requires full-width top and bottom borders and one column-zero
  `❯` prompt inside them, with its normal status row immediately after the
  bottom border. When one or more background subagents add a status panel below
  that row, the cursor must be inside the recognized composer, exactly one panel
  row must carry the selected marker, and that row must be `main`. A composer
  beginning with the client-native `Message @` agent placeholder is never
  accepted in this shape. Arbitrary later content without all of that evidence
  still fails closed.
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
