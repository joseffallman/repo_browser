import re


def read_rw5_data(file_content: str):
    # Skapa en dictionary för att lagra de extraherade värdena
    extracted_data = {}

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
        return "EPSG:3007"
    elif "sweref 99 15 00" in extracted.lower():
        return "EPSG:3008"

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
