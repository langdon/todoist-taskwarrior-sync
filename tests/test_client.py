"""Tests for TodoistV1Client.

All HTTP calls are mocked — no real network access required.
"""
import pytest
from unittest.mock import patch, MagicMock
from todoist_taskwarrior.client import TodoistV1Client


API_KEY = 'test_api_key'


def _mock_response(json_data, status_code=200):
    mock = MagicMock()
    mock.status_code = status_code
    mock.content = b'content'
    mock.json.return_value = json_data
    mock.raise_for_status = MagicMock()
    return mock


def _mock_empty_response(status_code=204):
    mock = MagicMock()
    mock.status_code = status_code
    mock.content = b''
    mock.json.return_value = {}
    mock.raise_for_status = MagicMock()
    return mock


class TestGetAllTasks:
    def test_single_page(self):
        payload = {'results': [{'id': '1', 'content': 'Buy milk'}], 'next_cursor': None}
        with patch('requests.get', return_value=_mock_response(payload)) as mock_get:
            client = TodoistV1Client(API_KEY)
            tasks = client.get_all_tasks()

        assert len(tasks) == 1
        assert tasks[0]['content'] == 'Buy milk'
        mock_get.assert_called_once()

    def test_pagination(self):
        page1 = {'results': [{'id': '1'}], 'next_cursor': 'cursor_abc'}
        page2 = {'results': [{'id': '2'}], 'next_cursor': None}
        responses = [_mock_response(page1), _mock_response(page2)]
        with patch('requests.get', side_effect=responses) as mock_get:
            client = TodoistV1Client(API_KEY)
            tasks = client.get_all_tasks()

        assert len(tasks) == 2
        assert mock_get.call_count == 2
        # Second call should include cursor param
        _, kwargs = mock_get.call_args_list[1]
        assert kwargs['params']['cursor'] == 'cursor_abc'

    def test_auth_header(self):
        payload = {'results': [], 'next_cursor': None}
        with patch('requests.get', return_value=_mock_response(payload)) as mock_get:
            TodoistV1Client('my_secret_key').get_all_tasks()
        _, kwargs = mock_get.call_args
        assert kwargs['headers']['Authorization'] == 'Bearer my_secret_key'


class TestGetAllProjects:
    def test_returns_projects(self):
        payload = {
            'results': [{'id': 'p1', 'name': 'Inbox', 'parent_id': None}],
            'next_cursor': None,
        }
        with patch('requests.get', return_value=_mock_response(payload)):
            client = TodoistV1Client(API_KEY)
            projects = client.get_all_projects()
        assert projects[0]['name'] == 'Inbox'


class TestCreateTask:
    def test_posts_required_fields(self):
        created = {'id': '42', 'content': 'Walk dog'}
        with patch('requests.post', return_value=_mock_response(created)) as mock_post:
            client = TodoistV1Client(API_KEY)
            result = client.create_task('Walk dog')

        assert result['id'] == '42'
        _, kwargs = mock_post.call_args
        assert kwargs['json']['content'] == 'Walk dog'

    def test_posts_optional_fields(self):
        created = {'id': '99', 'content': 'Task'}
        with patch('requests.post', return_value=_mock_response(created)) as mock_post:
            client = TodoistV1Client(API_KEY)
            client.create_task(
                'Task',
                project_id='p1',
                priority=3,
                labels=['work'],
                due_string='tomorrow',
            )

        _, kwargs = mock_post.call_args
        body = kwargs['json']
        assert body['project_id'] == 'p1'
        assert body['priority'] == 3
        assert body['labels'] == ['work']
        assert body['due_string'] == 'tomorrow'

    def test_omits_none_optional_fields(self):
        created = {'id': '1', 'content': 'x'}
        with patch('requests.post', return_value=_mock_response(created)) as mock_post:
            client = TodoistV1Client(API_KEY)
            client.create_task('x')
        _, kwargs = mock_post.call_args
        body = kwargs['json']
        assert 'project_id' not in body
        assert 'priority' not in body
        assert 'labels' not in body
        assert 'due_string' not in body


class TestUpdateTask:
    def test_post_request(self):
        updated = {'id': '5', 'content': 'New content'}
        with patch('requests.post', return_value=_mock_response(updated)) as mock_post:
            client = TodoistV1Client(API_KEY)
            result = client.update_task('5', content='New content', priority=2)

        assert result['content'] == 'New content'
        _, kwargs = mock_post.call_args
        assert kwargs['json'] == {'content': 'New content', 'priority': 2}

    def test_url_contains_task_id(self):
        with patch('requests.post', return_value=_mock_response({})) as mock_post:
            TodoistV1Client(API_KEY).update_task('task_99', content='x')
        args, _ = mock_post.call_args
        assert 'task_99' in args[0]


class TestMoveTask:
    def test_delegates_to_update(self):
        with patch.object(TodoistV1Client, 'update_task', return_value={}) as mock_update:
            client = TodoistV1Client(API_KEY)
            client.move_task('t1', 'p2')
        mock_update.assert_called_once_with('t1', project_id='p2')


class TestCompleteTask:
    def test_posts_to_close_endpoint(self):
        with patch('requests.post', return_value=_mock_empty_response()) as mock_post:
            TodoistV1Client(API_KEY).complete_task('t7')
        args, _ = mock_post.call_args
        assert args[0].endswith('/t7/close')

    def test_raises_on_http_error(self):
        mock = _mock_empty_response(status_code=404)
        mock.raise_for_status.side_effect = Exception('404 Not Found')
        with patch('requests.post', return_value=mock):
            with pytest.raises(Exception, match='404'):
                TodoistV1Client(API_KEY).complete_task('bad_id')


class TestReopenTask:
    def test_posts_to_reopen_endpoint(self):
        with patch('requests.post', return_value=_mock_empty_response()) as mock_post:
            TodoistV1Client(API_KEY).reopen_task('t8')
        args, _ = mock_post.call_args
        assert args[0].endswith('/t8/reopen')


class TestAddComment:
    def test_posts_comment(self):
        created = {'id': 'c1', 'content': 'hello'}
        with patch('requests.post', return_value=_mock_response(created)) as mock_post:
            result = TodoistV1Client(API_KEY).add_comment('task_1', 'hello')
        assert result['content'] == 'hello'
        _, kwargs = mock_post.call_args
        assert kwargs['json'] == {'task_id': 'task_1', 'content': 'hello'}
