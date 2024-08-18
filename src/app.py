import base64
import os

from dotenv import load_dotenv
from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from requests.exceptions import HTTPError
from requests_oauthlib import OAuth2Session

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("secret_key")

# Gitea-konfiguration
client_id = os.getenv("client_id")
client_secret = os.getenv("client_secret")
gitea_url = os.getenv("gitea_url")
app_url = os.getenv("app_url")

if not app_url:
    app_url = "http://localhost:5000/"

if not app_url.endswith("/"):
    app_url = app_url + "/"

if not gitea_url.endswith("/"):
    gitea_url = gitea_url + "/"

authorization_base_url = f"{gitea_url}login/oauth/authorize"
token_url = f"{gitea_url}login/oauth/access_token"
api_base_url = f"{gitea_url}api/v1"


@app.route("/")
def home():
    return render_template("home.html")


@app.route("/login")
def login():
    try:
        gitea = OAuth2Session(
            client_id=client_id,
            redirect_uri=f"{app_url}callback",
            scope="repository",
        )
        authorization_url, state = gitea.authorization_url(authorization_base_url)

        # Spara state i sessionen så vi kan verifiera efter callback
        session["oauth_state"] = state
        return redirect(authorization_url)
    except Exception as e:
        flash(f"Något gick fel vid inloggning: {e}")
        return redirect(url_for("home"))


@app.route("/logout")
def logout():
    session.pop("oauth_token", None)  # Ta bort OAuth-token från sessionen
    flash("Du har loggat ut.")
    return redirect(url_for("home"))


@app.route("/callback")
def callback():
    try:
        gitea = OAuth2Session(client_id, state=session["oauth_state"])
        token = gitea.fetch_token(
            token_url, client_secret=client_secret, authorization_response=request.url
        )

        # Spara token i sessionen
        session["oauth_token"] = token
        return redirect(url_for(".repos"))
    except HTTPError as http_err:
        flash(f"HTTP-fel vid hämtning av token: {http_err}")
        return redirect(url_for("home"))
    except Exception as e:
        flash(f"Något gick fel vid autentisering: {e}")
        return redirect(url_for("home"))


@app.route("/repos")
def repos():
    try:
        gitea = OAuth2Session(client_id, token=session["oauth_token"])
        # Hämta användarens data (inklusive användarnamn)
        user_response = gitea.get(f"{api_base_url}/user")
        user_response.raise_for_status()
        user_data = user_response.json()
        session["username"] = user_data["login"]  # Spara användarnamnet i sessionen

        response = gitea.get(api_base_url + "/user/repos")
        response.raise_for_status()  # Kasta ett fel om statuskoden inte är 200-399
        repos = response.json()
        repo_info = [
            {
                "name": repo["name"],
                "owner": repo["owner"]["login"],
                "full_name": repo["full_name"],
            }
            for repo in repos
        ]

        return render_template("repos.html", repo_infos=repo_info)

    except HTTPError as http_err:
        flash(f"HTTP-fel vid hämtning av repositories: {http_err}")
        return redirect(url_for("home"))
    except Exception as e:
        flash(f"Något gick fel vid hämtning av repositories: {e}")
        return redirect(url_for("home"))


@app.route("/repo/<owner>/<repo_name>/contents/", defaults={"path": ""})
@app.route("/repo/<owner>/<repo_name>/contents/<path:path>")
def repo_content(owner, repo_name, path):
    try:
        gitea = OAuth2Session(client_id, token=session["oauth_token"])

        api_url = f"{api_base_url}/repos/{owner}/{repo_name}/contents/{path}"
        # Dela upp path i delar och bygg upp current_paths
        path_parts = path.split("/")
        current_paths = []
        temp_path = ""
        for part in path_parts:
            temp_path = temp_path + "/" + part if temp_path else part
            current_paths.append((temp_path, part))

        response = gitea.get(api_url)
        response.raise_for_status()
        contents = response.json()
        files = [item for item in contents if item["type"] == "file"]
        dirs = [
            item
            for item in contents
            if item["type"] == "dir" and not item["name"].startswith(".")
        ]
        session["owner"] = owner  # Spara ägarnamnet i sessionen

        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return render_template(
                "tree_content.html",
                owner=owner,
                repo_name=repo_name,
                path=path,
                current_paths=current_paths,
                files=files,
                dirs=dirs,
            )
        else:
            return render_template(
                "repo_content.html",
                owner=owner,
                repo_name=repo_name,
                path=path,
                current_paths=current_paths,
                files=files,
                dirs=dirs,
            )
    except HTTPError as http_err:
        flash(f"HTTP-fel vid hämtning av repository-innehåll: {http_err}")
        return redirect(url_for("repos"))
    except Exception as e:
        flash(f"Något gick fel vid hämtning av repository-innehåll: {e}")
        return redirect(url_for("repos"))


@app.route("/repo/<repo_name>/create_folder", methods=["POST"])
def create_folder(repo_name):
    folder_name = request.form.get("folder_name")
    path = request.form.get("path", "")

    if not folder_name:
        flash("Mappnamn får inte vara tomt.")
        return redirect(
            url_for(
                "repo_content", owner=session["owner"], repo_name=repo_name, path=path
            )
        )

    full_path = f"{path}/{folder_name}".lstrip("/")
    try:
        gitea = OAuth2Session(client_id, token=session["oauth_token"])

        # Skicka en tom fil för att skapa en ny mapp (en tom README.md fil t.ex.)
        data = {
            "message": f"Create folder {full_path}",
            "content": "",  # Innehållet är tomt för att skapa en mapp
            "branch": "main",  # Här specificerar vi huvudgrenen, anpassa efter behov
        }
        response = gitea.put(
            f"{api_base_url}/repos/{session['owner']}/{repo_name}/contents/{full_path}/.gitkeep",
            json=data,
        )
        response.raise_for_status()

        flash("Mappen skapades framgångsrikt.")
    except HTTPError as http_err:
        flash(f"HTTP-fel vid skapande av mapp: {http_err}")
    except Exception as e:
        flash(f"Något gick fel vid skapande av mapp: {e}")

    return redirect(
        url_for("repo_content", owner=session["owner"], repo_name=repo_name, path=path)
    )


@app.route("/repo/<repo_name>/upload_file", methods=["POST"])
def upload_file(repo_name):
    uploaded_file = request.files.get("file")
    path = request.form.get("path", "")

    if not uploaded_file:
        flash("Ingen fil vald.")
        return redirect(
            url_for(
                "repo_content", owner=session["owner"], repo_name=repo_name, path=path
            )
        )

    file_content = uploaded_file.read().decode("utf-8")  # Läser filens innehåll
    file_name = uploaded_file.filename
    full_path = f"{path}/{file_name}".lstrip("/")

    try:
        gitea = OAuth2Session(client_id, token=session["oauth_token"])
        data = {
            "message": f"Add file {full_path}",
            "content": file_content.encode("utf-8").decode("utf-8"),
            "branch": "main",  # Här specificerar vi huvudgrenen, anpassa efter behov
        }
        response = gitea.put(
            f"{api_base_url}/repos/{session['owner']}/{repo_name}/contents/{full_path}",
            json=data,
        )
        response.raise_for_status()

        flash("Filen laddades upp framgångsrikt.")
    except HTTPError as http_err:
        flash(f"HTTP-fel vid uppladdning av fil: {http_err}")
    except Exception as e:
        flash(f"Något gick fel vid uppladdning av fil: {e}")

    return redirect(
        url_for("repo_content", owner=session["owner"], repo_name=repo_name, path=path)
    )


@app.route("/repo/<repo_name>/get_file_content", methods=["GET"])
def get_file_content(repo_name):
    path = request.args.get("path", "")
    if not path:
        return jsonify({"error": "Ingen fil angiven."}), 400

    try:
        gitea = OAuth2Session(client_id, token=session["oauth_token"])
        response = gitea.get(
            f"{api_base_url}/repos/{session['owner']}/{repo_name}/contents/{path}"
        )
        response.raise_for_status()

        file_data = response.json()
        file_content = base64.b64decode(file_data["content"]).decode("utf-8")
        return jsonify({"content": file_content})
    except HTTPError as http_err:
        return jsonify({"error": f"HTTP-fel: {http_err}"}), 500
    except Exception as e:
        return jsonify({"error": f"Fel: {e}"}), 500


@app.route("/repo/<repo_name>/edit_file", methods=["POST"])
def edit_file(repo_name):
    path = request.form.get("path", "")
    content = request.form.get("content", "")

    if not path:
        flash("Ingen fil angiven.")
        return redirect(
            url_for(
                "repo_content", owner=session["owner"], repo_name=repo_name, path=path
            )
        )

    try:
        gitea = OAuth2Session(client_id, token=session["oauth_token"])

        # Hämta den befintliga filinformationen
        response = gitea.get(
            f"{api_base_url}/repos/{session['owner']}/{repo_name}/contents/{path}"
        )
        response.raise_for_status()
        file_data = response.json()

        # Förbered uppdateringen
        update_data = {
            "message": f"Edit file {path}",
            "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
            "sha": file_data["sha"],  # Filens nuvarande SHA krävs för att uppdatera
            "branch": "main",  # Här specificerar vi vilken branch som ska uppdateras
        }

        # Skicka PUT-förfrågan för att uppdatera filen
        update_response = gitea.put(
            f"{api_base_url}/repos/{session['owner']}/{repo_name}/contents/{path}",
            json=update_data,
        )
        update_response.raise_for_status()

        flash("Filen uppdaterades framgångsrikt.", "success")
    except HTTPError as http_err:
        flash(f"HTTP-fel vid uppdatering av fil: {http_err}", "danger")
    except Exception as e:
        flash(f"Något gick fel vid uppdatering av fil: {e}", "danger")

    # Extrahera mappens sökväg
    directory_path = "/".join(path.split("/")[:-1])

    return redirect(
        url_for(
            "repo_content",
            owner=session["owner"],
            repo_name=repo_name,
            path=directory_path,
        )
    )


if __name__ == "__main__":
    app.run(debug=True)
