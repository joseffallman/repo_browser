import base64
import json
import os
import time
from functools import wraps

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

try:
    from src.crd_reader import crd_to_json, json_to_crd
    from src.rw5_reader import read_rw5_data
except ImportError:
    from crd_reader import crd_to_json, json_to_crd
    from rw5_reader import read_rw5_data

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("secret_key")

# Gitea-konfiguration
client_id = os.getenv("client_id")
client_secret = os.getenv("client_secret")
gitea_url = os.getenv("gitea_url")
app_url = os.getenv("app_url")

# Build enviroments
build_date = os.getenv("BUILD_DATE", time.strftime("%Y-%m-%d"))
build_version = os.getenv("BUILD_VERSION", "Develop")

if len(build_version) > 15 and ":" in build_version:
    branch, repo = build_version.split(":")
    build_version = branch + ":" + repo[0:7]

if not app_url:
    app_url = "http://localhost:5000/"

if not app_url.endswith("/"):
    app_url = app_url + "/"

if not gitea_url.endswith("/"):
    gitea_url = gitea_url + "/"

authorization_base_url = f"{gitea_url}login/oauth/authorize"
token_url = f"{gitea_url}login/oauth/access_token"
api_base_url = f"{gitea_url}api/v1"


@app.context_processor
def inject_global_variables():
    return {
        "build_date": build_date,
        "build_version": build_version,
    }


@app.route("/")
def home():
    return render_template("home.html")


def login_required(f):
    """Decorator to ensure access token exists before accessing route."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "oauth_token" not in session or "user" not in session:
            flash("Du måste vara inloggad först.", "danger")
            return redirect(url_for("home"))
        return f(*args, **kwargs)

    return decorated_function


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
        flash(f"Något gick fel vid inloggning: {e}", "danger")
        return redirect(url_for("home"))


@app.route("/logout")
def logout():
    session.pop("oauth_token", None)  # Ta bort OAuth-token från sessionen
    session.pop("user", None)
    flash("Du har loggat ut.", "primary")
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
        # session["oauth_token"]["expires_at"] = time.time() + token.get(
        #     "expires_in", 3600
        # )  # Default to 1 hour if not specified
        user_info = gitea.get(f"{api_base_url}/user")
        user_info.raise_for_status()
        session["user"] = user_info.json()
        return render_template("login_popup.html")
        # return redirect(url_for("repos"))
    except HTTPError as http_err:
        flash(f"HTTP-fel vid hämtning av token: {http_err}", "danger")
        return redirect(url_for("home"))
    except Exception as e:
        flash(f"Något gick fel vid autentisering: {e}", "danger")
        return redirect(url_for("home"))


@app.route("/refresh")
def refresh():
    token = session.get("oauth_token")
    if token:
        oauth = OAuth2Session(client_id, token=token)
        new_token = oauth.refresh_token(
            token_url, client_id=client_id, client_secret=client_secret
        )
        session["oauth_token"] = new_token
        return "Token refreshed!"
    return flash("You need to login first!", "warning")


def is_token_expired():
    token = session.get("oauth_token")
    if not token:
        return True
    expires_at = token.get("expires_at")
    if not expires_at:
        return True
    return time.time() > expires_at


def before_request():
    if "user" in session and is_token_expired():
        refresh()


@app.route("/repos")
def repos():
    try:
        before_request()
        gitea = OAuth2Session(client_id, token=session["oauth_token"])

        response = gitea.get(api_base_url + "/user/repos")
        response.raise_for_status()
        repos = response.json()
        repo_info = [
            {
                "name": repo["name"],
                "owner": repo["owner"]["login"],
                "full_name": repo["full_name"],
            }
            for repo in repos
        ]

        user_info = session.get("user")

        return render_template(
            "repos.html", repo_infos=repo_info, is_admin=user_info.get("is_admin")
        )

    except HTTPError as http_err:
        flash(f"HTTP-fel vid hämtning av repositories: {http_err}", "danger")
        return redirect(url_for("home"))
    except Exception as e:
        flash(f"Något gick fel vid hämtning av repositories: {e}", "danger")
        return redirect(url_for("home"))


@app.route("/admin_dashboard")
@login_required
def admin_dashboard():
    try:
        before_request()
        gitea = OAuth2Session(client_id, token=session["oauth_token"])

        # Get the list of all users
        users = gitea.get(f"{api_base_url}/admin/users").json()

    except HTTPError as http_err:
        flash(f"HTTP-fel vid hämtning av repositories: {http_err}", "danger")
        return redirect(url_for("home"))
    except Exception as e:
        flash(f"Något gick fel vid hämtning av repositories: {e}", "danger")
        return redirect(url_for("home"))

    all_user_data = []

    # Loop through users and get the 5 latest commits for each
    for user in users:
        username = user["login"]
        # 1. Hämta användarens aktivitetsfeed
        activities = gitea.get(
            f"{api_base_url}/users/{username}/activities/feeds?only-performed-by=true&page=1&limit=5"
        ).json()

        user_commits = []

        for activity in activities:
            if activity["op_type"] == "commit_repo":
                activity_content = json.loads(activity["content"])
                commit = activity_content["Commits"][0]
                commit_data = {
                    "repo": activity["repo"]["name"],
                    "owner": activity["repo"]["owner"]["login"],
                    "html_url": activity["repo"]["html_url"],
                    "commit_url": f"{activity['repo']['html_url']}/commit/{commit['Sha1']}",
                    "commit_message": commit["Message"],
                    "commit_date": commit["Timestamp"],
                }
                user_commits.append(commit_data)
                user_name = f"{commit["AuthorName"]} ({username})"
                user_url = f"{activity['act_user']['html_url']}"
                user_lastlogin = f"{activity['act_user']['last_login']}"

        # Sortera och begränsa till de senaste 5 commits eller push-aktiviteter
        user_commits = sorted(
            user_commits, key=lambda x: x["commit_date"], reverse=True
        )[:5]

        user_filtered_data = {
            "user_name": user_name,
            "user_url": user_url,
            "user_lastlogin": user_lastlogin,
            "commits": user_commits,
        }

        # Lägg till användarens commits i huvudlistan
        all_user_data.append(user_filtered_data)

    # Render the commits on the dashboard
    return render_template(
        "admin_dashboard.html",
        all_user_data=all_user_data,
    )


@app.route("/repo/<owner>/<repo_name>/contents/", defaults={"path": ""})
@app.route("/repo/<owner>/<repo_name>/contents/<path:path>")
@login_required
def repo_content(owner, repo_name, path):
    try:
        before_request()
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
        files = [
            item
            for item in contents
            if item["type"] == "file" and not item["name"].startswith(".")
        ]
        dirs = [
            item
            for item in contents
            if item["type"] == "dir" and not item["name"].startswith(".")
        ]
        projects = [item for item in contents if item["name"].endswith(".crd")]
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
                projects=projects,
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
                projects=projects,
            )
    except HTTPError as http_err:
        flash(f"HTTP-fel vid hämtning av repository-innehåll: {http_err}", "danger")
        return redirect(url_for("repos"))
    except Exception as e:
        flash(f"Något gick fel vid hämtning av repository-innehåll: {e}", "danger")
        return redirect(url_for("repos"))


@app.route("/repo/<repo_name>/create_folder", methods=["POST"])
@login_required
def create_folder(repo_name):
    folder_name = request.form.get("folder_name")
    path = request.form.get("path", "")
    owner = request.form.get("owner", "")

    if not folder_name:
        flash("Mappnamn får inte vara tomt.", "warning")
        return redirect(
            url_for("repo_content", owner=owner, repo_name=repo_name, path=path)
        )

    full_path = f"{path}/{folder_name}".lstrip("/")
    try:
        before_request()
        gitea = OAuth2Session(client_id, token=session["oauth_token"])

        # Skicka en tom fil för att skapa en ny mapp (en tom README.md fil t.ex.)
        data = {
            "message": f"Create folder {full_path}",
            "content": "",
            "branch": "main",  # Här specificerar vi huvudgrenen, anpassa efter behov
        }
        response = gitea.post(
            f"{api_base_url}/repos/{owner}/{repo_name}/contents/{full_path}/.gitkeep",
            json=data,
        )
        response.raise_for_status()

        if response.status_code == 201:
            flash("Mappen skapades framgångsrikt.", "success")
    except HTTPError as http_err:
        flash(f"HTTP-fel vid skapande av mapp: {http_err}", "danger")
        print(response.json())
    except Exception as e:
        flash(f"Något gick fel vid skapande av mapp: {e}", "danger")

    return redirect(
        url_for("repo_content", owner=owner, repo_name=repo_name, path=full_path)
    )


@app.route("/repo/<repo_name>/upload_file", methods=["POST"])
@login_required
def upload_file(repo_name):
    uploaded_file = request.files.get("file")
    path = request.form.get("path", "")
    owner = request.form.get("owner", "")
    branch = request.form.get("branch", "main")  # Standardgren är 'main'

    if not uploaded_file:
        flash("Ingen fil vald.", "warning")
        return redirect(
            url_for("repo_content", owner=owner, repo_name=repo_name, path=path)
        )

    file_content = uploaded_file.read()  # Läser filens innehåll
    file_name = uploaded_file.filename
    full_path = f"{path}/{file_name}".lstrip("/")

    try:
        before_request()
        gitea = OAuth2Session(client_id, token=session["oauth_token"])

        # Kontrollera om filen redan finns
        get_response = gitea.get(
            f"{api_base_url}/repos/{owner}/{repo_name}/contents/{full_path}",
            params={"ref": branch},
        )

        if get_response.status_code == 200:
            flash(
                "En fil med detta namn finns redan på den angivna platsen.", "warning"
            )
            return redirect(
                url_for("repo_content", owner=owner, repo_name=repo_name, path=path)
            )

        encoded_content = base64.b64encode(file_content).decode("utf-8")

        data = {
            "message": f"Add file {full_path}",
            "content": encoded_content,
            "branch": branch,
        }

        response = gitea.post(
            f"{api_base_url}/repos/{owner}/{repo_name}/contents/{full_path}",
            json=data,
        )
        response.raise_for_status()

        if response.status_code == 201:
            flash("Filen skapades framgångsrikt.", "success")
        else:
            flash("Något gick fel vid uppladdning av filen.", "danger")
    except HTTPError as http_err:
        error_detail = response.json().get("message", str(http_err))
        flash(f"HTTP-fel vid uppladdning av fil: {error_detail}", "danger")
    except Exception as e:
        flash(f"Något gick fel vid uppladdning av fil: {e}", "danger")

    return redirect(
        url_for("repo_content", owner=owner, repo_name=repo_name, path=path)
    )


def fetch_file_content(owner, repo_name, path):
    """
    Hämtar och avkodar innehållet i en fil från Gitea API.

    :param owner: Ägaren av repot (repository)
    :param repo_name: Namnet på repot
    :param path: Sökvägen till filen i repot
    :return: Avkodat innehåll av filen
    :raises HTTPError: Om det uppstår fel vid API-anropet
    """
    try:
        # Förbered förfrågan med OAuth2-sessionen
        before_request()  # Om det behövs för att uppdatera tokens
        gitea = OAuth2Session(client_id, token=session["oauth_token"])

        # Gör GET-förfrågan till Gitea API för att hämta filen
        response = gitea.get(
            f"{api_base_url}/repos/{owner}/{repo_name}/contents/{path}"
        )
        response.raise_for_status()  # Om svaret indikerar ett HTTP-fel kastas ett undantag

        # Hämta och avkoda filens innehåll
        file_data = response.json()
        file_content = base64.b64decode(file_data["content"])
        return file_content

    except HTTPError as http_err:
        # Om det uppstår ett HTTP-fel, kan vi logga eller hantera det
        # Returnera en tom sträng även om filen inte finns.
        return b""
        raise http_err
    except Exception as e:
        # Andra potentiella fel, t.ex. avkodningsfel
        raise e


@app.route("/repo/<owner>/<repo_name>/get_file_content", methods=["GET"])
@login_required
def get_file_content(repo_name, owner):
    path = request.args.get("path", "")
    editProject = request.args.get("editProject", "")
    editProject = True if editProject.lower() == "true" else False
    if not path:
        return jsonify({"error": "Ingen fil angiven."}), 400

    try:
        # Hämta innehållet för den begärda filen
        file_content = fetch_file_content(owner, repo_name, path)

        # Kontrollera om filen är en CRD-fil
        if editProject or path.endswith(".crd"):
            # Konvertera CRD-filens innehåll till JSON
            file_content_json = crd_to_json(file_content)

            # Hämta .rw5-filens innehåll
            rw5_path = path.replace(".crd", ".rw5")
            rw5_content = fetch_file_content(owner, repo_name, rw5_path)

            # Bearbeta innehållet i .rw5-filen
            rw5_result = read_rw5_data(rw5_content.decode("utf-8", errors="ignore"))

            # Returnera båda resultaten
            return jsonify({"content": file_content_json, "info": rw5_result})
        else:
            # För icke-CRD-filer, returnera innehållet som text
            file_content = file_content.decode("utf-8", errors="ignore")
            return jsonify({"content": file_content})
    except HTTPError as http_err:
        return jsonify({"error": f"HTTP-fel: {http_err}"}), 500
    except Exception as e:
        return jsonify({"error": f"Fel: {e}"}), 500


@app.route("/repo/<repo_name>/edit_file", methods=["POST"])
@login_required
def edit_file(repo_name):
    path = request.form.get("path", "")
    owner = request.form.get("owner", "")
    content = request.form.get("content", "")

    if not path:
        flash("Ingen fil angiven.", "warning")
        return redirect(
            url_for("repo_content", owner=owner, repo_name=repo_name, path=path)
        )

    try:
        before_request()
        gitea = OAuth2Session(client_id, token=session["oauth_token"])

        # Hämta den befintliga filinformationen
        response = gitea.get(
            f"{api_base_url}/repos/{owner}/{repo_name}/contents/{path}"
        )
        response.raise_for_status()
        file_data = response.json()

        # Kontrollera om filen är en .crd-fil och konvertera om nödvändigt
        if path.endswith(".crd"):
            # Konvertera JSON-innehåll tillbaka till CRD-format
            file_content = json_to_crd(content)
            encoded_content = base64.b64encode(file_content).decode("utf-8")
        else:
            # För vanliga textfiler, behandla innehållet som vanlig text
            encoded_content = base64.b64encode(content.encode("utf-8")).decode("utf-8")

        # Förbered uppdateringen
        update_data = {
            "message": f"Edit file {path}",
            "content": encoded_content,
            "sha": file_data["sha"],  # Filens nuvarande SHA krävs för att uppdatera
            "branch": "main",  # Här specificerar vi vilken branch som ska uppdateras
        }

        # Skicka PUT-förfrågan för att uppdatera filen
        update_response = gitea.put(
            f"{api_base_url}/repos/{owner}/{repo_name}/contents/{path}",
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
            owner=owner,
            repo_name=repo_name,
            path=directory_path,
        )
    )


@app.route("/repo/<owner>/<repo_name>/search", methods=["GET"])
@login_required
def search_repo(owner, repo_name):
    search_term = request.args.get("q", "").lower()
    sha = request.args.get("sha", "HEAD")

    try:
        before_request()
        gitea = OAuth2Session(client_id, token=session["oauth_token"])

        filtered_items = search(gitea, owner, repo_name, sha, search_term)

        for item in filtered_items:
            if item["type"] == "blob":
                if (i := item["path"].rfind("/")) != -1:
                    path = item["path"][0:i]
                else:
                    path = ""
            elif item["type"] == "tree":
                path = item["path"]

            item["href"] = url_for(
                "repo_content",
                owner=owner,
                repo_name=repo_name,
                path=path,
            )

        return jsonify(filtered_items)
    except Exception as e:
        return jsonify({"error": f"Fel: {e}"}), 500


def search(
    gitea: OAuth2Session,
    owner: str,
    repo: str,
    sha: str,
    search_term: str,
    page: int = 0,
) -> list:
    # Hämta den befintliga filinformationen
    response = gitea.get(
        f"{api_base_url}/repos/{owner}/{repo}/git/trees/{sha}?recursive=1&page={page}"
    )
    response.raise_for_status()
    tree_data = response.json()
    result = []

    # Loopa igenom hela fil-trädet
    if not tree_data["tree"]:
        return result

    for item in tree_data["tree"]:
        if item["path"].startswith("."):
            continue

        if "/" in item["path"]:
            filedirname = item["path"].split("/")[-1]
        else:
            filedirname = item["path"]

        if search_term in filedirname.lower():
            result.append(item)

    if tree_data["truncated"]:
        result += search(gitea, owner, repo, sha, search_term, page + 1)

    return result


if __name__ == "__main__":
    app.run(debug=True)
