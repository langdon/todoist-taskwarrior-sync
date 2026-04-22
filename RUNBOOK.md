# todoist-taskwarrior-sync Runbook

## Running (container)

```bash
make build                 # first time, or after Containerfile changes
make sync-dry              # preview — no writes to either side
make sync                  # write changes to Taskwarrior and Todoist
```

`TODOIST_API_KEY` must be set in your shell environment. The Makefile validates
this and exits early if it is missing.

## Running (local venv)

```bash
cd todoist-taskwarrior-sync
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install --no-deps .
export TODOIST_API_KEY='<your-token>'
./titwsync sync --dry-run
./titwsync sync --apply
```

The venv breaks any time the system Python minor version bumps. Recreate it
with the same commands above. Prefer the container for long-term stability.

## Todoist API situation

`todoist-python==8.1.4` uses the **Todoist Sync API v1**. Todoist shipped
v2, encountered serious problems, and had to partially walk it back. The
situation remains unstable. If sync starts failing with HTTP errors:

1. Check whether Todoist has changed their API endpoints
2. There is no maintained drop-in replacement for `todoist-python`; any fix
   likely means patching `todoist_taskwarrior/client.py` directly

## Commands

| Command | Effect |
|---------|--------|
| `sync --dry-run` | Preview two-way sync, no writes |
| `sync --apply` | Apply two-way sync to both sides |
| `import-v1 --dry-run` | Preview Todoist → Taskwarrior only |
| `import-v1 --apply` | Apply one-way import (never writes to Todoist) |

## Rollback

If a sync run corrupts Taskwarrior state, restore from backup:

```bash
rm -rf ~/.task
mv ~/.task.backup-<timestamp> ~/.task
cp ~/.taskrc.backup-<timestamp> ~/.taskrc
```

## Notes

- Default for all commands is dry-run. Writes require `--apply`.
- Conflict resolution: whichever side has a more recent `modified`/`updated_at`
  timestamp wins (UTC-normalized via `_to_utc_timestamp`).
- `todoist_id` UDA is the join key; `todoist_sync` UDA tracks last sync time.
- The `taskw` fork dep (`git+git://github.com/matt-snider/taskw`) has been
  removed — PR #121 (parse uuids with recur) was merged and released as
  `taskw>=2.0.0` on PyPI.
