from pyproj import Transformer

transformer = Transformer.from_crs("EPSG:4326", "EPSG:3006", always_xy=True)


def degrees_to_meters(minx, miny, maxx, maxy) -> tuple(int, int):
    """ Konverterar bbox-koordinater från grader till meter i EPSG:3006 """
    # Transformera koordinaterna till EPSG:3006
    x1, y1 = transformer.transform(minx, miny)
    x2, y2 = transformer.transform(maxx, maxy)

    width_m = abs(x2 - x1)
    height_m = abs(y2 - y1)

    return width_m, height_m
