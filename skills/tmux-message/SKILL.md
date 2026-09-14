---
name: tmux-message
description: Deliver a message to another Claude Code or Codex session running in a tmux pane - addressing, fail-closed composer classification, safe bracketed paste, occupied-line backoff, and post-send verification. Use whenever pinging, replying to, or handing something to a session in another tmux window or pane, including merge requests, verdicts, handoff prompts and status pings.
---

# Message another session through tmux

Keystrokes injected into someone else's pane are indistinguishable from the
operator typing them. Deliver every message through
[`scripts/tmux_send.py`](scripts/tmux_send.py). Do not replace the script with a
separate inspection and raw `tmux paste-buffer`: the pane can change between
those operations, and the inspection ceases to be a guard.

## 1. Address the session

- **The target**: `<session>:<window>` for a single-pane window,
  `<session>:<window>.<pane>` otherwise. Use `tmux list-windows -a` to find it by
  name. Window indices renumber, so re-resolve a stale address by name rather
  than trusting one from an earlier turn.
- **Your own address**, when the target needs to reply:
  `tmux display-message -p -t "$TMUX_PANE" '#S:#I.#P'`. Include it in the
  message. A session that has to guess how to answer usually answers the user
  instead.
- A **busy target is valid**. Claude Code and Codex keep an input composer
  available while a turn runs. Busy is not the blocking condition; an occupied
  composer is.

Every message starts by identifying its sender in this exact shape:

    From <session>:<window>.<pane> (<short role>):

For example: `From 0:10.0 (backfill-fixes):`. Use the known current sender
address and the stable human-readable responsibility or window name as the
role. Re-resolve it only when it is unknown or stale, pane numbering may have
changed, or communication is not behaving as expected. The prefix is required
for handoffs, replies, follow-ups, status pings, merge requests, and one-line
notices alike.

## 2. Put the exact message in a file

Create a uniquely named file under `/tmp` with `apply_patch`. The file contains
the complete message, including real LF characters. Do not create it with shell
`echo`, `printf`, a here-document, or a serialized string. Do not rewrite or
truncate the message to make shell quoting easier.

The sender accepts a file rather than a shell argument because JSON represents
LF as the two characters `\n`, and POSIX double quotes do not decode that pair.
Passing serialized text can deliver literal backslash-n characters instead of
line breaks.

## 3. Invoke the guarded sender

Resolve the script path relative to this `SKILL.md`, then run:

    python3 <tmux-message-skill>/scripts/tmux_send.py <target> /tmp/<message-file>

The script writes one stable result token to stdout:

- `SENT`, exit `0`: the message was pasted, submitted, and the composer was
  verified clear.
- `OCCUPIED`, exit `1`: the composer contains unsubmitted text; nothing was
  sent.
- `DIALOG`, exit `2`: a dialog or other non-prompt interface owns the pane;
  nothing was sent.
- `UNKNOWN`, exit `3`: the pane shape, target, or tmux server could not be
  resolved safely; nothing was sent.
- `DELIVERY_UNVERIFIED`, exit `4`: paste began, but delivery could not be
  verified. Do not retry automatically; another paste could concatenate with a
  stranded message.
- Exit `64`: the invocation or message file is invalid; nothing was sent.

Diagnostics on stderr name the state and whether anything was sent. The script
never prints the captured composer or transcript. Remove the exact temporary
file after `SENT`. Retain it after a nonzero result until the refusal is handled
or the uncertain delivery is reported; never remove temporary messages with a
glob.

## 4. Back off on a pre-send refusal

For `OCCUPIED`, `DIALOG`, or `UNKNOWN`, retry the same guarded command after
roughly **5 seconds, 15 seconds, 45 seconds, and 2 minutes**. Each invocation
classifies again immediately before any paste and sends as soon as the pane is
safe.

If all four retries refuse, postpone the message rather than dropping it. Carry
on with work that does not depend on delivery and retry when you next surface.
Raise it with the user only when communication itself blocks progress, such as
a merge request whose verdict is required.

Do not apply this retry policy to `DELIVERY_UNVERIFIED`. Stop touching the pane
and report the uncertain delivery, including the target and the script's exact
diagnostic.

## Classifier contract

The script captures the pane with ANSI attributes and joined wrapped lines:

    tmux capture-pane -p -e -J -t <target>

It recognizes four states and fails closed:

- **`DIALOG`**: a footer such as “Enter to select,” “Enter to confirm,” or “Esc
  to cancel” owns the pane. Digits select and Enter confirms, so no key is safe.
- **`OCCUPIED`**: plain-styled text follows the `❯` Claude Code prompt or `›`
  Codex prompt. Literal prompt glyphs inside the draft do not start a new
  composer. Multiline and pasted drafts are occupied.
- **`CLEAR`**: the prompt is bare, contains only a recognized empty-composer
  placeholder, or contains only SGR-dim autofill text that typing replaces. A
  structurally recognized active-turn footer with no visible composer is also
  clear because the client queues typed input for the running turn.
- **`UNKNOWN`**: the capture, target, or layout supplies none of the required
  evidence. Unknown is always non-sending.

A passive toast above an intact clear composer is `CLEAR`, even when the toast
contains numbered options. The optional Claude feedback survey is one example.
The options render in the transcript area above the composer, and the footer is
the ordinary mode footer rather than a dialog footer. Never dismiss a toast
before sending; it belongs to the operator.

`-e` is mandatory. A plain capture can render a grey autofill suggestion like
typed text. Cursor position is corroboration only: `cursor_x` has been observed
at `2` while a real draft occupied the composer. An emptiness regex such as
`grep -cE "[❯›] $"` is also insufficient because trailing ANSI codes make it
fail on a clear prompt.

## Delivery and verification guarantees

The script owns the sequence that callers previously had to reproduce:

- It classifies before any keystroke and sends only from `CLEAR`.
- It reads the UTF-8 message file once, supplies that same value to a uniquely
  named tmux buffer, uses bracketed paste with literal LF preservation, deletes
  that buffer after paste, waits 50 ms for the terminal interface to process
  the paste, and sends Enter in a separate tmux call.
- It re-captures without printing the capture. Submission is verified from the
  resulting composer state, never merely from message text appearing in the
  transcript.
- Verification waits on an exponential schedule of 50, 100, 200, 400, 800,
  and 1600 ms. If the entire composer still equals the message file after that
  3.15-second window, the script sends the one permitted recovery Enter and
  verifies for one more 3.15-second window. Whole-value equality is the safety
  guard: the recovery can submit only the sender's own payload. A prefix,
  substring, or mixed-text match must never receive another key.
- It never sends Esc, `C-u`, or any other command that clears or cancels state.

Bracketed paste is required for Codex. `send-keys -l` can trigger its
paste-burst detector, making Enter finalize a chunk instead of submitting and
leaving `[Pasted Content ...]` or raw text in the composer.

## Diagnose an uncertain delivery

For `DELIVERY_UNVERIFIED`, inspect without typing:

    tmux capture-pane -p -e -J -t <target> | tail -20

If the composer contains different or mixed text, stop and report it. Do not
try to submit or clear it.

One narrow manual exception remains for a dialog raised by the sender's own
paste. A large paste can trigger a mode suggestion while leaving the message
undelivered. Esc followed by one Enter is permitted only when all three facts
are visible: the dialog names an input-mode suggestion rather than an operator
question; the just-pasted message is still the complete composer contents; and
the dialog appeared directly in response to that paste. Esc dismisses the
suggestion while preserving the composer, after which Enter submits it. If any
fact is uncertain, do not touch the pane.

Whenever a capture supports attribution rather than delivery, use `-e` there
too. Dim autofill text is a suggestion, not an instruction the operator wrote;
do not copy it into a status record or treat it as authorization.
