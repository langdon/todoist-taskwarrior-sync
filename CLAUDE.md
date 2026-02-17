# todoist-taskwarrior-sync

## What this project is

A fork of [adam-gaia/todoist-taskwarrior-sync](https://github.com/adam-gaia/todoist-taskwarrior-sync) — a Python CLI tool for two-way sync between Todoist and Taskwarrior. Fork repo: `langdon/todoist-taskwarrior-sync`.

## Current state

- **`import-v1` command** — one-way Todoist → Taskwarrior import using the current REST API v1. Working, idempotent, dry-run by default.
- **`sync` command** — two-way sync logic exists but depends on deprecated `todoist-python==8.1.4` library (Sync API v8/v9). Functionally broken.
- **Goal:** Port `sync` to the v1 REST API so two-way sync works again.

## Project layout

```
todoist_taskwarrior/
  cli.py              ← All CLI commands (configure, sync, clean, import-v1)
  utils.py            ← Field conversion (priority maps, dates, recurrence)
  errors.py           ← Custom exceptions
pyproject.toml        ← Dependencies (poetry), CLI entry point
RUNBOOK.md            ← One-way migration runbook
tests/                ← Test suite
```

## Key conventions

- **Branch:** Active development on `todoist-v1-import` (fork branch)
- **Remotes:** `origin` = upstream (adam-gaia), `fork` = langdon fork
- **CLI entry point:** `titwsync` via `todoist_taskwarrior.cli:cli`
- **Auth:** `TODOIST_API_KEY` env var, Bearer token for REST API
- **Taskwarrior UDAs:** `todoist_id` (string, join key), `todoist_sync` (date, last sync timestamp)
- **Default behavior:** Dry-run. Explicit `--apply` required for writes.

## For agents (Codex, Claude Code, etc.)

1. **Verify issue is open** — before doing any work, confirm the referenced issue exists in `langdon/todoist-taskwarrior-sync` and is OPEN. If closed, missing, or wrong repo, STOP and report.
2. Read this file first.
3. Read `RUNBOOK.md` for the migration context.
4. Each build task has a self-contained prompt as a `## BUILD PROMPT` comment on the GitHub issue. Execute the prompt for your assigned task.
5. Write code to `todoist_taskwarrior/`. Write tests to `tests/`.
6. Do not modify `~/.taskrc` or Taskwarrior UDA definitions.
7. Run `python -m pytest tests` before delivering.

## Build & run

```bash
# Install dependencies (poetry)
poetry install

# Or with pip
pip install -r requirements.txt

# Run CLI
TODOIST_API_KEY=<key> titwsync --help
TODOIST_API_KEY=<key> titwsync import-v1 --dry-run
TODOIST_API_KEY=<key> titwsync sync
```

## Relationship to other projects

- Tracked in the AI control plane (`~/cloud-sync/areas/meta/ai-control-plane/`) with slug `tasks` (being wound down) and as a standalone resource.
- The Virtual Assistant (`langdon/virtual-assistant`) reads from Todoist; this tool syncs Todoist ↔ Taskwarrior. They are complementary but independent.
