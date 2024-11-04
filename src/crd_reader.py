import json
import struct


def crd_to_json(file_content):
    json_data = {"header": {}, "points": []}

    # Kontrollera om filen är numerisk eller alfanumerisk baserat på storleken på headern
    header = file_content[:56]  # Testa med numerisk header först
    nor, eas, elv, des = struct.unpack("<ddd32s", header)

    if len(des.strip(b"\x00")) > 0 and False:  # Numerisk fil
        json_data["header"] = {
            "nor": nor,
            "eas": eas,
            "elv": elv,
            "des": des.decode("utf-8", errors="ignore").strip(),
        }
        record_size = 56
        file_type = "numeric"
    else:  # Alfanumerisk fil
        header = file_content[:104]  # Läsa 104 bytes för alfanumerisk header
        id, date, des, format_str = struct.unpack("<d32s32s32s", header)
        json_data["header"] = {
            "id": id,
            "date": date.strip(b"\x00").decode("utf-8", errors="ignore").strip(),
            "des": des.strip(b"\x00").decode("utf-8", errors="ignore").strip(),
            "format": format_str.strip(b"\x00")
            .decode("utf-8", errors="ignore")
            .strip(),
        }
        record_size = 66
        file_type = "alphanumeric"

    # Nu går vi igenom alla poster
    for i in range(len(header), len(file_content), record_size):
        if file_type == "numeric":
            record = file_content[i : i + record_size]
            nor, eas, elv, des = struct.unpack("<ddd32s", record)
            point = {
                "nor": nor,
                "eas": eas,
                "elv": elv,
                "des": des.strip(b"\x00").decode("utf-8", errors="ignore").strip(),
            }
        else:
            record = file_content[i : i + record_size]
            nor, eas, elv, des, id = struct.unpack("<ddd32s10s", record)
            point = {
                "nor": nor,
                "eas": eas,
                "elv": elv,
                "des": des.strip(b"\x00").decode("utf-8", errors="ignore").strip(),
                "id": id.strip(b"\x00").decode("utf-8", errors="ignore").strip(),
            }
        json_data["points"].append(point)

    return json.dumps(json_data, indent=4)


def json_to_crd(json_data):
    crd_content = bytearray()

    data = json.loads(json_data)

    # Hantera headern först
    header = data.get("header", {})

    if "format" in header:  # Alfanumerisk fil
        id = header.get("id", 0.0)
        date = header.get("date", "").encode("utf-8").ljust(32, b"\x00")
        des = header.get("des", "").encode("utf-8").ljust(32, b"\x00")
        format_str = header.get("format", "").encode("utf-8").ljust(32, b"\x00")
        crd_content.extend(struct.pack("<d32s32s32s", id, date, des, format_str))

        # Packa punkterna
        for point in data.get("points", []):
            nor = point.get("nor", 0.0)
            eas = point.get("eas", 0.0)
            elv = point.get("elv", 0.0)
            des = point.get("des", "").encode("utf-8").ljust(32, b"\x00")
            id = point.get("id", "").encode("utf-8").ljust(10, b"\x00")
            crd_content.extend(struct.pack("<ddd32s10s", nor, eas, elv, des, id))

    else:  # Numerisk fil
        nor = header.get("nor", 0.0)
        eas = header.get("eas", 0.0)
        elv = header.get("elv", 0.0)
        des = header.get("des", "").encode("utf-8").ljust(32, b"\x00")
        crd_content.extend(struct.pack("<ddd32s", nor, eas, elv, des))

        # Packa punkterna
        for point in data.get("points", []):
            nor = point.get("nor", 0.0)
            eas = point.get("eas", 0.0)
            elv = point.get("elv", 0.0)
            des = point.get("des", "").encode("utf-8").ljust(32, b"\x00")
            crd_content.extend(struct.pack("<ddd32s", nor, eas, elv, des))

    return bytes(crd_content)


def change_point_id(json_data, amount: int, old_point_id: int = None):
    """Ändrar id på alla punkter, eller given punkt, med angiven summa."""
    if not json_data.get("points"):
        return

    if old_point_id is None:
        for point in json_data["points"]:
            point["id"] = str(int(point["id"]) + amount)
    else:
        for point in json_data["points"]:
            if int(point["id"]) == old_point_id:
                point["id"] = str(int(point["id"]) + amount)


def get_point_len(json_data):
    """Räknar antalet punkter i filen."""
    return len(json_data.get("points", []))
