import base64
import json
import time
from urllib.parse import urlsplit

import requests

from config import LM_consumer_key, LM_consumer_secret, LM_stac_scope

STAC_API_BASE = "https://api.lantmateriet.se/stac-hojd/v1"
STAC_TOKEN_URL = "https://apimanager.lantmateriet.se/oauth2/token"

# Rate limiting: 240 requests/min = 4 requests/sec = min 0.25 sec mellan requests
MIN_REQUEST_INTERVAL = 0.25  # sekunder
_last_request_time = 0


def _rate_limit_sleep():
    """Säkerställ att vi inte överskrider 240 requests/min till Lantmäteriet."""
    global _last_request_time
    now = time.time()
    time_since_last = now - _last_request_time
    if time_since_last < MIN_REQUEST_INTERVAL:
        time.sleep(MIN_REQUEST_INTERVAL - time_since_last)
    _last_request_time = time.time()


def get_stac_access_token():
    """Hämtar OAuth2 access token för STAC-höjdmodell från Lantmäteriet."""
    if not (LM_consumer_key and LM_consumer_secret):
        raise RuntimeError("LM_consumer_key or LM_consumer_secret is not configured")

    credentials = f"{LM_consumer_key}:{LM_consumer_secret}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()

    headers = {
        "Authorization": f"Basic {encoded_credentials}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    scope = LM_stac_scope or ""
    data = f"grant_type=client_credentials&scope={scope}"

    _rate_limit_sleep()
    resp = requests.post(STAC_TOKEN_URL, headers=headers, data=data, timeout=30)
    resp.raise_for_status()

    token = resp.json().get("access_token")
    if not token:
        raise RuntimeError("Ingen access_token i STAC oauth-respons")

    return token


def fetch_stac_items(bbox, collections=None, max_items=10):
    """Hämtar STAC-items inom bbox och eventuellt specifik collection.

    Args:
        bbox: "minx,miny,maxx,maxy" i EPSG:4326
        collections: lista med collection-namn att filtrera på
        max_items: max antal items att returnera (begränsar antal requests/assets)
    """
    token = get_stac_access_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    body = {
        "bbox": [float(x) for x in bbox.split(",")],
        "limit": 10,
    }

    if collections:
        body["collections"] = collections

    _rate_limit_sleep()
    resp = requests.post(f"{STAC_API_BASE}/search", headers=headers, json=body, timeout=60)

    if resp.status_code == 429:
        retry_after = int(resp.headers.get("Retry-After", 60))
        print(f"Rate limited. Väntar {retry_after}s...")
        time.sleep(retry_after)
        _rate_limit_sleep()
        resp = requests.post(f"{STAC_API_BASE}/search", headers=headers, json=body, timeout=60)

    resp.raise_for_status()

    data = resp.json()
    if not data or "features" not in data:
        return []

    items = data.get("features", [])
    return items[:max_items]


def save_stac_assets_to_zip(items, bbox, asset_keys=None):
    """Hämtar betecknade asset-filer och paketerar i ett ZIP-objekt.

    Args:
        items: STAC-items
        bbox: bounding box sträng
        asset_keys: vilka asset-typer att hämta (t.ex. ["data"] eller ["thumbnail"])
                    None = hämta bara vanliga typer
    """
    from io import BytesIO
    import zipfile

    if asset_keys is None:
        asset_keys = ["data", "thumbnail", "overview"]

    token = get_stac_access_token()
    headers = {
        "Authorization": f"Bearer {token}",
    }

    mem_zip = BytesIO()
    total_assets = 0
    max_assets = 20

    with zipfile.ZipFile(mem_zip, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("metadata.json", f"{{\"bbox\": \"{bbox}\", \"count\": {len(items)} }}")

        for i, item in enumerate(items):
            item_id = item.get("id", f"item_{i}")
            geometry = item.get("geometry")

            if geometry:
                zf.writestr(f"item_{i}_geometry.geojson", json.dumps({"type": "Feature", "id": item_id, "geometry": geometry, "properties": item.get("properties", {})}))

            assets = item.get("assets", {})
            for asset_key, asset_info in assets.items():
                if asset_keys and asset_key not in asset_keys:
                    continue

                if total_assets >= max_assets:
                    zf.writestr("_WARNING.txt", f"Begränsat till {max_assets} assets för att respektera API-limitering")
                    break

                href = asset_info.get("href")
                if not href:
                    continue

                candidate_name = urlsplit(href).path.split("/")[-1]
                if not candidate_name:
                    candidate_name = f"item_{i}_{asset_key}"

                try:
                    _rate_limit_sleep()
                    response = requests.get(href, headers=headers, stream=True, timeout=120)

                    if response.status_code == 429:
                        retry_after = int(response.headers.get("Retry-After", 60))
                        print(f"Rate limited vid asset-download. Väntar {retry_after}s...")
                        time.sleep(retry_after)
                        _rate_limit_sleep()
                        response = requests.get(href, headers=headers, stream=True, timeout=120)

                    response.raise_for_status()
                    file_data = response.content
                    zf.writestr(f"{item_id}_{asset_key}_{candidate_name}", file_data)
                    total_assets += 1
                except Exception as exc:
                    zf.writestr(f"{item_id}_{asset_key}_ERROR.txt", str(exc))

            if total_assets >= max_assets:
                break

    mem_zip.seek(0)
    return mem_zip.getvalue()
