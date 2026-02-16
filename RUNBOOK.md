# Taskwarrior Todoist Migration Runbook (One-way)

## Install
```bash
cd ~/loc-areas/meta/tasks/taskwarrior-todoist-sync/todoist-taskwarrior-sync
python3 -m venv .venv
. .venv/bin/activate
PIP_CACHE_DIR=$PWD/.pip-cache pip install -e .
```

## Env var setup
```bash
export TODOIST_API_KEY='<your-token>'
```

## Dry-run (no Taskwarrior writes)
```bash
cd ~/loc-areas/meta/tasks/taskwarrior-todoist-sync/todoist-taskwarrior-sync
. .venv/bin/activate
titwsync import-v1 --dry-run
```

## Apply (one-way Todoist -> Taskwarrior)
```bash
titwsync import-v1 --apply
```

## Rollback
```bash
# Restore backups created during cutover
rm -rf ~/.task
mv ~/.task.backup-<timestamp> ~/.task
cp ~/.taskrc.backup-<timestamp> ~/.taskrc
```

Notes:
- This runbook intentionally does not use bidirectional sync.
- `titwsync import-v1` does not write to Todoist.
