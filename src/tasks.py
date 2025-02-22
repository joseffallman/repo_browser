import time

from celery import Celery

from __init__ import api_base_url, celery_broker_url, celery_result_backend, client_id

celery = Celery(
    "tasks",
    broker=celery_broker_url,
    backend=celery_result_backend
)


@celery.task(bind=True)
def add(self, x, y):
    time.sleep(30)  # Simulera en lång körning
    result = x + y
    print(f"Debug: Adding {x} + {y} = {result}")
    return result


@celery.task
def fetch_repo_contents(self, owner, repo_name, path, token):
    from requests_oauthlib import OAuth2Session

    # Initiera en session med OAuth
    gitea = OAuth2Session(client_id=client_id, token=token)
    api_url = f"{api_base_url}/repos/{owner}/{repo_name}/contents/{path}"

    response = gitea.get(api_url)
    response.raise_for_status()
    contents = response.json()

    # Returnera innehållet
    return contents
