# todoist-taskwarrior-sync Runbook

Repo: `~/cloud-sync/resources/todoist-taskwarrior-sync`

## Install

```bash
cd ~/cloud-sync/resources/todoist-taskwarrior-sync
poetry install
```

## Env var setup

```bash
export TODOIST_API_KEY='<your-token>'
```

## Two-way sync (dry-run first)

```bash
titwsync sync --dry-run   # preview — no writes to either side
titwsync sync --apply     # write changes to Taskwarrior and Todoist
```

## One-way import (Todoist → Taskwarrior only)

```bash
titwsync import-v1 --dry-run
titwsync import-v1 --apply
```

`import-v1` never writes to Todoist. Useful if you only want to pull tasks in.

## Tests

```bash
python -m pytest tests/
```

## Rollback

If a sync run corrupts Taskwarrior state, restore from backup:

```bash
rm -rf ~/.task
mv ~/.task.backup-<timestamp> ~/.task
cp ~/.taskrc.backup-<timestamp> ~/.taskrc
```

## Notes

- Default behavior for all commands is dry-run. Writes require `--apply`.
- Conflict resolution uses UTC-normalized timestamps (`_to_utc_timestamp`). Whichever side has a more recent `modified`/`updated_at` wins.
- `todoist_id` UDA is the join key; `todoist_sync` UDA tracks last sync timestamp.
- Initial one-way migration artifacts have been discarded — the migration is complete.
