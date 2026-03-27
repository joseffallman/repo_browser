from .stac import fetch_stac_items, save_stac_assets_to_zip


# @celery.task(bind=True, name="hojd.routes.download_and_create_hojd")
def download_and_create_hojd(self, bbox):
    """Celery task to hämta markhöjdmodell via STAC och skapa zip/geojson.

    Rate limiting:
    - Max 240 requests/min till Lantmäteriet (4 req/sec, 0.25s mellan requests)
    - Max 10 items per bbox search
    - Max 20 asset-filer per nedladdning (begränsar total requests)
    - Bara hämtar data/thumbnail/overview assets
    """
    items = fetch_stac_items(bbox, collections=[], max_items=10)

    if not items:
        raise RuntimeError("Ingen markhöjddata hittades för den angivna bboxen")

    geojson = {
        "type": "FeatureCollection",
        "features": [],
    }

    for item in items:
        feature = {
            "type": "Feature",
            "id": item.get("id"),
            "geometry": item.get("geometry"),
            "properties": item.get("properties", {}),
        }
        geojson["features"].append(feature)

    # Hämta bara vanliga asset-typer för att begränsa requests
    zip_bytes = save_stac_assets_to_zip(items, bbox, asset_keys=["data"])

    return {
        "geojson": geojson,
        "zip": zip_bytes,
    }
