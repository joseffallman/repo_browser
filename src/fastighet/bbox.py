from typing import Tuple

from pyproj import Transformer

transformer = Transformer.from_crs("EPSG:4326", "EPSG:3006", always_xy=True)


def degrees_to_meters(minx, miny, maxx, maxy) -> Tuple[int, int]:
    """
    Transform a bounding box from EPSG:4326 to EPSG:3006 and calculate its size in meters.

    :param minx: Minimum longitude
    :param miny: Minimum latitude
    :param maxx: Maximum longitude
    :param maxy: Maximum latitude
    :return: Tuple containing (width in meters, height in meters)
    """
    x1, y1 = transformer.transform(minx, miny)
    x2, y2 = transformer.transform(maxx, maxy)

    width_m = abs(x2 - x1)
    height_m = abs(y2 - y1)

    return width_m, height_m
