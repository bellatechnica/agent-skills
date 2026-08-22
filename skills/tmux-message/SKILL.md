---
name: tmux-message
description: Deliver a message to another Claude Code or Codex session running in a tmux pane - addressing, inspecting the target before typing, sending safely through bracketed paste, backing off when the input line is occupied, and verifying delivery. Use whenever pinging, replying to, or handing something to a session in another tmux window or pane, including merge requests, verdicts, handoff prompts and status pings.
---

# Message another session through tmux

Keystrokes injected into someone else's pane are indistinguishable from
the operator typing them. Every rule here exists because that is true:
the failures are not "the message did not arrive", they are "the message
arrived as an answer the operator never gave".

Five steps, in order. Do not compress them into one command — step 2's
output must be READ before step 3 runs.

## 1. Address

- **The target**: `<session>:<window>` for a single-pane window,
  `<session>:<window>.<pane>` otherwise. `tmux list-windows -a` to find
  it by name; window *indices renumber*, so re-resolve a stale address
  by name rather than trusting one from an earlier turn.
- **Your own address**, when the target needs to reply:
  `tmux display-message -p -t "$TMUX_PANE" '#S:#I.#P'`. Include it in
  the message — a session that has to guess how to answer you usually
  answers the user instead.
- A **busy target is fine**. The CLI queues typed input for its next
  turn; do not wait for an idle prompt. Busy is not the blocking
  condition — an occupied input line is (step 2).

Every message starts by identifying its sender in this exact shape:

    From <session>:<window>.<pane> (<short role>):

For example: `From 0:10.0 (backfill-fixes):`. Use the known current sender
address and the stable human-readable responsibility or window name as the
role. Do not re-resolve a known address for every message; resolve it only when
it is unknown or stale, pane numbering may have changed, or communication is
not behaving as expected. This prefix is required for handoffs, replies,
follow-ups, status pings, merge requests, and one-line notices alike. A target
often has several workstreams in its transcript; the prefix makes authorship
and reply routing clear without reconstructing which pane sent the text.

## 2. Inspect the pane BEFORE typing

**This must be its own tool call, whose output you read before issuing
the send.** Piping `capture-pane` into the same command as
`paste-buffer` is not an inspection: the output only becomes visible
after the keystrokes have fired. That exact shortcut once typed a long message
into an open dialog and confirmed "Yes" on the operator's behalf.

    tmux capture-pane -pe -t <address> | tail -20

`-e` keeps attributes and is what makes the next distinction possible.
Four states:

- **A dialog or other non-prompt UI** — a footer like "Enter to select ·
  Tab/Arrow keys to navigate · Esc to cancel", numbered options,
  checkbox rows. The pane is not in input mode at all. Digits select,
  Enter confirms, and your message becomes the operator's answer. Do not
  send **anything**, Esc included — cancelling is itself a state change
  the operator did not ask for. Go to step 4's backoff.
- **A passive toast above a live composer** — numbered options that are
  NOT a dialog, most commonly the optional feedback survey ("How is
  Claude doing this session? 1: Bad 2: Fine 3: Good 0: Dismiss"). Numbered
  options alone do not mean blocked; read the LAYOUT instead. It is a
  toast, and delivery is safe, when all three hold: the options render
  ABOVE the composer border, in the transcript area; the composer itself
  is present and clear (bare `❯`, `cursor_x` ≈ 2); and the footer is the
  ordinary one ("⏵⏵ auto mode on · N shells · ← for agents"), not a
  dialog footer. **Send normally — do not back off, and do not dismiss
  first.** A survey addressed to the operator is theirs to answer, so
  clearing it is a state change needing their authorization, exactly like
  a draft. When they DO authorize it, a single `tmux send-keys -t <addr>
  '0'` with NO Enter dismisses it cleanly: verified against the survey
  above a merger session — the toast disappeared, the composer stayed
  bare and `cursor_x` stayed 2, so the digit was consumed by the toast
  and never became text. Mistaking this state for a dialog costs a real
  delivery: it stranded a merge request until the operator was asked.
- **An occupied input line** — plain-styled (non-dim) text after the
  prompt: `❯` in Claude Code or `›` in Codex. That is a real unsubmitted
  draft. Do not type into it: your text appends to theirs and your Enter
  submits both. Go to step 4's backoff.
- **A clear input line** — bare `❯` or `›`, or either prompt followed by
  text wrapped in SGR dim (`\e[2m`), which is the CLI's grey autofill
  suggestion and is replaced by typing. Safe to send. Placeholders such
  as "Press up to edit queued messages" or "Use /skills to list available
  skills" are also clear — they mean empty-with-history.

Second signal when dim-vs-plain is ambiguous:
`tmux display-message -p -t <address> '#{cursor_x}'` — cursor parked
right after either prompt (x≈2) means suggestion; cursor after the last
character means typed. This signal applies to both Claude Code and Codex.
**A plain capture without `-e` renders both identically**, which is why
the flag is not optional.

**One capture answers TWO questions — "may I type here" and "may I
attribute this" — and the dim marker settles both.** `-e` is required
whenever a capture is used as EVIDENCE, not only before typing: a plain
capture renders the grey autofill suggestion byte-identical to text the
operator submitted, and an invented instruction propagates into durable
records as provenance. And the suggestion is AIMED, not random — it
proposes exactly the action the reader was hoping to see, including
live writes on nobody's authority — so verify hardest when the text
agrees with you. Whoever runs the may-I-type check will otherwise skip
the may-I-attribute check; state both, every capture.

An emptiness guard like `grep -cE "[❯›] $"` fails on trailing ANSI codes.
Over-strict is the safe direction: expect false refusals, and re-inspect
rather than loosening the pattern blindly.

## 3. Send

For a multiline message, an exact payload, or any message containing shell
quotes, first create a uniquely named file under `/tmp` with `apply_patch`.
The file contains the message itself, with its real LF characters. Do not
generate that file with shell `echo`, `printf`, a here-document, or a serialized
string. Then load it before pasting:

    tmux load-buffer -b <unique-buffer> /tmp/<unique-message-file>
    tmux paste-buffer -prd -b <unique-buffer> -t <address>
    sleep 0.05
    tmux send-keys -t <address> Enter

- Remove the exact temporary file after delivery; never use a glob or a shared
  path for this.
- Use a buffer name unique to this sender and delivery. `-d` deletes it
  after pasting, so it does not accumulate or collide with a later send.
- `paste-buffer -p` wraps the content in bracketed-paste control codes
  when the target requested them. `-r` preserves literal LF newlines.
  This is required for Codex: `send-keys -l` can trigger its paste-burst
  detector in chunks, making Enter finalize a chunk instead of submitting
  and leaving `[Pasted Content ...]` or raw text in the composer.
- The short delay gives the TUI time to finish handling the explicit paste
  before submission. It is not a substitute for verification.
- A simple one-line message containing no shell quote may still use
  `tmux set-buffer -b <unique-buffer> -- '<message>'`. Do not rewrite message
  text to make shell quoting easier; use the file path above instead.
- Never concatenate `JSON.stringify(payload)` or another serialized string
  into a shell command that calls `tmux set-buffer`. JSON represents LF as the
  two characters `\n`, and POSIX double quotes do not decode that pair. The
  recipient then receives literal backslash-n text rather than line breaks.
- Enter goes in a **separate tmux call**. One message, one Enter.
- Do not fall back to one or more `send-keys -l` calls for message text.
  Splitting text makes Codex's burst behavior worse; even one large call
  can be internally consumed as several bursts.

## 4. When the line is occupied: back off, do not abandon

A dialog or a draft usually clears within a minute or two — the other
session finishes its turn, or the operator submits. Retry on an
exponential backoff: roughly **5s, 15s, 45s, 2min — four attempts over
~3 minutes**, re-inspecting each time (step 2, still as its own call),
and send the moment the line is clear.

If it is still occupied when the backoff is exhausted, **postpone the
message, not the session**. Carry on with any work that does not depend
on the delivery and retry when you next surface. Raise it with the user
only when the communication itself is what blocks progress — a merge
request you cannot proceed without, say, as opposed to a status ping.

Two failure modes, both wrong: waiting idle for a pane to clear, and
dropping the message while reporting the send as done.

**Never clear someone else's input**: no Esc, no `C-u`, no
`send-keys -X cancel`. Submitting or discarding a draft is theirs to do,
and a dialog you cancel is an answer you gave.

## 5. Verify delivery — by an EMPTY input line

    tmux capture-pane -pe -t <address> | tail -10

**Confirm the bottom composer is empty. Do NOT confirm merely that your
text appeared somewhere in the pane** — submitted text remains visible in
the transcript, while an unsubmitted paste is visible in the composer.
Visible text by itself proves nothing.

Empty means: bare `❯` or `›`, or one of those prompts followed only by a
dim suggestion or empty-composer placeholder. For Codex, `[Pasted Content
...]` or raw message text after the bottom `›` means the message is still
a draft. If the exact message you just pasted is still there and the pane
has not changed state, send Enter once more and re-verify. If the composer
contains different or mixed text, stop touching the pane and report it;
do not risk submitting someone else's draft.

If you suspect a mis-send into a dialog: stop touching the pane, and
report to the user exactly what was sent and exactly what the pane
showed. Do not try to undo it — every corrective keystroke is another
state change on their behalf.

**One exception to "never Esc" — the dialog YOUR OWN paste raised
(2026-08-14, verified):** a large paste can trigger the target CLI's
own suggestion dialog (Codex: "Create a plan?  shift+tab use Plan
mode  esc dismiss"), which holds your message undelivered while
`cursor_x` still reads ≈2 — a false-delivery mode cursor checks
cannot see, caught only by step 5's composer capture. When ALL THREE
hold — the dialog names a mode suggestion about input (not an
operator question), YOUR just-pasted text is still visible in the
composer, and the dialog appeared in direct response to your paste —
Esc dismisses the suggestion while preserving the composer, and a
bare Enter then submits. Verify by step 5 afterward. If any of the
three is uncertain, it is the operator's dialog: back off per step 4.
