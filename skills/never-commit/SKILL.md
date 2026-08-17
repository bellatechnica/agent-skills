---
name: never-commit
description: The classes of content that must never enter a git repository's history - credentials, personal identity, internal network and machine detail, absolute local paths, vendor naming residue, unlicensed third-party content, citations to rewritable commit hashes, and references to anything the reader cannot obtain - with the detection signal and the usual false positive for each. Use when reviewing a change before it lands, sweeping a repository after the fact, or deciding whether something belongs in a committed file or in machine-local config. Before a change lands it is the gate for whoever lands it, whether the author committing directly or a reviewer merging someone else's branch; after it lands, the sweep is history-audit.
---

# What must never enter a repository's history

One list, two uses. **Before a change lands** it is a gate — the cheap
moment, when fixing it costs one amended commit or one rebase. The gate
belongs to whoever lands the change: the author checks their own diff
before committing to the trunk, and where a separate reviewer merges
branches, that reviewer checks again. **After it lands** it is an
audit — the expensive moment, when the only complete cure is rewriting
every descendant sha and coordinating every branch in flight.

That asymmetry is the whole reason this list exists. **Deleting the
content in a later commit does not remove it**: it stays in the object
store, in every clone, and in anything that mirrored the repo. Whoever
lets one through, author or reviewer, has not deferred the cost, they
have multiplied it.

Every class below carries the signal to look for AND the false positive
that most often wastes the search. Read the hit before flagging it —
most greps here fire on ordinary code.

## Credentials

Any secret that authenticates, in any form, including one labelled
sample, expired, revoked or test.

- **Signal**: `sk-`, `AKIA`, `ghp_`, `gho_`, `xoxb-`, `xoxp-`, `AIza`,
  `-----BEGIN`, `api_key`, `secret_key`, `password=`, `.pgpass`, and
  credentials embedded in a connection URL (`scheme://user:pass@host`).
- **False positive**: `api_key` is almost always the NAME of an
  environment variable (`api_key_env`), not a value. `sk-` collides
  with ordinary English (`ask-the-scheduler`, `task-pipeline`) and with
  placeholders (`sk-test`).
- **Where it belongs instead**: a machine-local file the repo ignores.

An expired credential is still a credential: it proves the shape, the
account and often the tenant, and "expired" is a claim nobody can
verify from the diff.

## Personal identity

Real names, personal email addresses, phone numbers — where a role
address or a project identity belongs.

- **Signal**: personal email domains in tracked files; any identifier
  the project has named as sensitive; and **every commit's author and
  committer email across all refs** —
  `git log --all --format='%ae' | sort -u` — because a personal address
  sits in git metadata with no tracked line ever mentioning it.
- **Never choose a contact identity on the user's behalf.** Where an
  outbound identity is genuinely needed, it is theirs to pick.

## Internal network and machine shape

- **Signal**: private ranges (`10.`, `192.168.`, `172.16-31.`, `127.`,
  `169.254.`), internal hostnames, machine-name patterns
  (`DESKTOP-*`), ports tied to one operator's box.
- **False positive**: a private-range check inside source is usually a
  defensive blocklist, not a leaked address.

## Absolute local paths

- **Signal**: `/home/<user>/`, `/mnt/<drive>/`, `C:\Users\`.
- **Before recommending a change**, check whether the project already
  states where deployment-specific values belong (unit files, local
  config) — say what that convention implies rather than inventing one.

## Vendor and product naming residue

Any name the product used to carry, or a third-party tool name embedded
in comments, meta-keys or config, beyond whatever term prompted the
search.

## Unlicensed third-party content

Long foreign-language or domain-specific blocks in fixtures, where the
repo cannot satisfy the licence.

- **Judge by construction, not by content**: templated helpers and
  role-labelled ids (`unrelated-1`, `inject-1`) read as synthetic.
- This is a licensing question, not a secrets one, and an uncertain
  call belongs with whoever wrote the fixture rather than decided
  unilaterally.

## Citations to a rewritable commit hash

A doc or comment pinning a claim to a sha is good practice — until the
sha it names is rewritten, and every such citation stops resolving.

- **Signal**: `git grep -noP '\b[0-9a-f]{7,40}\b'`, then resolve each
  candidate with `git log -1 <hash>`.
- **Rule**: cite shas already on the trunk. A sha from an unlanded
  branch, or from a history slated for rewrite, is a dangling citation
  the moment it lands.
- **False positive**: projects with their own content-addressed ids
  (fingerprints, run ids, lease ids) match the same regex. Rule each in
  or out by resolution and context, never by pattern length.

## A reference to something the reader cannot obtain

The sibling of the section above, and the worse one. A sha citation
resolves until someone rewrites history; this never resolved for any
reader but its author, and nothing about it looks broken at review time
— the author can open it, so it reads as a working link.

- **Signal**: extract every repo-relative path from tracked files
  (`git grep -ho '<ignored-dir>/[A-Za-z0-9._/-]*'`), then test each for
  existence AND tracked status. Existence alone is not the test: the
  dangerous ones are the paths that DO exist locally.
- **The signal the grep cannot give you**, and it is the worse form: a
  deferral that names no file at all — "measured and written up
  separately as a proposal". Nothing to grep, no link to break, no way
  to find the gap except by already knowing the document exists. A
  dangling path announces itself; this does not. It needs a human
  reading the sentence and asking *where would I go to read that.*
- **Rule**: describe the source in the committed text — what it was,
  what it covered, when it was taken — instead of pointing at it. That
  is what a stranger can use; the path is what only the author can use.
- **The remedies differ and picking the wrong one makes it worse.** For
  EVIDENCE, delete the pointer and state what the source was — do NOT
  haul the evidence into the committed document, which breaks the rule
  the pointer was serving. For a deferred DECISION, the sentence exists
  because something needs saying, so say it inline or promote the
  document that says it. Deleting is right for evidence, never for a
  decision.
- **False positive**: naming a directory rather than a file
  (`docs/do_not_commit/`) is a statement about where a class of material
  lives, not a citation, and stays true in every clone.

## The ignore-rule reality check

A path being ignored today says nothing about whether it was ever
tracked.

- `git log --all --full-history -- <path>` must return NOTHING.
- Confirm the rule actually matches with `git check-ignore -v <path>`
  rather than inferring it from the pattern text.
- A worktree or scratch directory created inside the repo at a
  non-ignored path pollutes every session's status output and is one
  careless `git add -A` from being committed wholesale.
