---
name: init-repo
description: Initialize a new repository in the current directory - gather languages/tooling, git init, write a tailored .gitignore, set up direnv (conda layout for Python), README, and an initial commit. Use for a new or empty project directory.
---

Initialize the current directory as a new repository. Adapt every step to the project's languages and skip steps that are already done (e.g. an existing `.git/` or `.gitignore`) — extend rather than overwrite existing files.

## 1. Inspect, then ask once

Look at existing files first to infer languages and tooling. Then ask everything that remains in a single AskUserQuestion round (recommended default listed first per question):

- **Languages/toolchains**, if not inferable from existing files or the user's invocation.
- **Environment details** where relevant — e.g. for Python: conda env name (default: directory name, lowercase) and Python version.
- Anything else that changes the result (e.g. license needed?). Default to no license and no remote setup unless asked.

Don't ask about things with an obvious default (README, initial commit, direnv itself) — just do them.

## 2. git init

If not already a repo: `git init -b main`.

## 3. .gitignore

Always include this base:

```gitignore
# IDE / editor
.vscode/
.idea/
*.swp
*.swo
.DS_Store
Thumbs.db

# Claude Code
.claude/worktrees/
.claude/*.local.*
CLAUDE.local.md

# Codex
.codex/worktrees/

# Project-specific
**/do_not_commit/
```

Then add sections only for the project's actual languages. For Python:

```gitignore
# Byte-compiled / optimized / DLL files
__pycache__/
*.py[cod]
*$py.class
*.so

# Distribution / packaging
build/
dist/
*.egg-info/
*.egg

# Virtual environments
.venv/
venv/
env/
ENV/
```

For other languages, add the standard equivalents (Node: `node_modules/`, `dist/`; Rust: `target/`; Go: binaries; etc.). Keep it to what this project will plausibly generate — no kitchen-sink templates.

## 4. direnv (.envrc)

Create `.envrc` appropriate to the toolchain, then run `direnv allow`.

Python with conda (the default for Python projects here — `layout anaconda` is in direnv's stdlib):

```bash
layout anaconda <env-name>
export PYTHONNOUSERSITE=1
PATH_add "$CONDA_PREFIX/bin"
```

If the conda env doesn't exist yet, create it first: `conda create -n <env-name> python=<version> -y`.

Other toolchains: use the matching direnv stdlib layout (`layout node`, etc.) or project env vars; if the toolchain needs nothing, skip `.envrc` entirely rather than creating an empty one.

WSL note: if the project is on `/mnt/*` (drvfs) and will have runtime data with heavy I/O (databases, caches), point that data at the native filesystem via env vars in `.envrc`, e.g. `export <PROJECT>_HOME="$HOME/.local/share/<project>"`.

## 5. Scaffolding

- `README.md` stub: project name as title plus a one-line description (from the user's invocation or ask-round answers).
- Minimal language scaffolding only if the user asked for it (e.g. `pyproject.toml`); an initialized-but-empty repo is a fine outcome.

## 6. Verify and commit

- Confirm direnv loads: `direnv exec . <toolchain sanity check>` (e.g. `python --version` resolving to the env).
- Confirm `git status` shows only intended files (nothing that should be ignored).
- Make the initial commit: `git add -A && git commit -m "Initialize repository"`.
