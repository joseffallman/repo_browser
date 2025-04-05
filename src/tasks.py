import time

from celery import Celery
from requests_oauthlib import OAuth2Session

from __init__ import api_base_url, celery_broker_url, celery_result_backend, client_id
from fastighet.routes import download_and_create_dxf
from gitea import (
    CRSMISSMATCH,
    _prepare_content,
    append_file,
    create_file,
    fetch_file_content,
)

celery = Celery(
    "tasks",
    broker=celery_broker_url,
    backend=celery_result_backend,
    broker_connection_retry_on_startup=True,
)

celery.task(bind=True, name="fastighet.routes.download_and_create_dxf")(
    download_and_create_dxf
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


@celery.task(bind=True)
def edit_file_task(self, repo_name, path, newPath, owner, newContent, action, projCRS, oauth_token):
    updated_files = []
    gitea = OAuth2Session(client_id, token=oauth_token)

    returnMSG = "Ett fel har uppstått."

    try:
        # Fetch the current file content and SHA
        response = gitea.get(
            f"{api_base_url}/repos/{owner}/{repo_name}/contents/{path}")
        response.raise_for_status()
        file_data = response.json()
        sha = file_data["sha"]
    except Exception as e:
        return {"status": "failed", "message": str(e)}

    if action == "update":
        updated_content = _prepare_content(path, newContent)
        updated_files.append({
            "operation": "update",
            "path": path,
            "content": updated_content,
            "sha": sha,
        })
        commitMsg = f"Updated file: {path}"
        returnMSG = f"Uppdaterade filen: {path}"

    elif action == "create":
        fromRw5Path = path.replace(".crd", ".rw5")
        fromRw5Content = fetch_file_content(
            gitea,
            owner,
            repo_name,
            fromRw5Path
        )
        fromRw5Content = fromRw5Content.decode("utf-8", errors="ignore")
        files = create_file(newPath, newContent, fromRw5Content)
        if len(files) == 0:
            return {"status": "failed", "message": "No changes made"}
        commitMsg = "Copied to new. [skip ci]"
        updated_files += files

        returnMSG = f"Skapade filen: {newPath}"

    elif action == "append":
        fromRw5Path = path.replace(".crd", ".rw5")
        fromRw5Content = fetch_file_content(
            gitea,
            owner,
            repo_name,
            fromRw5Path
        )
        fromRw5Content = fromRw5Content.decode("utf-8", errors="ignore")
        toRw5Path = newPath.replace(".crd", ".rw5")
        try:
            response = gitea.get(
                f"{api_base_url}/repos/{owner}/{repo_name}/contents/{newPath}")
            response.raise_for_status()
            toCRDfile = response.json()
            response = gitea.get(
                f"{api_base_url}/repos/{owner}/{repo_name}/contents/{toRw5Path}")
            response.raise_for_status()
            toRw5file = response.json()
        except Exception as e:
            return {"status": "failed", "message": str(e)}

        try:
            files = append_file(newContent, fromRw5Content,
                                projCRS, toCRDfile, toRw5file)
        except CRSMISSMATCH:
            return {"status": "failed", "message": "CRS missmatch"}

        if len(files) == 0:
            return {"status": "failed", "message": "No changes made"}
        updated_files += files
        commitMsg = f"Copied points to project {newPath.split('/')[-1]}. [skip ci]"

        returnMSG = f"Kopierade punkter till projekt filen: {newPath}"

    commit_data = {
        "branch": "main",
        "message": commitMsg,
        "files": updated_files,
    }

    try:
        commit_response = gitea.post(
            f"{api_base_url}/repos/{owner}/{repo_name}/contents", json=commit_data)
        commit_response.raise_for_status()
    except Exception as e:
        return {"status": "failed", "message": str(e)}

    return {"status": "success", "message": returnMSG}
