
import io

import ezdxf

from .lm import fetch_property_data


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
def download_and_create_dxf(self, bbox):
    """Celery task to download data and create DXF"""

    data = fetch_property_data(bbox)
    dxf_str = create_dxf(data)

    geojson_data = {
        "type": "FeatureCollection",
        "features": flip_coordinates(data)
    }

    return {
        "geojson": geojson_data,
        "dxf": dxf_str.encode('utf-8')
    }
