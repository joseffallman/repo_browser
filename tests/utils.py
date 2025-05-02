import pytest


def assert_successful_response(response, expected_status=200):
    """
    Kontrollera att response har expected_status.
    Om inte, skriv ut ev. felmeddelande från JSON-svaret.
    """
    data = response.get_json(silent=True)
    if response.status_code != expected_status:
        if isinstance(data, dict) and "error" in data:
            pytest.fail(
                f"Expected status {expected_status}, got {response.status_code}. Error: {data['error']}")
        else:
            pytest.fail(
                f"Expected status {expected_status}, got {response.status_code}. Response: {data}")
    return data
