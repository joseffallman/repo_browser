import os
import time

from dotenv import load_dotenv

load_dotenv()

# Gitea-konfiguration
client_id = os.getenv("client_id")
client_secret = os.getenv("client_secret")
gitea_url = os.getenv("gitea_url")
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
