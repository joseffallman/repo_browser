import math


def degrees_to_meters(minx, miny, maxx, maxy):
    """Convert a bounding box defined by its minimum and maximum coordinates"""
    meters_per_deg_lat = 111320
    avg_lat = (miny + maxy) / 2.0
    meters_per_deg_lng = 40075000 * math.cos(math.radians(avg_lat)) / 360

    width_deg = abs(maxx - minx)
    height_deg = abs(maxy - miny)

    return width_deg * meters_per_deg_lng, height_deg * meters_per_deg_lat
