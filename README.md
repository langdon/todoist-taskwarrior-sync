# todoist-taskwarrior-sync

Two-way sync between Todoist and Taskwarrior.

Fork of [adam-gaia/todoist-taskwarrior-sync](https://github.com/adam-gaia/todoist-taskwarrior-sync),
itself forked from [webmeisterei](https://git.webmeisterei.com/webmeisterei/todoist-taskwarrior/),
originally from [matt-snider/todoist-taskwarrior](https://github.com/matt-snider/todoist-taskwarrior).

## Running (container — recommended)

Avoids Python version breakage across OS upgrades.

```bash
make podman-build
make sync-dry    # preview, no writes
make sync        # apply changes to both sides
```

`TODOIST_API_KEY` must be set in your environment. The container mounts
`~/.taskrc` (read-only) and `~/.task` (read-write).

For custom invocations:

```bash
make podman-run ARGS="import-v1 --dry-run"
```

## Running (local venv)

Faster to iterate on, but venv breaks when the system Python minor version bumps.

```bash
cd todoist-taskwarrior-sync
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install --no-deps .
export TODOIST_API_KEY='<your-token>'
./titwsync sync --dry-run
./titwsync sync --apply
```

Recreate the venv any time it breaks (e.g. after a Python minor version upgrade).

## Todoist API situation

This tool uses `todoist-python==8.1.4`, which targets the **Todoist Sync API v1**.
Todoist shipped a v2 API, had significant problems with it, and effectively had
to walk it back — the situation remains messy. The v1 library works but is
unmaintained and will not receive updates.

If sync starts returning errors, check whether Todoist has changed their API
surface again. The VA uses the REST API v1 (`/api/v1/`) directly rather than
this library, which has proven more stable.

## Configuration

`titwsync configure` writes `~/.titwsyncrc.yaml`. Run once to set up project
and tag mappings:

```bash
./titwsync configure \
  --map-project Inbox= \
  --map-project MyProject=myproject \
  $TODOIST_API_KEY
```

## Commands

| Command | Effect |
|---------|--------|
| `sync --dry-run` | Preview two-way sync, no writes |
| `sync --apply` | Apply two-way sync |
| `import-v1 --dry-run` | Preview Todoist → Taskwarrior only |
| `import-v1 --apply` | Apply Todoist → Taskwarrior only |

## Development

```bash
python -m pytest tests/
```

## License

MIT

## Authors

- 2018-2019 [matt-snider](https://github.com/matt-snider/todoist-taskwarrior)
- 2019– [webmeisterei](https://git.webmeisterei.com/webmeisterei/todoist-taskwarrior)
- 2022– [adam-gaia](https://github.com/adam-gaia/todoist-taskwarrior-sync)
