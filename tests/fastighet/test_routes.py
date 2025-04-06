import io

import ezdxf
import pytest

from src.fastighet.routes import create_dxf


def test_create_dxf():
    # Testdata
    test_data = {
        "type": "FeatureCollection",
        "numberReturned": 10,
        "timeStamp": "2025-04-03T19:48:36Z",
        "features": [
            {
                "type": "Feature",
                "id": "1",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [6435049.763, 335110.696],
                            [6435110.323, 335124.568],
                            [6435122.303, 335095.882],
                            [6435129.817, 335046.751],
                            [6435044.187, 335055.179],
                            [6435049.763, 335110.696]
                        ]
                    ]
                },
                "properties": {
                    "objektidentitet": "8eb74e9c-7b13-b737-9ec2-f665b864b919",
                    "registerenhetsreferens": "909a6a6b-de2d-90ec-e040-ed8f66444c3f",
                    "objekttyp": "fastighetsområde",
                    "senastandrad": "2020-12-17T11:02:00Z",
                    "lanskod": "14",
                    "kommunkod": "1462",
                    "kommunnamn": "LILLA EDET",
                    "trakt": "ATTLERED",
                    "block": "1",
                    "enhet": 7,
                    "omradesnummer": 1,
                    "etikett": "1:7"
                }
            }
        ]
    }

    # Kör funktionen
    dxf_data = create_dxf(test_data.get("features", []))

    # Kontrollera att resultatet är en bytes-ström
    assert isinstance(dxf_data, str)

    # Kontrollera att DXF-filen kan öppnas och läsas av ezdxf
    dxf_stream = io.StringIO(dxf_data)
    doc = ezdxf.read(dxf_stream)

    # Kontrollera att filen innehåller minst en LWPOLYLINE
    msp = doc.modelspace()
    lwpolylines = list(msp.query("LWPOLYLINE"))
    assert len(lwpolylines) > 0

    # Spara DXF-filen för manuell inspektion
    with open("/workspace/tests/output/test_output.dxf", "w") as f:
        f.write(dxf_data)
