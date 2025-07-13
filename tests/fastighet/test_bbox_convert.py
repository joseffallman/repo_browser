
from fastighet.bbox import degrees_to_meters


def test_degrees_to_meters():
    bbox_4326 = '14.1007251130,56.4312900880,14.1167298421,56.4403897576'

    coords = list(map(float, bbox_4326.split(',')))
    minx, miny, maxx, maxy = coords

    width, height = degrees_to_meters(minx, miny, maxx, maxy)

    # Tillåt liten tolerans för rundningsfel (±5 meter)
    assert abs(width - 1000) <= 5
    assert abs(height - 1000) <= 5
