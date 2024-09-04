from unittest.mock import Mock, patch

import pytest

from src.app import app


@pytest.fixture
def test_app():
    app.config["TESTING"] = True
    with app.test_client() as test_app:
        yield test_app


@pytest.fixture
def oauth_token(test_app):
    with test_app.session_transaction() as s:
        s["oauth_token"] = 123456789


@pytest.fixture
def oauth2session(test_app, oauth_token):
    with patch("src.app.OAuth2Session", new=Mock()) as mock:
        yield mock
