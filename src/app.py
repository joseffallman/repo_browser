import base64
import json
import os
import re
import time
from functools import wraps

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

from __init__ import (
    api_base_url,
    app_url,
    authorization_base_url,
    build_date,
    build_version,
    client_id,
    client_secret,
    token_url,
)
from crd_reader import change_point_id, crd_to_json, get_point_len, json_to_crd
from crs_systems import crs_list
from rw5_reader import change_jobb_name as rw5changeJobbName
from rw5_reader import change_point_id as rw5changeID
from rw5_reader import get_point as rw5get_point
from rw5_reader import get_rw5_header, read_rw5_data
from tasks_routes import tasks_routes

app = Flask(__name__)
app.secret_key = os.getenv("secret_key")


@app.context_processor
def inject_global_variables():
    return {
        "build_date": build_date,
        "build_version": build_version,
    }


# Importera och registrera blueprint
app.register_blueprint(tasks_routes)


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
        authorization_url, state = gitea.authorization_url(
            authorization_base_url)

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
        settingsCRS = ""
        settingsFilePath = ""
        if len(projects):
            settingsCRS = find_settings_file(
                owner, repo_name, os.path.dirname(
                    projects[0]["path"]), "defaultCrs"
            )
            projectsSettingFile = next(
                (
                    item
                    for item in contents
                    if item["type"] == "file" and item["name"].lower() == "settings.ini"
                ),
                None,
            )
            if projectsSettingFile:
                settingsFilePath = projectsSettingFile["path"]

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
                settingsCRS=settingsCRS,
                crs_list=crs_list,
                settingsFilePath=settingsFilePath,
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
                settingsCRS=settingsCRS,
                crs_list=crs_list,
                settingsFilePath=settingsFilePath,
            )
    except HTTPError as http_err:
        flash(
            f"HTTP-fel vid hämtning av repository-innehåll: {http_err}", "danger")
        return redirect(url_for("repos"))
    except Exception as e:
        flash(
            f"Något gick fel vid hämtning av repository-innehåll: {e}", "danger")
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
            url_for("repo_content", owner=owner,
                    repo_name=repo_name, path=path)
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
        url_for("repo_content", owner=owner,
                repo_name=repo_name, path=full_path)
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
            url_for("repo_content", owner=owner,
                    repo_name=repo_name, path=path)
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
                url_for("repo_content", owner=owner,
                        repo_name=repo_name, path=path)
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


def fetch_file_info(owner, repo_name, path):
    """
    Hämtar information om en fil från Gitea API.
    """
    try:
        before_request()
        gitea = OAuth2Session(client_id, token=session["oauth_token"])

        # Hämta den befintliga filinformationen
        response = gitea.get(
            f"{api_base_url}/repos/{owner}/{repo_name}/contents/{path}"
        )
        response.raise_for_status()
        file_data = response.json()
        return file_data
    except HTTPError as http_err:
        raise http_err
    except Exception as e:
        raise e


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


def find_settings_file(owner, repo_name, path, setting, max_levels=3):
    """Letar efter settings.ini filen i denna mapp eller tre våningar upp."""
    try:
        before_request()
        gitea = OAuth2Session(client_id, token=session["oauth_token"])
        current_path = path
        for _ in range(max_levels):
            settings_path = os.path.join(current_path, "settings.ini")
            # Kontrollera om filen existerar
            response = gitea.get(
                f"{api_base_url}/repos/{owner}/{repo_name}/contents/{settings_path}"
            )
            crs = check_crs_in_settings(response, setting)
            if crs is not None:
                return crs.rstrip("\\n")
            # Gå en nivå upp
            current_path = os.path.dirname(current_path)
        return ""

    except HTTPError as http_err:
        raise http_err
    except Exception as e:
        raise e


def check_crs_in_settings(response, setting) -> str | None:
    """Kontrollerar om settings.ini innehåller defaultCrs= och returnerar crs."""

    if response.status_code != 200:
        return None

    # Hämta och avkoda filens innehåll
    file_data = response.json()
    file_content = base64.b64decode(file_data["content"]).decode(
        "utf-8", errors="ignore"
    )
    match = re.search(rf"{setting}=([^\s]+)", file_content)
    return match.group(1) if match else None


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
            rw5_result = read_rw5_data(
                rw5_content.decode("utf-8", errors="ignore"))

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
    newPath = request.form.get("newpath", "")
    owner = request.form.get("owner", "")
    newContent = request.form.get("content", "")
    action = request.form.get("action").lower()
    projCRS = request.form.get("projCRS").lower()

    if not path or not action:
        flash("Felaktiga parametrar, avbryter.", "warning")
        return redirect(
            url_for("repo_content", owner=owner,
                    repo_name=repo_name, path=path)
        )

    gitea = OAuth2Session(client_id, token=session["oauth_token"])
    updated_files = []

    try:
        # Hämta filens nuvarande innehåll och SHA
        response = gitea.get(
            f"{api_base_url}/repos/{owner}/{repo_name}/contents/{path}"
        )
        response.raise_for_status()
        file_data = response.json()
        # current_content = base64.b64decode(file_data["content"]).decode(
        #     "utf-8", errors="ignore"
        # )
        sha = file_data["sha"]
    except Exception as e:
        flash(f"Något gick fel: {str(e)}", "danger")
        return redirect(
            url_for("repo_content", owner=owner,
                    repo_name=repo_name, path=path)
        )

    if action == "update":
        updated_content = _prepare_content(path, newContent)
        updated_files.append(
            {
                "operation": "update",
                "path": path,
                "content": updated_content,
                "sha": sha,
            }
        )

        commitMsg = f"Uppdaterade fil: {path}"
        msg = ("Filen uppdaterades framgångsrikt.", "success")

        # Extrahera mappens sökväg
        directory_path = "/".join(path.split("/")[:-1])

    elif action == "create":
        # Hämta .rw5-filens innehåll.
        fromRw5Path = path.replace(".crd", ".rw5")
        fromRw5Content = fetch_file_content(owner, repo_name, fromRw5Path)
        fromRw5Content = fromRw5Content.decode("utf-8", errors="ignore")

        files = create_file(newPath, newContent, fromRw5Content)

        if len(files) == 0:
            flash("Ingen ändringar gjorda", "warning")
            return redirect(
                url_for("repo_content", owner=owner,
                        repo_name=repo_name, path=path)
            )

        commitMsg = "Copied to new. [skip ci]"
        msg = ("Projektet skapades framgångsrikt.", "success")
        updated_files += files

        # Extrahera mappens sökväg
        directory_path = "/".join(newPath.split("/")[:-1])

    elif action == "append":
        # Hämta .rw5-filens innehåll.
        fromRw5Path = path.replace(".crd", ".rw5")
        fromRw5Content = fetch_file_content(owner, repo_name, fromRw5Path)
        fromRw5Content = fromRw5Content.decode("utf-8", errors="ignore")

        toRw5Path = newPath.replace(".crd", ".rw5")

        try:
            # Hämta rw5 filens nuvarande innehåll och SHA
            response = gitea.get(
                f"{api_base_url}/repos/{owner}/{repo_name}/contents/{newPath}"
            )
            response.raise_for_status()
            toCRDfile = response.json()
            # Hämta  crd filens nuvarande innehåll och SHA
            response = gitea.get(
                f"{api_base_url}/repos/{owner}/{repo_name}/contents/{toRw5Path}"
            )
            response.raise_for_status()
            toRw5file = response.json()
        except Exception as e:
            flash(f"Något gick fel: {str(e)}", "danger")
            return redirect(
                url_for("repo_content", owner=owner,
                        repo_name=repo_name, path=path)
            )

        files = append_file(newContent, fromRw5Content,
                            projCRS, toCRDfile, toRw5file)

        if len(files) == 0:
            flash("Ingen ändringar gjorda", "warning")
            return redirect(
                url_for("repo_content", owner=owner,
                        repo_name=repo_name, path=path)
            )

        updated_files += files
        commitMsg = f"Copied points to project {newPath.split("/")[-1]}. [skip ci]"
        msg = (
            f"{newPath.split("/")[-1]} Projektet uppdaterades framgångsrikt.",
            "success",
        )

        # Extrahera mappens sökväg
        directory_path = "/".join(newPath.split("/")[:-1])

    # Skapa en commit som innehåller alla ändringar
    commit_data = {
        "branch": "main",
        "message": commitMsg,
        "files": updated_files,
    }

    # Skapa commiten via Gitea API
    try:
        commit_response = gitea.post(
            f"{api_base_url}/repos/{owner}/{repo_name}/contents", json=commit_data
        )
        commit_response.raise_for_status()
    except Exception as e:
        flash(f"Något gick fel: {str(e)}", "danger")
        return redirect(
            url_for("repo_content", owner=owner,
                    repo_name=repo_name, path=path)
        )

    # Visa ditt meddelande och återgå till rätt sida
    flash(*msg)
    return redirect(
        url_for(
            "repo_content",
            owner=owner,
            repo_name=repo_name,
            path=directory_path,
        )
    )


def append_file(newContent, fromRw5Content, projCRS: str, toCRDfile, toRw5file) -> list:
    """Lägg till nytt innehåll i slutet av en fil"""

    toRw5Content = base64.b64decode(toRw5file["content"]).decode(
        "utf-8", errors="ignore"
    )

    # Kontrollera CRS.
    current_rw5_info = read_rw5_data(toRw5Content)
    if current_rw5_info["CRS"].lower() != projCRS.lower():
        flash(f"Filen {toCRDfile} har ett annat koordinatsystem.", "warning")
        return []

    # Hämta punkter från rw5-filen.
    newCrdJson = json.loads(newContent)
    rw5Points = ""
    for point in newCrdJson["points"]:
        rw5Points += rw5get_point(fromRw5Content, point["id"])

    # Räkna hur många punkter som redan fanns.
    toCRDContent = crd_to_json(base64.b64decode(toCRDfile["content"]))
    toCRDContent = json.loads(toCRDContent)
    toCRDPointCount = get_point_len(toCRDContent)

    # Ändra punktid på både crd och rw5
    rw5Points = rw5changeID(rw5Points, toCRDPointCount)
    change_point_id(newCrdJson, toCRDPointCount)

    # Lägg på nya rw5 punkter och crd punkter till befintliga filer.
    toRw5Content += rw5Points
    toCRDContent["points"] += newCrdJson["points"]

    # Convertera CRD till sträng
    toCRDStr = json.dumps(toCRDContent)

    return [
        {
            "operation": "update",
            "path": toCRDfile["path"],
            "content": _prepare_content(toCRDfile["path"], toCRDStr),
            "sha": toCRDfile["sha"],
        },
        {
            "operation": "update",
            "path": toRw5file["path"],
            "content": _prepare_content(toRw5file["path"], toRw5Content),
        },
    ]


def create_file(newPath, newContent, fromRw5Content) -> list:
    """Skapa en ny projektfil."""

    # Skapa nytt RW5 innehåll.
    newRw5Path = newPath.replace(".crd", ".rw5")
    newRw5Content = get_rw5_header(fromRw5Content)
    newJobbname = newPath.split("/")[-1].split(".")[0]
    newRw5Content = rw5changeJobbName(newRw5Content, newJobbname)

    # Loopa över punkterna i innehållet från blivande crd filen och lägg till dem i rw5
    newCrdJson = json.loads(newContent)
    for point in newCrdJson["points"]:
        newRw5Content += rw5get_point(fromRw5Content, point["id"])

    return [
        {
            "operation": "create",
            "path": newPath,
            "content": _prepare_content(newPath, newContent),
        },
        {
            "operation": "create",
            "path": newRw5Path,
            "content": _prepare_content(newRw5Path, newRw5Content),
        },
    ]


def _prepare_content(path: str, content: str) -> bytes:
    """Preparera innehållet för att skrivas till repot"""

    # Kontrollera om filen är en .crd-fil och konvertera om nödvändigt
    if path.endswith(".crd"):
        # Konvertera JSON-innehåll tillbaka till CRD-format
        file_content = json_to_crd(content)
        return base64.b64encode(file_content).decode("utf-8")
    else:
        # För vanliga textfiler, behandla innehållet som vanlig text
        return base64.b64encode(content.encode("utf-8")).decode("utf-8")


@app.route("/repo/<owner>/<repo_name>/export_projekt", methods=["POST"])
@login_required
def export_projekt(repo_name, owner):
    """Ändra projektfil som kör export action i git repot."""
    project = request.form.get("project", "")
    defaultCRS = request.form.get("defaultCRS").lower()
    exportCRS = request.form.get("exportCRS").lower()
    settingsFilePath = request.form.get("settingsFilePath")

    if not project or not exportCRS:
        flash("Felaktiga parametrar, avbryter.", "warning")
        return redirect(
            url_for("repo_content", owner=owner, repo_name=repo_name, path="")
        )

    project = json.loads(project)
    path = project["path"]
    projName = project["name"]
    path = path.replace(".crd", ".rw5")
    # Extrahera mappens sökväg
    directory_path = os.path.dirname(path)
    crs_name = next(
        (crs["name"]
         for crs in crs_list if crs["code"].lower() == exportCRS.lower()),
        "",
    )
    commitMsg = f"Export av {projName} i {crs_name}."

    gitea = OAuth2Session(client_id, token=session["oauth_token"])

    settingsFileCommit = []
    if defaultCRS.strip() != exportCRS.strip():
        settingsFileCommit = createSettingsFile(
            gitea, owner, repo_name, settingsFilePath, directory_path, exportCRS
        )

    rw5FileCommit = []
    try:
        # Hämta filens nuvarande innehåll och SHA
        response = gitea.get(
            f"{api_base_url}/repos/{owner}/{repo_name}/contents/{path}"
        )
        response.raise_for_status()
        file_data = response.json()
        current_content = base64.b64decode(file_data["content"]).decode(
            "utf-8", errors="ignore"
        )
        if current_content[-1] == " ":
            current_content = current_content[:-1]
        else:
            current_content += " "
        rw5FileCommit = [
            {
                "operation": "update",
                "path": path,
                "content": _prepare_content(path, current_content),
                "sha": file_data["sha"],
            }
        ]
    except Exception as e:
        flash(f"Något gick fel: {str(e)}", "danger")
        return redirect(
            url_for(
                "repo_content", owner=owner, repo_name=repo_name, path=directory_path
            )
        )

    # Skapa en commit som innehåller alla ändringar
    commit_data = {
        "branch": "main",
        "message": commitMsg,
        "files": settingsFileCommit + rw5FileCommit,
    }

    # Skapa commiten via Gitea API
    try:
        commit_response = gitea.post(
            f"{api_base_url}/repos/{owner}/{repo_name}/contents", json=commit_data
        )
        commit_response.raise_for_status()
    except Exception as e:
        flash(f"Något gick fel: {str(e)}", "danger")
        return redirect(
            url_for(
                "repo_content", owner=owner, repo_name=repo_name, path=directory_path
            )
        )

    # Visa ditt meddelande och återgå till rätt sida

    flash(
        f"En ny export av {projName} med koordinatsystem {crs_name} har startats.",
        "success",
    )
    return redirect(
        url_for(
            "repo_content",
            owner=owner,
            repo_name=repo_name,
            path=directory_path,
        )
    )


def createSettingsFile(
    gitea, owner, repo_name, settingsFilePath, directory_path, exportCRS
):
    """Skapa en settings fil med exportCRS koden. Returnera fil info lista."""

    # Hämta filens nuvarande innehåll och SHA
    if settingsFilePath:
        settingsFile = fetch_file_info(owner, repo_name, settingsFilePath)
        current_content = base64.b64decode(settingsFile["content"]).decode(
            "utf-8", errors="ignore"
        )
        new_content = update_default_crs(current_content, exportCRS)
        return [
            {
                "operation": "update",
                "path": settingsFilePath,
                "content": _prepare_content(settingsFilePath, new_content),
                "sha": settingsFile["sha"],
            }
        ]
    else:
        # Skapa en ny settings fil med defaultCRS
        new_content = rf"[SurveyExport]\ndefaultCrs={exportCRS}\n"
        return [
            {
                "operation": "create",
                "path": os.path.join(directory_path, "settings.ini"),
                "content": _prepare_content(settingsFilePath, new_content),
            }
        ]


def update_default_crs(current_content, new_crs_value):
    # Kolla om 'defaultCrs' finns, om den gör det, uppdatera den, annars skapa den
    if re.search(r"\s*defaultCrs\s*=", current_content, re.IGNORECASE):
        # Om den finns, uppdatera värdet
        current_content = re.sub(
            r"(\s*defaultCrs\s*=\s*)[^\n]*",
            r"\1" + new_crs_value,
            current_content,
            flags=re.IGNORECASE,
        )
    else:
        # Om den inte finns, lägg till den
        current_content += f"\ndefaultCrs={new_crs_value}\n"

    return current_content


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
