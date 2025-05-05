import base64
import json

from requests import HTTPError
from requests_oauthlib import OAuth2Session

from config import api_base_url
from crd_reader import change_point_id, crd_to_json, get_point_len, json_to_crd
from rw5_reader import change_jobb_name as rw5changeJobbName
from rw5_reader import change_point_id as rw5changeID
from rw5_reader import get_point as rw5get_point
from rw5_reader import (
    get_rw5_header,
    read_rw5_data,
)


class Gitea(OAuth2Session):
    def __init__(self, client_id, token):
        super().__init__(client_id=client_id, token=token)


def fetch_file_content(gitea: OAuth2Session, owner, repo_name, path):
    """
    Hämtar och avkodar innehållet i en fil från Gitea API.

    :param owner: Ägaren av repot (repository)
    :param repo_name: Namnet på repot
    :param path: Sökvägen till filen i repot
    :return: Avkodat innehåll av filen
    :raises HTTPError: Om det uppstår fel vid API-anropet
    """
    try:

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


class CRSMISSMATCH(Exception):
    """Fel vid överensstämmelse av CRS."""


def append_file(newContent, fromRw5Content, projCRS: str, toCRDfile, toRw5file) -> list:
    """Lägg till nytt innehåll i slutet av en fil"""

    toRw5Content = base64.b64decode(toRw5file["content"]).decode(
        "utf-8", errors="ignore"
    )

    # Kontrollera CRS.
    current_rw5_info = read_rw5_data(toRw5Content)
    if current_rw5_info["CRS"].lower() != projCRS.lower():
        raise CRSMISSMATCH(f"Filen {toCRDfile} har ett annat koordinatsystem.")
        # flash(f"Filen {toCRDfile} har ett annat koordinatsystem.", "warning")
        # return []

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
