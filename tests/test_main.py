from unittest.mock import Mock

from flask import get_flashed_messages


def test_home_page(test_app):
    """Test that the home page loads correctly."""
    response = test_app.get("/")
    assert response.status_code == 200
    assert b"Hantera dina projekt med enkelhet." in response.data


def test_protected_routes(test_app):
    """Test that protected routes are inaccessible without authentication."""
    response = test_app.get("/repos")
    messages = get_flashed_messages()
    assert len(messages) == 1
    assert messages[0] == "Något gick fel vid hämtning av repositories: 'oauth_token'"
    assert response.status_code == 302


def test_login(test_app, requests_mock):
    """Test the login process."""
    requests_mock.post(
        "https://gitea_instance_url/api/v1/user", json={"token": "fake_token"}
    )
    response = test_app.get(
        "/login", query_string={"username": "user", "password": "pass"}
    )
    assert response.status_code == 302  # Expect redirect after login
    assert (
        "/login/oauth/authorize?response_type=code&client_id="
        in response.headers["Location"]
    )


# @patch("src.app.OAuth2Session")
def test_repo_contents(oauth2session, test_app):
    """Test that file and folders show up on repo content."""

    # Skapa en mock-respons för .get() metoden
    mock_response = Mock()
    mock_response.json.return_value = [
        {"type": "file", "name": "file.txt"},
        {"type": "file", "name": ".gitignore"},
        {"type": "dir", "name": "foldername"},
        {"type": "dir", "name": ".secrets"},
    ]
    mock_response.raise_for_status = (
        Mock()
    )  # Gör så att raise_for_status inte gör något

    # Ställ in mock-objektet så att det returnerar mock-responsen
    mock_oauth2 = Mock()
    mock_oauth2.get.return_value = mock_response
    oauth2session.return_value = mock_oauth2

    response = test_app.get("/repo/user/repo/contents/file")
    messages = get_flashed_messages()
    assert len(messages) == 0
    assert response.status_code == 200
    assert b'data-filepath="file/file.txt"' in response.data
    assert b'data-filepath="file/.gitignore"' not in response.data
    assert (
        b'href="/repo/user/repo/contents/file/foldername">foldername</a>'
        in response.data
    )
    assert (
        b'href="/repo/user/repo/contents/file/.secrets">.secrets</a>'
        not in response.data
    )
