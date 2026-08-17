---
name: history-audit
description: Audit a git repository's tracked files and full commit history for what should be absent — credentials, personal identity, internal network/machine details, vendor or product naming residue, unlicensed third-party content, hardcoded commit-hash citations — and produce a findings doc plus an honestly-priced rewrite-vs-forward-fix recommendation. Use when asked to audit a repo for secrets, PII, leaked internal details, or stale vendor references, to check "what's in our git history that shouldn't be," or before a public release or a history rewrite.
---

# History Audit

Read-only investigation of a repo's tracked files AND full commit
history, widened past whatever specific term prompted it, ending in a
findings doc that names exactly what was checked — not just what was
found.

## Binding defaults (override only if the caller says otherwise)

- Read-only: no tracked-file edits, no history rewrite, no
  `filter-branch`/`filter-repo` execution — not even a "dry run" that
  writes — during the audit itself.
- Never enter another session's linked worktree (`git worktree list`
  reports it) — read the listing, don't `cd` into it or run commands
  scoped to it.
- **Stop condition**: if a check turns up something that reads as an
  ACTUAL live credential — not a placeholder, not an env-var name, not
  a test fixture — stop immediately and report to the user before
  finishing the rest of the audit. Rotation precedes any rewrite; a
  rewrite does not un-leak a key that was ever pushed anywhere
  reachable.
- Findings go into the project's gitignored scratch location, never
  into a tracked file.

## Method

### 1. Establish repo shape first — it prices any rewrite before you argue for one

- `git rev-list --all --count` (total across all refs); per-branch
  count for the main line if relevant.
- `git worktree list`, `git branch -a` — note which branches currently
  have no worktree.
- Stale refs: `git show-ref | grep remotes` cross-checked against
  `.git/config` (`grep '\[remote'`) — a remote-tracking ref with no
  matching config section is orphaned; its own reflog
  (`git reflog show <ref>`) usually names exactly how it was created
  (e.g. a self-fetch `fetch . main:refs/remotes/x/main`, not a real
  remote).
- Merge strategy: merge commits present, or rebase-only?
- **Re-run the worktree/branch listing again near the end of the
  audit and diff against the first snapshot.** A repo under active
  multi-session use moves. If it moved — a worktree appeared or
  vanished, a branch tip changed, `main` itself advanced — that is
  direct, observed evidence for the coordination-cost argument later,
  not something to describe as hypothetical.

### 2. For the named term(s) — the vendor name, old product name, whatever prompted the audit

- Tracked files: `git grep -ni "<term>"`.
- History, two independent searches — they can disagree, report both
  counts: `git log --all -S"<term>" --oneline` (content added/removed
  in a diff) and `git log --all -i --grep="<term>" --oneline` (commit
  messages).
- **Read the actual diff for every hit** (`git show <commit> | grep -n
  "<term>"`) before classifying it. Do not classify by match count.
- Find the earliest touching commit and compute the blast radius:
  `git rev-list --count <earliest>^..<tip>` against the total. This
  single number is what tells you whether a rewrite is a cheap
  tail-trim or a whole-repo operation — an early commit means nearly
  every later commit gets a new hash.

### 3. Widen past the named term — sweep every category below, every time

**The classes themselves live in the `never-commit` skill**, with the
usual false positive for each; what follows is this audit's detection
method over a whole history rather than a single diff. Read that list
alongside this section — if the two ever disagree about what counts,
`never-commit` is the definition and this is the search. The same list
is the gate before a change lands, applied by whoever lands it, which
is where these are cheap to catch; every finding here is one that got
past it.

**Credentials** — tracked files and `git log --all -S/-G`: `sk-`,
`AKIA`, `ghp_`, `gho_`, `xoxb-`, `xoxp-`, `AIza`, `-----BEGIN`,
`api_key`, `secret_key`, `password=`, `.pgpass`, and a regex for
credentials embedded in a connection-string URL
(`scheme://user:pass@host`). Read every hit's diff — `api_key` almost
always means the *name* of an env var (`api_key_env`), not a value;
`sk-` collides with ordinary English ("a**sk-**the-scheduler",
"**task-**pipeline") and with test placeholders (`sk-test`).

**Personal identity** — personal email domains (gmail/yahoo/outlook/
qq/163/etc.) in tracked files and history; any personal identifiers the
project has previously named as sensitive (ask if none are known);
**every commit's author/committer email across all refs**
(`git log --all --format='%ae'`/`'%ce' | sort -u`), checked against the
project's approved outbound identity — not just content greps, since a
personal address can sit in git metadata with no tracked line ever
mentioning it.

**Internal network shape** — private IP ranges (`10.`, `192.168.`,
`172.16-31.`, `127.`, `169.254.`), internal hostnames, machine-name
patterns (e.g. `DESKTOP-*`). Read context before flagging: a
private-IP-range check inside source is usually a defensive blocklist,
not a leaked address.

**Absolute local paths** — `/home/<user>/`, `/mnt/<drive>/`,
`C:\Users\`, etc. Check whether the project already has a stated
convention for where deployment-specific values belong (e.g. unit
files vs. docs) before recommending a change — still worth reporting
either way, but say what the existing convention implies first.

**Vendor/product naming residue** — any name the product used to be
called, or a third-party tool name embedded in comments, meta-key
names, or config, beyond whatever term the requester already named.

**Third-party account identifiers** — confirm they never reached
tracked files even when they live in a gitignored local directory;
check history too, not just the current tree.

**Real content in fixtures** — scan test/fixture files for long
foreign-language or domain-specific text blocks (flag runs over N
characters). Judge synthetic-vs-scraped by construction — templated
helper functions, role-labeled IDs like `unrelated-1` or `inject-1` —
rather than by content alone, and hand an uncertain call to whoever
wrote the fixture instead of deciding it unilaterally. This is a
licensing question, not a secrets one.

**`.gitignore` reality check** — confirm claimed-ignored paths were
NEVER tracked, not just currently absent:
`git log --all --full-history -- <path>` must return nothing. Confirm
the ignore rule actually matches with `git check-ignore -v <path>`;
don't infer it from the pattern text alone.

**Hardcoded commit-hash citations** — grep tracked files (docs *and*
code — this shows up in docstrings and comments, not just design docs)
for standalone 7–40-char hex tokens:
`git grep -noP '\b[0-9a-f]{7,40}\b'`, then resolve each candidate with
`git log -1 <hash>` (or `git cat-file -t <hash>` for exact-length
checks). A real, resolvable one is a direct rewrite cost — every such
citation stops resolving after a rewrite — and it's easy to miss
because the hash itself reads as inert. Projects with their own
content-addressed IDs (fingerprints, run IDs, lease IDs) will produce
false positives against the same regex; rule each one in or out
individually by resolution and context, not by pattern length alone.

### 3b. Two traps that make a search lie

**A multi-word term can WRAP.** `git grep "<two words>"` misses the
instance split across two source lines in prose, a docstring or a
comment. Search the shortest distinctive token, or use a
whitespace-tolerant pattern (`\s+` between words), and compare the two
hit counts — a tolerant count exceeding the literal one is a wrapped
instance the literal search would have reported as absent.

**Scope decides the answer when auditing AFTER a rewrite.** Stale
branches, worktree branches and tags still point at pre-rewrite
commits, so `--all` reaches the old history through them and reports a
successful rewrite as a failure. Say which ref you scoped to: "clean on
`main`, still reachable in this clone until the remaining refs are
carried forward and the objects expire" is the honest claim, and it is
a different claim from "gone".

### 4. Document the negative, not just the positive

For every "0 matches" / "clean" result, state the exact command used
in the findings doc. A clean audit is only as trustworthy as its
documented search surface — the next reader has to be able to re-run
it, not take "checked" on faith.

### 5. Price a rewrite honestly before recommending one

- Blast radius (§2).
- Every ref that needs updating: branches with a worktree, branches
  without one, stale remote-tracking refs, reflogs.
- What breaks that isn't a ref at all: hash citations (§3), anything
  else in the product computed from or displaying a commit hash.
- What a rewrite does NOT fix: any existing clone or fetch outside
  this working directory keeps the old blobs regardless of what
  happens here.

### 6. Recommend, don't just enumerate

Default order — argue for the one that fits the findings, rather than
listing both neutrally:

1. **Rename/reword forward only, accept history as historical** — the
   correct default when nothing found is actually confidential; costs
   one normal commit through the project's normal review path.
2. **Full rewrite** (`git filter-repo`, never `filter-branch`) — only
   when something found is genuinely sensitive, or the requester
   insists after seeing the priced cost from §5. Coordinate through
   the project's standing merge/release process if it has one; never
   run it solo, and never as part of the same pass that's still
   auditing. **Execution is its own procedure** — scoping the
   rewrite, running it in an isolated clone, verifying it changed
   exactly what was intended, carrying other branches forward,
   confirming old content is actually gone. Don't improvise that
   here; hand it off once the decision to rewrite is made.

## Deliverable

A findings doc, in the project's gitignored scratch location
(`do_not_commit/` or equivalent), with:

- What's actually present, in tracked files and in history, separated
  by severity.
- The exact command used for every clean result.
- The rewrite cost priced for *this* repo specifically, not a generic
  estimate.
- A recommendation, argued from the findings, not a bare options list.
- Open questions routed to the right place: gaps in the audit's own
  brief go to whoever handed it off; product/policy calls (rewrite
  yes/no, what counts as an acceptable vendor reference, a licensing
  judgment on fixture content) go to the user.
