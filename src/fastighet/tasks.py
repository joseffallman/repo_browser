
import base64
import io

import ezdxf

from .lm import fetch_property_data

from config import api_base_url


def create_dxf(data):
    """ Skapar en DXF-fil från geojson data """
    doc = ezdxf.new()
    msp = doc.modelspace()

    for feature in data:
        if "geometry" in feature and feature["geometry"].get("type") == "Polygon":
            for coords in feature["geometry"]["coordinates"]:
                if isinstance(coords, list) and all(isinstance(point, list) and len(point) == 2 for point in coords):
                    points = [(float(y), float(x)) for x, y in coords]
                    msp.add_lwpolyline(
                        points, close=True)

    dxf_stream = io.StringIO()
    doc.write(dxf_stream)
    dxf_stream.seek(0)
    return dxf_stream.getvalue()

def flip_coordinates(geojson_features):
    def flip_coords(coords):
        # Hantera olika typer av koordinatstrukturer
        return [[ [x, y] for y, x in ring ] for ring in coords]

    flipped_features = []
    for feature in geojson_features:
        geom_type = feature.get('geometry', {}).get('type')
        coords = feature.get('geometry', {}).get('coordinates')

        if geom_type == 'Polygon' and coords:
            feature['geometry']['coordinates'] = flip_coords(coords)
        elif geom_type == 'MultiPolygon' and coords:
            feature['geometry']['coordinates'] = [
                flip_coords(polygon) for polygon in coords
            ]
        # Lägg till fler typer om det behövs

        flipped_features.append(feature)

    return flipped_features


# @celery.task(bind=True, name="fastighet.routes.download_and_create_dxf")
def download_and_create_dxf(self, bbox, repo_name=None, owner=None, path="/", oauth_token=None):
    """Celery task to download data and create DXF"""

    data = fetch_property_data(bbox)
    dxf_str = create_dxf(data)

    geojson_data = {
        "type": "FeatureCollection",
        "features": flip_coordinates(data)
    }

    if repo_name and owner and oauth_token:
        # Commit the DXF to the repo
        from requests_oauthlib import OAuth2Session
        from config import client_id
        gitea = OAuth2Session(client_id, token=oauth_token)

        # Generate filename, e.g., fastighet_20240328.dxf
        from datetime import datetime
        filename = f"fastighet_{datetime.now().strftime('%Y%m%d_%H%M%S')}.dxf"
        file_path = f"{path.rstrip('/')}/{filename}" if path != "/" else filename

        commit_data = {
            "branch": "main",
            "message": f"Added {filename}",
            "files": [{
                "operation": "create",
                "path": file_path,
                "content": base64.b64encode(dxf_str.encode("utf-8")).decode("utf-8")
            }],
        }

        try:
            commit_response = gitea.post(
                f"{api_base_url}/repos/{owner}/{repo_name}/contents", json=commit_data)
            commit_response.raise_for_status()
            return {
                "geojson": geojson_data,
                "status": "committed",
                "dxf": dxf_str.encode('utf-8'),
                "file_path": file_path,
                "repo_url": {"owner": owner, "repo_name": repo_name, "path": path}
            }
        except Exception as e:
            return {
                "geojson": geojson_data,
                "status": "failed",
                "dxf": dxf_str.encode('utf-8'),
                "error": str(e)
            }
    else:
        return {
            "geojson": geojson_data,
            "dxf": dxf_str.encode('utf-8')
        }
