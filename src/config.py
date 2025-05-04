import os
import time
from functools import wraps

from dotenv import load_dotenv
from flask import flash, redirect, session, url_for

load_dotenv()

LM_consumer_key = os.getenv("LM_consumer_key")
LM_consumer_secret = os.getenv("LM_consumer_secret")
jocoding_validation_url = os.getenv("jocoding_validation_url")

# Gitea-konfiguration
client_id = os.getenv("client_id")
client_secret = os.getenv("client_secret")
gitea_url = os.getenv("gitea_url", "http://localhost:8000/")
app_url = os.getenv("app_url", "http://localhost:5000/")

# Celery-konfiguration
celery_broker_url = os.getenv(
    "CELERY_BROKER_URL",
    "redis://redis:6379/0"
)
celery_result_backend = os.getenv(
    "CELERY_RESULT_BACKEND",
    "redis://redis:6379/0"
)

# Build enviroments
build_date = os.getenv("BUILD_DATE", time.strftime("%Y-%m-%d"))
build_version = os.getenv("BUILD_VERSION", "Develop")

if len(build_version) > 15 and ":" in build_version:
    branch, repo = build_version.split(":")
    build_version = branch + ":" + repo[0:7]

if not app_url.endswith("/"):
    app_url = app_url + "/"

if not gitea_url.endswith("/"):
    gitea_url = gitea_url + "/"

authorization_base_url = f"{gitea_url}login/oauth/authorize"
token_url = f"{gitea_url}login/oauth/access_token"
api_base_url = f"{gitea_url}api/v1"


def login_required(f):
    """Decorator to ensure access token exists before accessing route."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "oauth_token" not in session or "user" not in session:
            flash("Du måste vara inloggad först.", "danger")
            return redirect(url_for("home"))
        return f(*args, **kwargs)

    return decorated_function
