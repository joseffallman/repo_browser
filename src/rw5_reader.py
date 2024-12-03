import json
import re


def read_rw5_data(file_content: str):
    # Skapa en dictionary för att lagra de extraherade värdena
    extracted_data = {"Date": None, "Time": None, "CRS": None, "last_point": None}

    # Reguljära uttryck för att plocka ut datum och tid (DT och TM)
    dates = re.findall(r"--DT(\d{2}-\d{2}-\d{4})", file_content)
    times = re.findall(r"--TM(\d{2}:\d{2}:\d{2})", file_content)

    # Hämta första förekomsten av User Defined koordinatsystem
    crs = extract_crs(file_content)

    last_point = extract_last_gps_point(file_content)

    # Lägg till de extraherade värdena i dictionaryn
    if dates:
        extracted_data["Date"] = dates[0]  # Använd första datumet i filen
    if times:
        extracted_data["Time"] = times[0]  # Använd första tiden i filen
    if crs:
        extracted_data["CRS"] = crs

    extracted_data["last_point"] = last_point if last_point else -1

    return extracted_data


def extract_crs(file_content) -> str:
    # Använd reguljära uttryck för att hitta alla GPS-punkter (
    crdsys_match = re.search(r"--(?:User Defined|Projection):\s*(.+)", file_content)
    extracted = ""
    if crdsys_match:
        extracted = crdsys_match.group(1)

    if "sweref 99 tm" in extracted.lower():
        return "EPSG:3006"
    elif "sweref 99 13 30" in extracted.lower():
        return "EPSG:3008"
    elif "sweref 99 15 00" in extracted.lower():
        return "EPSG:3009"

    # Default
    return "EPSG:3006"


def extract_last_gps_point(file_content) -> int | None:
    # Använd reguljära uttryck för att hitta alla GPS-punkter (t.ex. GPS,PN1, GPS,PN2 osv.)
    gps_points = re.findall(r"GPS,PN(\d+)", file_content)

    # Om det finns några punkter, returnera den sista punkten
    if gps_points:
        last_point = gps_points[-1]  # Den sista punkten i listan
        return int(last_point)
    else:
        return None  # Returnera None om inga GPS-punkter hittades


def change_point_code(file_content: str, point_number, new_code):
    # Regular expression för att matcha GPS-rader med punktnummer och ändra punktkoden
    gps_pattern = re.compile(rf"(GPS,PN{point_number}.*?--)([\w\s+-\.\,\:\;]+?)(\n)")
    gs_pattern = re.compile(rf"(--GS,PN{point_number}.*?--)([\w\s+-\.\,\:\;]+?)(\n)")

    # Ändra punktkoden för GPS,PN-raden
    file_content = re.sub(gps_pattern, rf"\1{new_code}\3", file_content)

    # Ändra punktkoden för --GS,PN-raden
    file_content = re.sub(gs_pattern, rf"\1{new_code}\3", file_content)

    # Returnera ändrad fil
    return file_content


def get_point(file_content: str, point_number: int) -> str:
    """Get last point with id"""
    pattern = rf"(GPS,PN{point_number},[^\n]+(?:\n(?:--|G\d)[^\n]+)*\n?)"

    matches = re.findall(pattern, file_content)

    if matches:
        return matches[-1]
    return ""


def get_all_points(file_content: str) -> list[str]:
    """Get all points in file."""
    pattern = r"(GPS,PN[^\n]+(?:\n--[^\n]+)*\n?)"

    matches = re.findall(pattern, file_content)

    if matches:
        return matches
    return []


def get_rw5_header(file_content: str) -> str:
    """Retrun file header."""
    pattern = r"JB,[^\n]+(?:\n(?:--|MO|BP|LS)[^\n]+)*\n?"

    jb = re.search(pattern, file_content)

    if jb:
        return jb.group()
    return ""


def change_jobb_name(file_content: str, new_name: str) -> str:
    """Mönster för att hitta text efter "NM" och innan nästa komma"""
    pattern = r"(NM)([^,]+)"
    nytt_data = re.sub(pattern, rf"\g<1>{new_name}", file_content)
    return nytt_data


def change_point_id(file_content: str, amount: int, old_point_id: int = None):
    """Ändrar ID på alla punkter, eller given punkt, med angiven summa."""
    if old_point_id:
        # Search for only the old id
        search_id = str(old_point_id)
    else:
        # Search for all numbers after PN
        search_id = r"\d+"

    pattern = rf"(,PN)({search_id})(,)"

    def uppdatera_id(match):
        prefix = match.group(1)
        punkt_id = int(match.group(2))
        nytt_id = punkt_id + amount
        suffix = match.group(3)
        return f"{prefix}{nytt_id}{suffix}"

    # Använd re.sub med uppdatera_id för att ersätta alla matchningar
    nytt_data = re.sub(pattern, uppdatera_id, file_content)
    return nytt_data


def rw5_to_json(file_content: str):
    """Get header and points from rw5 as json."""
    json_data = {"header": {}, "points": []}

    json_data["header"] = get_rw5_header(file_content)
    json_data["points"] = get_all_points(file_content)

    return json.dumps(json_data, indent=4)


def json_to_rw5(json_data: dict):
    """Get header and points from json as rw5."""

    data = json.loads(json_data)

    rw5_content = data["header"]
    rw5_content += "\n"
    rw5_content += "\n".join(data["points"])

    return rw5_content
