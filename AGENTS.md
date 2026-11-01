# Rules for editing skills in this repository

These rules bind anyone, human or agent, who writes or edits a skill under
`skills/`, shared or private.

- **A skill holds only what an agent needs to act.** A reason of one or a few
  sentences may stay with the rule it explains. Incident stories, persuasion,
  measurements and other evidence do not belong in a skill, and neither do
  pointers to where that rationale lives. Condense an anecdote into the rule
  it supports. Evidence a maintainer needs goes in `docs/`, which no skill
  tells an agent to read. Only shared skills get committed docs: a private
  skill's evidence goes in `docs/do_not_commit/`, which stays untracked.
- **Split what only one case needs.** When instructions for one harness,
  client or launch type grow long, move them to a file in the skill's own
  directory that the skill tells only that case to read, as `new-session`
  does with `sandbox.md` and `token-cost` with its `references/` files.
- **Point at another skill; do not restate it.** When a skill relies on
  another, name it and say what to use it for. Do not repeat its procedure,
  its rules, or internal mechanics the caller does not need to act on: a
  restated copy drifts from the skill that owns it, and the reader follows
  whichever copy it read last.
- **Do not restate the agent instructions.** A rule that belongs in the
  user's global agent instructions is not repeated in a skill: skills are
  shared, so a copy imposes one user's rules on every user and drifts from, or
  contradicts, the global file actually loaded. Usually a skill does not point
  at those rules either: a session follows its agent instructions without
  being told to. Point at them generically only where missing one would be
  costly: landing a change points at any merge rules, as `implement` does. A
  prompt or brief for another session or subagent always names the
  instruction files by path and says they bind, because that session may run
  under a different global file or none; `implement` and `review-loop` do
  this.
