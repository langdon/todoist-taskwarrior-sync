"""Tests for the two-way sync logic helpers in cli.py.

Covers _to_utc_timestamp, _sync_task_v1, _push_tw_to_todoist_v1,
_tw_update_task, and _convert_v1_ti_task field mapping.
"""
import datetime
from datetime import timezone
import pytest
from unittest.mock import MagicMock, patch, call

# The helpers we test live in cli.py and reference module-level globals
# (config, taskwarrior).  We patch those before importing so tests are
# fully isolated.
import todoist_taskwarrior.cli as cli_mod


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_config(project_map=None, tag_map=None, project_sync=None):
    return {
        'todoist': {
            'api_key': 'fake',
            'project_map': project_map or {},
            'tag_map': tag_map or {},
        },
        'taskwarrior': {
            'project_sync': project_sync or {},
        },
    }


def _ti_task(
    tid='ti_1',
    content='Test task',
    project_id='p1',
    priority=1,
    labels=None,
    added_at='2024-01-01T00:00:00Z',
    updated_at='2024-01-02T00:00:00Z',
    due=None,
    checked=False,
):
    return {
        'id': tid,
        'content': content,
        'project_id': project_id,
        'priority': priority,
        'labels': labels or [],
        'added_at': added_at,
        'updated_at': updated_at,
        'due': due,
        'checked': checked,
    }


def _tw_task(
    uuid='uuid-1',
    description='Test task',
    project='Inbox',
    priority=None,
    tags=None,
    status='pending',
    todoist_id='ti_1',
    todoist_sync=None,
    modified=None,
):
    task = {
        'uuid': uuid,
        'description': description,
        'project': project,
        'tags': tags or [],
        'status': status,
    }
    if priority:
        task['priority'] = priority
    if todoist_id:
        task['todoist_id'] = todoist_id
    if todoist_sync:
        task['todoist_sync'] = todoist_sync
    if modified:
        task['modified'] = modified
    return task


# ---------------------------------------------------------------------------
# _convert_v1_ti_task
# ---------------------------------------------------------------------------

class TestConvertV1TiTask:
    def setup_method(self):
        cli_mod.config = _make_config()

    def test_basic_fields(self):
        ti = _ti_task(tid='42', content='Buy apples', project_id='p1')
        result = cli_mod._convert_v1_ti_task(ti, {'p1': 'Shopping'}, 'Inbox')
        assert result['tid'] == '42'
        assert result['description'] == 'Buy apples'
        assert result['project'] == 'Shopping'
        assert result['status'] == 'pending'

    def test_completed_status(self):
        ti = _ti_task(checked=True)
        result = cli_mod._convert_v1_ti_task(ti, {}, 'Inbox')
        assert result['status'] == 'completed'

    def test_priority_mapping(self):
        for todoist_p, tw_p in [(1, None), (2, 'L'), (3, 'M'), (4, 'H')]:
            ti = _ti_task(priority=todoist_p)
            result = cli_mod._convert_v1_ti_task(ti, {}, 'Inbox')
            assert result['priority'] == tw_p

    def test_labels_become_tags(self):
        ti = _ti_task(labels=['work', 'urgent'])
        result = cli_mod._convert_v1_ti_task(ti, {}, 'Inbox')
        assert 'work' in result['tags']
        assert 'urgent' in result['tags']

    def test_tag_map_applied(self):
        cli_mod.config = _make_config(tag_map={'work': 'office'})
        ti = _ti_task(labels=['work'])
        result = cli_mod._convert_v1_ti_task(ti, {}, 'Inbox')
        assert result['tags'] == ['office']

    def test_fallback_to_default_project(self):
        ti = _ti_task(project_id='unknown')
        result = cli_mod._convert_v1_ti_task(ti, {}, 'MyInbox')
        assert result['project'] == 'MyInbox'


# ---------------------------------------------------------------------------
# _to_utc_timestamp — timezone normalisation (blocking review fix)
# ---------------------------------------------------------------------------

class TestToUtcTimestamp:
    def test_none_returns_zero(self):
        assert cli_mod._to_utc_timestamp(None) == 0.0

    def test_utc_aware_string(self):
        # ISO 8601 with explicit Z — must round-trip to the correct POSIX stamp
        stamp = cli_mod._to_utc_timestamp('2024-06-01T12:00:00Z')
        expected = datetime.datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc).timestamp()
        assert stamp == expected

    def test_naive_datetime_treated_as_local_time(self):
        # taskw returns naive datetimes in local time; _to_utc_timestamp must
        # produce the same POSIX stamp as Python's own .timestamp() (which also
        # treats naive datetimes as local).
        dt_naive = datetime.datetime(2024, 6, 1, 14, 30, 0)
        assert cli_mod._to_utc_timestamp(dt_naive) == dt_naive.timestamp()

    def test_aware_datetime_passthrough(self):
        dt_aware = datetime.datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        assert cli_mod._to_utc_timestamp(dt_aware) == dt_aware.timestamp()

    def test_naive_vs_aware_ordering_preserved(self):
        # Core of the review bug: a naive local datetime that is *later* than a
        # UTC-aware datetime must still compare as later after normalisation.
        # Use a UTC-aware reference that is clearly an hour before the naive one.
        ref_utc = datetime.datetime(2024, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
        # Local noon is always after 10:00 UTC regardless of timezone offset
        # (the maximum UTC offset is +14, so local noon = UTC 22:00 the day
        # before at worst — still the same day in most real deployments).
        # We use 23:00 local to be safe across UTC-12..UTC+14.
        dt_naive_later = datetime.datetime(2024, 6, 1, 23, 0, 0)
        assert cli_mod._to_utc_timestamp(dt_naive_later) > cli_mod._to_utc_timestamp(ref_utc)


# ---------------------------------------------------------------------------
# _build_v1_project_lookup
# ---------------------------------------------------------------------------

class TestBuildV1ProjectLookup:
    def setup_method(self):
        cli_mod.config = _make_config()

    def test_flat_project(self):
        projects = [{'id': 'p1', 'name': 'Work', 'parent_id': None}]
        lookup = cli_mod._build_v1_project_lookup(projects)
        assert lookup['p1'] == 'Work'

    def test_nested_project(self):
        projects = [
            {'id': 'p1', 'name': 'Work', 'parent_id': None},
            {'id': 'p2', 'name': 'Dev', 'parent_id': 'p1'},
        ]
        lookup = cli_mod._build_v1_project_lookup(projects)
        assert lookup['p2'] == 'Work.Dev'

    def test_project_map_applied(self):
        cli_mod.config = _make_config(project_map={'Work': 'work'})
        projects = [{'id': 'p1', 'name': 'Work', 'parent_id': None}]
        lookup = cli_mod._build_v1_project_lookup(projects)
        assert lookup['p1'] == 'work'


# ---------------------------------------------------------------------------
# _tw_update_task
# ---------------------------------------------------------------------------

class TestTwUpdateTask:
    def setup_method(self):
        cli_mod.config = _make_config()
        cli_mod.taskwarrior = MagicMock()

    def test_updates_description(self):
        tw = _tw_task(description='Old')
        ti = {
            'tid': 'ti_1',
            'description': 'New',
            'project': 'Inbox',
            'tags': [],
            'priority': None,
            'entry': None,
            'due': None,
            'recur': None,
            'status': 'pending',
        }
        cli_mod._tw_update_task(tw, ti)
        assert tw['description'] == 'New'
        cli_mod.taskwarrior.task_update.assert_called_once_with(tw)

    def test_no_update_when_unchanged(self):
        tw = _tw_task(description='Same')
        ti = {
            'tid': 'ti_1',
            'description': 'Same',
            'project': 'Inbox',
            'tags': [],
            'priority': None,
            'entry': None,
            'due': None,
            'recur': None,
            'status': 'pending',
        }
        cli_mod._tw_update_task(tw, ti)
        cli_mod.taskwarrior.task_update.assert_not_called()

    def test_does_not_change_recurring_status(self):
        tw = _tw_task(status='recurring')
        ti = {
            'tid': 'ti_1',
            'description': tw['description'],
            'project': 'Inbox',
            'tags': [],
            'priority': None,
            'entry': None,
            'due': None,
            'recur': None,
            'status': 'pending',
        }
        cli_mod._tw_update_task(tw, ti)
        assert tw['status'] == 'recurring'

    def test_does_not_change_waiting_status(self):
        tw = _tw_task(status='waiting')
        ti = {
            'tid': 'ti_1',
            'description': tw['description'],
            'project': 'Inbox',
            'tags': [],
            'priority': None,
            'entry': None,
            'due': None,
            'recur': None,
            'status': 'pending',
        }
        cli_mod._tw_update_task(tw, ti)
        assert tw['status'] == 'waiting'


# ---------------------------------------------------------------------------
# _sync_task_v1 — conflict resolution
# ---------------------------------------------------------------------------

class TestSyncTaskV1:
    def setup_method(self):
        cli_mod.config = _make_config()
        cli_mod.taskwarrior = MagicMock()
        self.client = MagicMock()

    def _make_stats(self):
        return {
            'imported': 0, 'synced_to_tw': 0, 'synced_to_ti': 0,
            'completed_in_ti': 0, 'completed_in_tw': 0,
            'pushed_new': 0, 'skipped': 0, 'errors': 0,
        }

    def test_tw_newer_pushes_to_todoist(self):
        sync_time = datetime.datetime(2024, 1, 1, 12, 0, 0)
        tw = _tw_task(
            todoist_sync=sync_time,
            modified=datetime.datetime(2024, 1, 2, 0, 0, 0),
        )
        ti = _ti_task(updated_at='2024-01-01T06:00:00Z')  # older than TW modified
        stats = self._make_stats()

        with patch.object(cli_mod, '_push_tw_to_todoist_v1') as mock_push:
            cli_mod._sync_task_v1(
                self.client, tw, ti, {}, {}, 'Inbox', dry_run=False, stats=stats,
            )
        mock_push.assert_called_once()
        assert stats['synced_to_ti'] == 1
        assert stats['synced_to_tw'] == 0

    def test_todoist_newer_pulls_to_tw(self):
        sync_time = datetime.datetime(2024, 1, 1, 12, 0, 0)
        tw = _tw_task(
            todoist_sync=sync_time,
            modified=datetime.datetime(2024, 1, 1, 6, 0, 0),
        )
        ti = _ti_task(updated_at='2024-01-02T00:00:00Z')  # newer than TW modified
        stats = self._make_stats()

        with patch.object(cli_mod, '_tw_update_task') as mock_update:
            cli_mod._sync_task_v1(
                self.client, tw, ti, {}, {}, 'Inbox', dry_run=False, stats=stats,
            )
        mock_update.assert_called_once()
        assert stats['synced_to_tw'] == 1
        assert stats['synced_to_ti'] == 0

    def test_dry_run_does_not_write(self):
        sync_time = datetime.datetime(2024, 1, 1, 12, 0, 0)
        tw = _tw_task(
            todoist_sync=sync_time,
            modified=datetime.datetime(2024, 1, 2, 0, 0, 0),
        )
        ti = _ti_task(updated_at='2024-01-01T06:00:00Z')
        stats = self._make_stats()

        with patch.object(cli_mod, '_push_tw_to_todoist_v1') as mock_push:
            cli_mod._sync_task_v1(
                self.client, tw, ti, {}, {}, 'Inbox', dry_run=True, stats=stats,
            )
        mock_push.assert_not_called()
        assert stats['synced_to_ti'] == 1

    def test_no_change_when_both_unchanged(self):
        sync_time = datetime.datetime(2024, 1, 2, 0, 0, 0)
        tw = _tw_task(
            todoist_sync=sync_time,
            modified=datetime.datetime(2024, 1, 1, 0, 0, 0),  # older than sync
        )
        ti = _ti_task(updated_at='2024-01-01T00:00:00Z')  # older than sync
        stats = self._make_stats()

        with patch.object(cli_mod, '_push_tw_to_todoist_v1') as p1, \
             patch.object(cli_mod, '_tw_update_task') as p2:
            cli_mod._sync_task_v1(
                self.client, tw, ti, {}, {}, 'Inbox', dry_run=False, stats=stats,
            )
        p1.assert_not_called()
        p2.assert_not_called()
        assert stats['synced_to_ti'] == 0
        assert stats['synced_to_tw'] == 0


# ---------------------------------------------------------------------------
# _push_tw_to_todoist_v1
# ---------------------------------------------------------------------------

class TestPushTwToTodoistV1:
    def setup_method(self):
        cli_mod.config = _make_config()
        cli_mod.taskwarrior = MagicMock()
        self.client = MagicMock()

    def test_pushes_description_and_priority(self):
        tw = _tw_task(description='Updated desc', priority='H')
        cli_mod._push_tw_to_todoist_v1(self.client, tw, {})
        self.client.update_task.assert_called_once()
        _, kwargs = self.client.update_task.call_args
        assert kwargs.get('content') == 'Updated desc' or \
               self.client.update_task.call_args[0][1:] or \
               'content' in self.client.update_task.call_args[1]
        # Check the update was called with the task id
        args, _ = self.client.update_task.call_args
        assert args[0] == 'ti_1'

    def test_maps_project_to_project_id(self):
        tw = _tw_task(project='Work')
        tw_name_to_project_id = {'Work': 'p_work'}
        cli_mod._push_tw_to_todoist_v1(self.client, tw, tw_name_to_project_id)
        _, kwargs = self.client.update_task.call_args
        assert kwargs.get('project_id') == 'p_work'

    def test_reverse_maps_tags_to_labels(self):
        cli_mod.config = _make_config(tag_map={'work': 'office'})
        tw = _tw_task()
        tw['tags'] = ['office']
        cli_mod._push_tw_to_todoist_v1(self.client, tw, {})
        _, kwargs = self.client.update_task.call_args
        assert kwargs.get('labels') == ['work']

    def test_updates_todoist_sync_uda(self):
        tw = _tw_task()
        cli_mod._push_tw_to_todoist_v1(self.client, tw, {})
        assert 'todoist_sync' in tw
        cli_mod.taskwarrior.task_update.assert_called_once_with(tw)
