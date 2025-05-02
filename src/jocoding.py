import re

import requests

from config import jocoding_validation_url


def is_valid_email(email: str) -> bool:
    return re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email) is not None


def validate_license_and_email(license_key: str, email: str) -> bool:
    if not is_valid_email(email) or len(license_key) < 10:
        return False
    try:
        response = requests.get(
            jocoding_validation_url,
            params={"api_key": license_key, "email": email},
            timeout=5
        )
        return response.status_code == 200 and response.json().get("success", False)
    except requests.RequestException as e:
        print(f"Validation error: {e}")
        return False
