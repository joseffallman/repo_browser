from unittest.mock import patch

import pytest

from src.app import app
from tests.utils import assert_successful_response

# curl -X POST http://localhost:5000/api/download \
#   -H "Authorization: Bearer YOUR_API_KEY|youremail@example.com" \
#   -H "Content-Type: application/json" \
#   -d '{"bbox": "14.7,56.58,14.71,56.581"}'


@pytest.fixture
def client():
    app.config['TESTING'] = True
    return app.test_client()


@patch("fastighet.routes.validate_license_and_email")
@patch("fastighet.routes.celery.send_task")
def test_api_download_success(mock_send_task, mock_validate, client):
    # Setup mockar
    mock_validate.return_value = True
    mock_send_task.return_value.id = "mock-task-id"

    # Setup testdata
    bbox = "12.0,55.0,12.01,55.001"
    headers = {
        "Authorization": "Bearer VALID_API_KEY_12345|test@example.com",
        "Content-Type": "application/json"
    }
    response = client.post(
        "fastighet/api/download", json={"bbox": bbox}, headers=headers)

    assert_successful_response(response, 202)
    data = response.get_json()
    assert "task_id" in data
    assert data["task_id"] == "mock-task-id"

    # Kontrollera att celery-mocken anropades med rätt bbox
    mock_send_task.assert_called_once_with(
        "fastighet.routes.download_and_create_dxf", args=[bbox])
