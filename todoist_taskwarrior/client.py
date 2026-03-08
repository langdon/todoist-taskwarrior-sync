"""Todoist REST API v1 client."""
import requests

BASE_URL = 'https://api.todoist.com'


class TodoistV1Client:
    """Thin wrapper around the Todoist REST API v1.

    All methods use Bearer-token auth from the supplied API key.
    GET methods follow cursor-based pagination automatically.
    """

    def __init__(self, api_key: str):
        self._headers = {'Authorization': f'Bearer {api_key}'}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_all(self, path: str, extra_params: dict = None) -> list:
        """Paginated GET that follows next_cursor until exhausted."""
        url = f'{BASE_URL}{path}'
        params = {'limit': 200, **(extra_params or {})}
        out = []
        while True:
            response = requests.get(url, headers=self._headers, params=params, timeout=30)
            response.raise_for_status()
            payload = response.json()
            out.extend(payload.get('results', []))
            cursor = payload.get('next_cursor')
            if not cursor:
                break
            params = {'limit': 200, 'cursor': cursor, **(extra_params or {})}
        return out

    def _post(self, path: str, body: dict) -> dict:
        response = requests.post(
            f'{BASE_URL}{path}',
            headers=self._headers,
            json=body,
            timeout=30,
        )
        response.raise_for_status()
        # Some endpoints (close/reopen) return 204 with no body
        if response.status_code == 204 or not response.content:
            return {}
        return response.json()

    def _patch(self, path: str, body: dict) -> dict:
        response = requests.patch(
            f'{BASE_URL}{path}',
            headers=self._headers,
            json=body,
            timeout=30,
        )
        response.raise_for_status()
        if response.status_code == 204 or not response.content:
            return {}
        return response.json()

    # ------------------------------------------------------------------
    # Tasks
    # ------------------------------------------------------------------

    def get_all_tasks(self) -> list:
        """Fetch all active (non-completed) tasks."""
        return self._get_all('/api/v1/tasks')

    def get_all_completed_tasks(self) -> list:
        """Fetch all completed tasks."""
        return self._get_all('/api/v1/tasks/completed/get_all')

    def create_task(
        self,
        content: str,
        project_id: str = None,
        priority: int = None,
        labels: list = None,
        due_string: str = None,
    ) -> dict:
        """Create a new task. Returns the created task dict."""
        body: dict = {'content': content}
        if project_id is not None:
            body['project_id'] = project_id
        if priority is not None:
            body['priority'] = priority
        if labels:
            body['labels'] = labels
        if due_string:
            body['due_string'] = due_string
        return self._post('/api/v1/tasks', body)

    def update_task(self, task_id: str, **fields) -> dict:
        """Partial update of a task. Pass only fields that should change."""
        return self._patch(f'/api/v1/tasks/{task_id}', fields)

    def move_task(self, task_id: str, project_id: str) -> dict:
        """Move a task to a different project."""
        return self.update_task(task_id, project_id=project_id)

    def complete_task(self, task_id: str) -> None:
        """Mark a task as completed (close it)."""
        self._post(f'/api/v1/tasks/{task_id}/close', {})

    def reopen_task(self, task_id: str) -> None:
        """Reopen a completed task."""
        self._post(f'/api/v1/tasks/{task_id}/reopen', {})

    # ------------------------------------------------------------------
    # Projects
    # ------------------------------------------------------------------

    def get_all_projects(self) -> list:
        """Fetch all projects."""
        return self._get_all('/api/v1/projects')

    # ------------------------------------------------------------------
    # Comments
    # ------------------------------------------------------------------

    def add_comment(self, task_id: str, content: str) -> dict:
        """Add a comment to a task."""
        return self._post('/api/v1/comments', {'task_id': task_id, 'content': content})
