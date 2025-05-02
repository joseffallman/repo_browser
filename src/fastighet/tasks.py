
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


# @celery.task(bind=True, name="fastighet.routes.download_and_create_dxf")
def download_and_create_dxf(self, bbox):
    """Celery task to download data and create DXF"""

    data = fetch_property_data(bbox)
    dxf_str = create_dxf(data)

    geojson_data = {
        "type": "FeatureCollection",
        "features": data
    }

    return {
        "geojson": geojson_data,
        "dxf": dxf_str.encode('utf-8')
    }
