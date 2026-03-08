import click
import os
import sys
import datetime
import dateutil.parser
import io

import yaml
from taskw import TaskWarrior
from . import errors, log, utils, validation
from .client import TodoistV1Client

# This is the location where the todoist
# data was cached (legacy — kept for the `clean` command).
TODOIST_CACHE = '~/.local/share/task/todoist-sync/'
TITWSYNCRC = '~/.config/titwsync/titwsyncrc.yaml' # TODO: read XDG_CONFIG_DIR


config = None
taskwarrior = None

""" CLI Commands """


@click.group()
def cli():
    """Two-way sync of Todoist and Taskwarrior. """
    global config, taskwarrior

    is_help_cmd = '-h' in sys.argv or '--help' in sys.argv
    rcfile = os.path.expanduser(TITWSYNCRC)

    # Keep defaults resilient so commands can run with only an env API key.
    config = {
        'todoist': {
            'project_map': {},
            'tag_map': {},
        },
        'taskwarrior': {
            'project_sync': {},
        },
    }

    if os.path.exists(rcfile):
        with open(rcfile, 'r') as stream:
            loaded = yaml.safe_load(stream) or {}
            config['todoist'].update(loaded.get('todoist', {}))
            config['taskwarrior'].update(loaded.get('taskwarrior', {}))

    cfg_key = config['todoist'].get('api_key')
    if cfg_key in (None, '', 'REDACTED'):
        cfg_key = None

    api_key = os.getenv('TODOIST_API_KEY') or cfg_key
    if api_key:
        config['todoist']['api_key'] = api_key
    elif not is_help_cmd:
        log.error('Run configure first or set TODOIST_API_KEY. Exiting.')
        exit(1)

    # Create the TaskWarrior client, overriding config to
    # create a `todoist_id` field which we'll use to
    # prevent duplicates
    taskwarrior = TaskWarrior(config_overrides={
        'uda.todoist_id.type': 'string',
        'uda.todoist_sync.type': 'date',
    })


@cli.command()
@click.option('-p', '--map-project', metavar='SRC=DST', multiple=True,
              callback=validation.validate_map,
              help='Project names specified will be translated '
              'from SRC to DST. '
              'If DST is omitted, the project will be unset when SRC matches.')
@click.option('-t', '--map-tag', metavar='SRC=DST', multiple=True,
              callback=validation.validate_map,
              help='Tags specified will be translated from SRC to DST. '
              'If DST is omitted, the tag will be removed when SRC matches.')
@click.argument('todoist_api_key')
def configure(map_project, map_tag, todoist_api_key):
    """Configure sync.

    Use --map-project to change or remove the project. Project hierarchies will
    be period-delimited during conversion. For example in the following,
    'Work Errands' and 'House Errands' will be both be changed to 'errands',
    'Programming.Open Source' will be changed to 'oss', and the project will be
    removed when it is 'Taxes':
    \r
    --map-project 'Work Errands'=errands
    --map-project 'House Errands'=errands
    --map-project 'Programming.Open Source'=oss
    --map-project Taxes=
    """
    data = {'todoist': {'api_key': todoist_api_key}, 'taskwarrior': {}}
    data['todoist']['project_map'] = map_project
    data['todoist']['tag_map'] = map_tag
    data['taskwarrior']['project_sync'] = {
        k: True for k in map_project.values()}

    rcfile = os.path.expanduser(TITWSYNCRC)
    with io.open(rcfile, 'w', encoding='utf8') as outfile:
        yaml.dump(data, outfile, default_flow_style=False, allow_unicode=True)


@cli.command()
@click.confirmation_option(
    prompt=f'Are you sure you want to delete {TODOIST_CACHE}?')
def clean():
    """Remove the legacy Todoist task cache (if it exists).

    NOTE - the local Todoist data cache is usually located at:

        ~/.local/share/task/todoist-sync/
    """
    cache_dir = os.path.expanduser(TODOIST_CACHE)

    if not os.path.exists(cache_dir):
        click.echo(f'Cache directory {cache_dir} does not exist, nothing to do.')
        return

    # Delete all files in directory
    for file_entry in os.scandir(cache_dir):
        with log.with_feedback(f'Removing file {file_entry.path}'):
            os.remove(file_entry)

    # Delete directory
    with log.with_feedback(f'Removing directory {cache_dir}'):
        os.rmdir(cache_dir)


@cli.command()
@click.option('--dry-run/--apply', default=True,
              help='Preview changes by default. Use --apply to write to Todoist and Taskwarrior.')
def sync(dry_run):
    """Two-way sync between Todoist and Taskwarrior.

    Uses the Todoist REST API v1. Default is dry-run (no writes).
    Pass --apply to perform actual writes.

    Sync logic:
    - Discovery: new Todoist tasks are imported to Taskwarrior.
    - Bidirectional: timestamp comparison determines which side wins.
    - Completion: completed TW tasks are closed in Todoist, and vice versa.
    - Push: new TW tasks (no todoist_id) are created in Todoist.
    """
    client = TodoistV1Client(config['todoist']['api_key'])

    projects = client.get_all_projects()
    project_lookup = _build_v1_project_lookup(projects)  # {todoist_id: tw_name}
    # Reverse for TW → Todoist writes: {tw_name: todoist_id}
    tw_name_to_project_id = {tw_name: pid for pid, tw_name in project_lookup.items()}

    default_project = utils.try_map(config['todoist'].get('project_map', {}), 'Inbox')
    config_ps = config.get('taskwarrior', {}).get('project_sync', {})

    # Fetch all active Todoist tasks
    ti_tasks = client.get_all_tasks()
    ti_tasks_by_id = {t['id']: t for t in ti_tasks}

    # Load TW tasks
    tw_all = taskwarrior.load_tasks()
    tw_pending = tw_all.get('pending', [])
    tw_completed_list = tw_all.get('completed', [])

    # Index TW tasks by todoist_id
    tw_pending_by_tid: dict = {}
    for tw in tw_pending:
        tid = tw.get('todoist_id')
        if tid:
            tw_pending_by_tid[str(tid)] = tw

    tw_completed_by_tid: dict = {}
    for tw in tw_completed_list:
        tid = tw.get('todoist_id')
        if tid:
            tw_completed_by_tid[str(tid)] = tw

    stats = {
        'imported': 0,
        'synced_to_tw': 0,
        'synced_to_ti': 0,
        'completed_in_ti': 0,
        'completed_in_tw': 0,
        'pushed_new': 0,
        'skipped': 0,
        'errors': 0,
    }

    # Track Todoist IDs created in this run (non-dry-run only).
    # Without this, the "gone from Todoist active" pass would see these new
    # tasks as missing from ti_tasks_by_id (which was fetched before creation)
    # and incorrectly complete them in TW.  In dry-run mode the set stays
    # empty — that's safe because no todoist_id is written to TW tasks, so
    # those tasks are skipped by the `if not tid: continue` guard anyway.
    newly_created_tids: set = set()

    # ------------------------------------------------------------------
    # Completion sync: TW completed → complete in Todoist
    # ------------------------------------------------------------------
    for tw_task in tw_completed_list:
        tid = tw_task.get('todoist_id')
        if not tid:
            continue
        tid = str(tid)
        if tid not in ti_tasks_by_id:
            continue  # already completed in Todoist
        log.important(f"Completing in Todoist: {tw_task.get('description')}")
        if not dry_run:
            try:
                client.complete_task(tid)
                stats['completed_in_ti'] += 1
            except Exception as e:
                log.error(f"Failed to complete task {tid} in Todoist: {e}")
                stats['errors'] += 1
        else:
            stats['completed_in_ti'] += 1

    # ------------------------------------------------------------------
    # Process all active Todoist tasks
    # ------------------------------------------------------------------
    for ti_task in ti_tasks:
        tid = str(ti_task['id'])

        # Determine TW project name for this Todoist task
        tw_project = project_lookup.get(ti_task.get('project_id')) or default_project

        # Project filter (only when config_ps is explicitly configured)
        if config_ps and (tw_project not in config_ps or not config_ps[tw_project]):
            stats['skipped'] += 1
            continue

        if tid in tw_completed_by_tid:
            # Already handled in completion sync pass above
            continue

        if tid not in tw_pending_by_tid:
            # -- Discovery: new Todoist task, import to TW --
            log.important(f"Importing to TW: {ti_task.get('content')}")
            if not dry_run:
                try:
                    c = _convert_v1_ti_task(ti_task, project_lookup, default_project)
                    _tw_add_task(c)
                    stats['imported'] += 1
                except Exception as e:
                    log.error(f"Failed to import task {tid}: {e}")
                    stats['errors'] += 1
            else:
                stats['imported'] += 1
            continue

        # -- Bidirectional sync for tasks in both systems --
        tw_task = tw_pending_by_tid[tid]
        try:
            _sync_task_v1(
                client, tw_task, ti_task,
                project_lookup, tw_name_to_project_id,
                default_project, dry_run, stats,
            )
        except Exception as e:
            log.error(f"Failed to sync task {tid}: {e}")
            stats['errors'] += 1

    # ------------------------------------------------------------------
    # Push new TW tasks (no todoist_id) to Todoist
    # ------------------------------------------------------------------
    for tw_task in tw_pending:
        if tw_task.get('todoist_id'):
            continue

        tw_project = tw_task.get('project') or default_project

        if config_ps and (tw_project not in config_ps or not config_ps[tw_project]):
            stats['skipped'] += 1
            continue

        project_id = tw_name_to_project_id.get(tw_project)
        if not project_id:
            log.warn(
                f"Project '{tw_project}' not found in Todoist, "
                f"skipping '{tw_task.get('description')}'"
            )
            stats['skipped'] += 1
            continue

        log.important(f"Pushing to Todoist: {tw_task.get('description')}")
        if not dry_run:
            try:
                tw_priority = tw_task.get('priority')
                priority = utils.tw_priority_to_ti(tw_priority) if tw_priority else 1
                ti_new = client.create_task(
                    content=tw_task['description'],
                    project_id=project_id,
                    priority=priority,
                )
                new_tid = str(ti_new['id'])
                newly_created_tids.add(new_tid)
                tw_task['todoist_id'] = new_tid
                tw_task['todoist_sync'] = datetime.datetime.now()
                taskwarrior.task_update(tw_task)
                stats['pushed_new'] += 1
            except Exception as e:
                log.error(f"Failed to push task to Todoist: {e}")
                stats['errors'] += 1
        else:
            stats['pushed_new'] += 1

    # ------------------------------------------------------------------
    # Complete TW tasks whose Todoist counterpart is gone (completed/deleted)
    # ------------------------------------------------------------------
    for tw_task in tw_pending:
        tid = tw_task.get('todoist_id')
        if not tid:
            continue
        tid = str(tid)
        if tid in ti_tasks_by_id or tid in newly_created_tids:
            continue
        # Task not in active Todoist — mark done in TW
        log.important(
            f"Completing in TW (gone from Todoist active): "
            f"{tw_task.get('description')}"
        )
        if not dry_run:
            try:
                tw_task['status'] = 'completed'
                tw_task['todoist_sync'] = datetime.datetime.now()
                taskwarrior.task_update(tw_task)
                stats['completed_in_tw'] += 1
            except Exception as e:
                log.error(f"Failed to complete TW task: {e}")
                stats['errors'] += 1
        else:
            stats['completed_in_tw'] += 1

    click.echo(
        f"Summary dry_run={dry_run} "
        f"imported={stats['imported']} "
        f"synced_to_tw={stats['synced_to_tw']} "
        f"synced_to_ti={stats['synced_to_ti']} "
        f"completed_in_ti={stats['completed_in_ti']} "
        f"completed_in_tw={stats['completed_in_tw']} "
        f"pushed_new={stats['pushed_new']} "
        f"skipped={stats['skipped']} "
        f"errors={stats['errors']}"
    )


@cli.command('import-v1')
@click.option('--dry-run/--apply', default=True,
              help='Preview changes by default. Use --apply to write to Taskwarrior.')
@click.option('--include-completed', is_flag=True, default=False,
              help='Also import completed tasks from /api/v1/tasks/completed/get_all.')
def import_v1(dry_run, include_completed):
    """One-way import from Todoist API v1 into Taskwarrior.

    This command never writes to Todoist. It upserts Taskwarrior tasks by
    `todoist_id`, which keeps repeated runs idempotent.
    """
    client = TodoistV1Client(config['todoist']['api_key'])

    projects = client.get_all_projects()
    project_lookup = _build_v1_project_lookup(projects)

    tasks = client.get_all_tasks()
    if include_completed:
        tasks.extend(client.get_all_completed_tasks())

    config_ps = config.get('taskwarrior', {}).get('project_sync', {})
    default_project = utils.try_map(config['todoist'].get('project_map', {}), 'Inbox')

    created = 0
    updated = 0
    skipped = 0
    errors_count = 0

    log.important(f'Importing {len(tasks)} task(s) from Todoist API v1...')
    for ti_task in tasks:
        try:
            c_ti_task = _convert_v1_ti_task(ti_task, project_lookup, default_project)
            desc = c_ti_task['description']
            project = c_ti_task['project']

            if config_ps and (project not in config_ps or not config_ps[project]):
                log.warn(f'Ignoring Task {desc} ({project})')
                skipped += 1
                continue

            _, tw_task = taskwarrior.get_task(todoist_id=c_ti_task['tid'])
            if bool(tw_task):
                if dry_run:
                    updated += 1
                    continue

                if 'project' not in tw_task:
                    tw_task['project'] = default_project
                _tw_update_task(tw_task, c_ti_task)
                updated += 1
                continue

            if dry_run:
                created += 1
                continue

            _tw_add_task(c_ti_task)
            created += 1
        except Exception as e:
            errors_count += 1
            log.error(f"Failed importing task id={ti_task.get('id')}: {e}")

    click.echo(
        f"Summary dry_run={dry_run} projects={len(projects)} tasks={len(tasks)} "
        f"created={created} updated={updated} skipped={skipped} errors={errors_count}"
    )


# ------------------------------------------------------------------
# Internal helpers — shared by sync and import-v1
# ------------------------------------------------------------------

def _build_v1_project_lookup(projects):
    """Build {todoist_project_id: tw_project_name} mapping."""
    by_id = {p['id']: p for p in projects}
    result = {}
    for p in projects:
        chain = [p]
        parent_id = p.get('parent_id')
        while parent_id and parent_id in by_id:
            parent = by_id[parent_id]
            chain.insert(0, parent)
            parent_id = parent.get('parent_id')

        project_name = '.'.join(node['name'] for node in chain)
        project_name = utils.try_map(config['todoist'].get('project_map', {}), project_name)
        result[p['id']] = utils.maybe_quote_ws(project_name)
    return result


def _convert_v1_ti_task(ti_task, project_lookup, default_project):
    data = {}
    data['tid'] = ti_task['id']
    data['description'] = ti_task.get('content', '')
    data['project'] = project_lookup.get(ti_task.get('project_id')) or default_project
    data['priority'] = utils.ti_priority_to_tw(ti_task.get('priority', 1))

    labels = ti_task.get('labels') or []
    data['tags'] = [utils.try_map(config['todoist'].get('tag_map', {}), label)
                    for label in labels]

    data['entry'] = utils.parse_date(ti_task.get('added_at'))
    data['due'] = utils.parse_due(ti_task.get('due'))
    try:
        data['recur'] = utils.parse_recur(ti_task.get('due'))
    except errors.UnsupportedRecurrence:
        data['recur'] = None

    data['status'] = 'completed' if ti_task.get('checked') else 'pending'
    return data


def _to_utc_timestamp(value) -> float:
    """Convert a datetime or string to a UTC POSIX timestamp.

    taskw returns naive datetimes in local time; Todoist returns ISO 8601
    strings with an explicit UTC offset.  Calling .timestamp() on a naive
    datetime assumes local time, which is correct — but only if we first
    make the datetime timezone-aware so that Python's UTC conversion is
    unambiguous.  Calling .astimezone() on a naive datetime attaches the
    local timezone, after which .timestamp() produces a correct UTC value
    regardless of the system timezone.
    """
    if value is None:
        return 0.0
    if isinstance(value, str):
        dt = dateutil.parser.parse(value)
    elif hasattr(value, 'timestamp'):
        dt = value
    else:
        return 0.0
    if dt.tzinfo is None:
        dt = dt.astimezone()  # naive → local-tz-aware → correct UTC stamp
    return dt.timestamp()


def _sync_task_v1(
    client, tw_task, ti_task,
    project_lookup, tw_name_to_project_id,
    default_project, dry_run, stats,
):
    """Bidirectional sync for a task that exists in both TW and Todoist."""
    todoist_sync_stamp = _to_utc_timestamp(tw_task.get('todoist_sync'))
    tw_modified_stamp = _to_utc_timestamp(tw_task.get('modified'))
    ti_updated_stamp = _to_utc_timestamp(ti_task.get('updated_at'))

    tw_changed = tw_modified_stamp > todoist_sync_stamp
    ti_changed = ti_updated_stamp > todoist_sync_stamp

    if tw_changed and (not ti_changed or tw_modified_stamp >= ti_updated_stamp):
        # TW is newer (or both changed and TW wins on wall-clock time)
        desc = tw_task.get('description')
        log.important(f"Pushing TW → Todoist: {desc}")
        if not dry_run:
            _push_tw_to_todoist_v1(client, tw_task, tw_name_to_project_id)
        stats['synced_to_ti'] += 1

    elif ti_changed:
        # Todoist is newer
        c = _convert_v1_ti_task(ti_task, project_lookup, default_project)
        desc = c.get('description')
        log.important(f"Pulling Todoist → TW: {desc}")
        if not dry_run:
            _tw_update_task(tw_task, c)
        stats['synced_to_tw'] += 1

    else:
        # No changes detected; stamp todoist_sync if it was never set
        if not dry_run and 'todoist_sync' not in tw_task:
            tw_task['todoist_sync'] = datetime.datetime.now()
            taskwarrior.task_update(tw_task)


def _push_tw_to_todoist_v1(client, tw_task, tw_name_to_project_id):
    """Push TW task field changes to Todoist."""
    tid = str(tw_task['todoist_id'])

    updates: dict = {'content': tw_task['description']}

    # Priority
    tw_priority = tw_task.get('priority')
    updates['priority'] = utils.tw_priority_to_ti(tw_priority) if tw_priority else 1

    # Project
    tw_project = tw_task.get('project')
    if tw_project and tw_project in tw_name_to_project_id:
        updates['project_id'] = tw_name_to_project_id[tw_project]

    # Labels / tags — reverse-map TW tags back to Todoist label names
    tag_map = config['todoist'].get('tag_map', {})
    rev_tag_map = {v: k for k, v in tag_map.items()}
    tags = tw_task.get('tags') or []
    updates['labels'] = [rev_tag_map.get(t, t) for t in tags if t]

    client.update_task(tid, **updates)

    tw_task['todoist_sync'] = datetime.datetime.now()
    taskwarrior.task_update(tw_task)


def _tw_add_task(ti_task):
    """Add a Taskwarrior task from a converted Todoist task dict.

    `todoist_id` and `todoist_sync` are stamped on the new task so that
    subsequent sync runs match it by `todoist_id` and skip re-importing it.

    Returns the created Taskwarrior task.
    """
    description = ti_task['description']
    project = ti_task['project']
    with log.with_feedback(f"Taskwarrior add '{description}' ({project})"):
        return taskwarrior.task_add(
            ti_task['description'],
            project=ti_task['project'],
            tags=ti_task['tags'],
            priority=ti_task['priority'],
            entry=ti_task['entry'],
            due=ti_task['due'],
            recur=ti_task['recur'],
            status=ti_task['status'],
            todoist_id=ti_task['tid'],       # join key — prevents re-import
            todoist_sync=datetime.datetime.now(),
        )


def _tw_update_task(tw_task, ti_task):
    """Update a Taskwarrior task from a converted Todoist task dict."""

    def _compare_value(item):
        return ((ti_task[item] and item not in tw_task) or
                (item in tw_task and tw_task[item] != ti_task[item]))

    description = ti_task['description']
    project = ti_task['project']
    with log.on_error(f"TW updating '{description}' ({project})"):
        changed = False

        if tw_task['description'] != ti_task['description']:
            tw_task['description'] = ti_task['description']
            changed = True

        if tw_task.get('project') != ti_task['project']:
            tw_task['project'] = ti_task['project']
            changed = True

        if _compare_value('tags'):
            tw_task['tags'] = ti_task['tags']
            changed = True

        if _compare_value('priority'):
            tw_task['priority'] = ti_task['priority']
            changed = True

        if _compare_value('entry'):
            tw_task['entry'] = ti_task['entry']
            changed = True

        if _compare_value('due'):
            tw_task['due'] = ti_task['due']
            changed = True

        if _compare_value('recur'):
            tw_task['recur'] = ti_task['recur']
            changed = True

        # Recurring templates must not be coerced to pending/completed.
        # 'waiting' status is a TW scheduling concern — don't override it.
        tw_status = tw_task.get('status')
        if (tw_status not in ('recurring', 'waiting') and
                tw_status != ti_task['status']):
            tw_task['status'] = ti_task['status']
            changed = True

        if changed:
            tid = ti_task['tid']
            log.info(f'TW updating (todoist_id={tid})...', nl=False)
            log.success('OK')

            tw_task['todoist_sync'] = datetime.datetime.now()
            taskwarrior.task_update(tw_task)


""" Entrypoint """

if __name__ == '__main__':
    cli()
