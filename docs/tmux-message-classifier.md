# tmux-message composer classifier

This document records the evidence behind the composer classifier in the
`tmux-message` skill's guarded sender: which pane shapes it accepts for each
supported agent CLI, the client versions and dates each shape was observed on,
and the timing of its paste and submit checks. It is for whoever changes the
classifier or its tests; agents sending messages need only the skill itself. It
describes `skills/tmux-message/scripts/tmux_send.py` and its tests in
`skills/tmux-message/tests/test_tmux_send.py`.

## Capture

The sender captures ANSI attributes one pane row per line:

    tmux capture-pane -p -e -t <pinned-pane-id>

It deliberately omits `-J`. That flag joins every row the terminal marks as
soft wrapped onto the next row. Claude Code and Antigravity CLI draw
full-width rows (composer borders, padded blank rows) that the terminal marks
that way, so `-J` merged a border with its prompt, with the row above it or
with the status row below it, and the live composer went unrecognized; Codex
history rows were joined the same way. On 2026-10-16, Claude Code 2.1.302,
Codex 0.156.1, Antigravity CLI 1.3.0 and OpenCode 1.18.31 in 100-column panes
produced the same composer text with and without `-J` for short, wrapped and
unbroken-token drafts, because each draws its own composer line breaks; the
only difference was trailing padding `-J` kept on a short Codex draft. Cursor
CLI was not rechecked live; none of its 65 recorded captures from 2026-10-02,
taken with `-J` at widths 80 to 120, contained a joined row. A capture whose
rows are joined anyway is not split back and classifies as `UNKNOWN`.

## Recognized composers

The sender recognizes only anchored Claude Code, Codex, Antigravity CLI, OpenCode, and
Cursor CLI composer regions. The Antigravity CLI 1.1.27 and OpenCode 1.18.31
shapes were live-checked on 2026-09-14, and the Cursor CLI 2026.10.01 and
2026.09.18 shapes on 2026-10-02:

- Claude Code requires full-width top and bottom borders and one column-zero
  `❯` prompt inside them. Clear-versus-occupied classification comes from that
  bordered composer itself; it does not depend on the wording or presence of a
  status row below the bottom border, but every nonblank row below that border
  must be indented at least two columns, as Claude Code 2.1.280 and 2.1.292
  draw their status and panel rows (observed 2026-10-07); any other row means
  the bordered box is history rather than the live composer. The terminal
  cursor is not consulted: the sandboxed client hides it and parks it in the
  pane's last column, not necessarily on a composer row.
  The sandboxed shape was reported from a live pane (cursor hidden at 79,18 on
  80x24) and replayed from a host capture; no raw capture of a sandboxed pane
  backs it. Not
  observed: what happens when input focus is elsewhere, such as a
  background-subagent panel or an overlay that leaves the box drawn. The
  expected outcome is that the paste goes to that control and the composer
  stays empty, so the sender reports `DELIVERY_UNVERIFIED paste-not-observed`
  without sending Enter; pasted characters may still act on that control.
  When one or more background subagents add rows beginning with their `●`/`◯`
  selection markers below the composer, exactly one such row must carry the
  selected marker, and that row must be `main`. A composer beginning with the
  client-native `Message @` agent placeholder is never accepted in this shape.
  Dialog footers and other interfaces without the bordered prompt still fail
  closed.
- Codex requires one column-zero `›` prompt followed by its structural spacer
  and bottommost footer. The footer is the model/directory summary, the
  full-width, entirely dim editing status line used while a draft is present,
  or the exact `tab to queue message` row (with an optional right-aligned
  `N% context left`) that replaces the summary when a draft is present during a
  running turn; a short dim row or later nonblank output fails closed. Codex
  0.160 adds a second footer row under the summary row: `? for shortcuts` with
  the warnings notice right-aligned when the composer is empty, only the
  right-aligned warnings notice while it holds a draft, and `tab to queue
  message` while a draft is present during a running turn. Each such pair is
  accepted with the blank spacer above the summary row, and none of the lower
  rows is a footer by itself. Checked 2026-10-07 on Codex 0.156.1 and 0.160.1,
  including a paste and submit into an idle pane and into a pane mid-turn.
  The `/review` custom-instructions field in Codex 0.156.1 draws the same
  prompt over an `enter submit · esc back` row, which passes the summary-row
  shape, so a bottommost row with those words is `DIALOG`.
  The summary row is recognized by its ` · ` separator, so a Codex
  `tui.status_line` setting with a single item draws a row without one and
  leaves the pane `UNKNOWN layout` whether idle or holding a draft, unless a
  warnings notice happens to share that row, as it can before Codex 0.160;
  configure two or more items, or leave the setting unset, in a pane that
  should receive messages. Checked 2026-10-16: Codex 0.153.3 was refused idle
  and with a draft, and Codex 0.156.1, whose row carried a warnings notice, was
  accepted because that notice supplies the separator.
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
- Cursor CLI hides the terminal cursor, so its composer is anchored by the rows
  around it. The bottommost nonblank rows must be two adjacent rows indented two
  columns whose text is dim (the model row and the workspace row), optionally
  preceded by one `(shift+tab to cycle)` mode row. Above them must be a blank
  spacer row and a blank padding row, then the composer rows, then a blank
  padding row. The first composer row starts with `→` at column two and later
  rows are indented to the same text column. An empty composer is a dim
  placeholder (`Plan, search, build anything`, or `Add a follow-up` while a
  turn runs, optionally followed by a dim `ctrl+c to stop`) whose first
  character is redrawn in reverse video as the hidden cursor; that one
  character is not typed text, but only when everything after it is dim. An
  all-dim composer without that reverse-video character is an unfocused
  placeholder and is `UNKNOWN layout`, as is a composer block with no visible
  character (hidden or clipped draft text). A picker or the workspace-trust
  prompt ends with an `Enter to select` footer and is `DIALOG`. A row inside the
  follow-ups panel above the composer reading `editing · enter done` means a
  queued entry is open for editing and input belongs to the panel, so it is
  `DIALOG`; the same words elsewhere in the conversation do not match. The
  tool-approval prompt (`Waiting for approval`, options ending `(y)`, `(tab)`,
  `(esc or n)`) replaces the composer on screen, so it is `UNKNOWN layout`.
  Any other change to the bottom of the screen, including
  the transient `Press Ctrl+C again to exit` and `Run Everything: OFF`
  notices, is `UNKNOWN layout`. Interrupting a turn with Ctrl+C restores the
  interrupted prompt into the composer as a draft, which is `OCCUPIED`. The
  follow-ups panel's `enter steer` hint does not block delivery: it describes
  Enter on an empty input, and the sender presses Enter only after the paste
  has made the input non-empty. Not observed: overlays other than those named
  here.
- Continuation rows require the clients' two-column continuation indentation.
  Quoted or pasted prompt and border glyphs inside a draft do not become
  structural markers.
- Bare composers and entirely SGR-dim suggestions are `CLEAR`. A native paste
  placeholder anywhere in the composer is `OCCUPIED` regardless of styling,
  because it represents stored input rather than a replaceable suggestion.
- Any dialog marker, mixed plain-plus-dim text, malformed region, or absent
  composer fails closed as `DIALOG`, `OCCUPIED`, or `UNKNOWN layout`.

## Paste and submit verification

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
