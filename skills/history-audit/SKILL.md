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

### 3. Widen past the named term — sweep every `never-commit` class, every time

Load the `never-commit` skill and read it before this step. It defines
the classes, their signals and their usual false positives; if it and
this section ever disagree about what counts, `never-commit` is the
definition and this is the search.

For each class in `never-commit`, search tracked files (`git grep`) AND
history (`git log --all -S/-G`) with its signals, and read every hit's
diff past its false positive before classifying it. History-specific
additions:

- **Identity in commit metadata**: list every author AND committer
  email across all refs (`git log --all --format='%ae%n%ce' | sort -u`)
  and check each against the project's approved outbound identity; ask
  if none is named. Search content for personal email domains (gmail,
  yahoo, outlook, qq, 163 and the like), and ask for the project's
  sensitive identifiers if none are known.
- **Third-party account identifiers**: confirm they never reached
  tracked files or history, even when they live in a gitignored local
  directory.
- **Fixtures**: flag long foreign-language or domain-specific text
  blocks in test and fixture files, and hand an uncertain call to the
  fixture's author.
- **Absolute local paths**: report them even where the project's
  convention for deployment-specific values covers them, after saying
  what that convention implies.
- **Hash citations**: sweep docstrings and comments too, not just docs.
  Resolve each candidate with `git log -1 <hash>` (or
  `git cat-file -t <hash>` for exact-length checks). Every resolvable
  citation stops resolving after a rewrite and counts toward its price
  (§5).

### 3b. Traps that make a search lie

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

**A remembered hash identifies nothing after a rewrite.** Re-find
commits by author date (`git log --since/--until`) or subject
(`--grep`) — both survive the rewrite; the hash does not, and every
untracked record citing one (boards, handoff docs, scratch output) is
dangling until re-anchored this way.

### 4. Document the negative, not just the positive

For every "0 matches" / "clean" result, state the exact command used
in the findings doc, so the next reader can re-run it.

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
   auditing. **Execution is its own procedure** (scoping, an
   isolated clone, verification, carrying other branches forward,
   confirming old content is gone): hand it off once the decision to
   rewrite is made, and don't improvise it here.

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
