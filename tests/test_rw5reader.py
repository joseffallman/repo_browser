import pytest

from src.rw5_reader import (
    change_jobb_name,
    change_point_id,
    get_all_points,
    get_point,
    get_rw5_header,
    json_to_rw5,
    rw5_to_json,
)

# Testdata
data = """
JB,NMNYADAL,DT03-17-2021,TM14:45:50
MO,AD0,UN1,SF1.00000000,EC0,EO0.0,AU0
--SurvCE Version 5.02
--CRD: Alphanumeric
--User Defined: SWEDEN/SWEREF 99 TM
--Equipment:   SatLab,  SL300, SN:BJYA15220199R C2SR0G550, FW:6.600 2015/Jan/28
--Antenna Type: [SL300EXT        NONE],RA0.0890m,SHMP0.0415m,L10.0591m,L20.0596m,--SL300 GNSS External Antenna
--Localization File: None
--Geoid Separation File: \Storage Card\Geoids\SW082000_Syd.gsf N54°37'11.0" E011°11'59.0" N58°15'36.0" E019°04'47.0"
--Grid Adjustment File: None
--GPS Scale: 1.00000000
--Scale Point not used
--RTK Method: RTCM V3.0, Device: Data Collector Internet, Network: NTRIP RTCM3_GNSS
BP,PN2234,LA56.534186799288,LN14.580284398934,EL234.9404,AG0.0000,PA0.0000,ATARP,SRROVER,--
--Entered Rover HR: 2.0000 m, Vertical
LS,HR2.0591
GPS,PN1,LA56.534182082079,LN14.580282246876,EL233.590624,--K ST el_SKP
--GS,PN1,N 6305692.8417,E 498017.1303,EL199.0365,--K ST el_SKP
--GT,PN1,SW2149,ST305982500,EW2149,ET305982500
--HSDV:0.011, VSDV:0.016, STATUS:FIXED, SATS:23, PDOP:1.350, HDOP:0.712, VDOP:1.147, TDOP:1.115, GDOP:1.751, NSDV:0.007, ESDV:0.009
--DT03-17-2021
--TM14:45:53
GPS,PN2,LA56.534180905203,LN14.580283080088,EL233.543759,--L
--GS,PN2,N 6305692.4777,E 498017.2712,EL198.9896,--L
--GT,PN2,SW2149,ST306013000,EW2149,ET306013000
--HSDV:0.011, VSDV:0.015, STATUS:FIXED, SATS:23, PDOP:1.342, HDOP:0.712, VDOP:1.138, TDOP:1.108, GDOP:1.740, NSDV:0.006, ESDV:0.009
--DT03-17-2021
--TM14:46:22
GPS,PN3,LA56.534188995972,LN14.580293123618,EL233.599757,--K
--GS,PN3,N 6305694.9786,E 498018.9719,EL199.0457,--K
--GT,PN3,SW2149,ST306091000,EW2149,ET306091000
--HSDV:0.011, VSDV:0.015, STATUS:FIXED, SATS:23, PDOP:1.332, HDOP:0.712, VDOP:1.126, TDOP:1.098, GDOP:1.726, NSDV:0.006, ESDV:0.009
--DT03-17-2021
--TM14:47:40
GPS,PN4,LA56.534196796345,LN14.580307371472,EL233.410173,--K
--GS,PN4,N 6305697.3894,E 498021.3841,EL198.8562,--K
--GT,PN4,SW2149,ST306101500,EW2149,ET306101500
--HSDV:0.011, VSDV:0.016, STATUS:FIXED, SATS:22, PDOP:1.265, HDOP:0.674, VDOP:1.070, TDOP:1.034, GDOP:1.634, NSDV:0.007, ESDV:0.008
--DT03-17-2021
--TM14:47:51
GPS,PN4,LA56.534196796345,LN14.580307371472,EL233.410173,--K el_SKP
--GS,PN4,N 6305697.3894,E 498021.3841,EL198.8562,--K el_SKP
--GT,PN4,SW2149,ST306101500,EW2149,ET306101500
--HSDV:0.011, VSDV:0.016, STATUS:FIXED, SATS:22, PDOP:1.265, HDOP:0.674, VDOP:1.070, TDOP:1.034, GDOP:1.634, NSDV:0.007, ESDV:0.008
--DT03-17-2021
--TM14:47:55
GPS,PN5,LA56.534208496110,LN14.580317734452,EL233.250896,--K
--GS,PN5,N 6305701.0062,E 498023.1394,EL198.6970,--K
--GT,PN5,SW2149,ST306112000,EW2149,ET306112000
--HSDV:0.011, VSDV:0.017, STATUS:FIXED, SATS:22, PDOP:1.264, HDOP:0.674, VDOP:1.069, TDOP:1.032, GDOP:1.632, NSDV:0.007, ESDV:0.008
--DT03-17-2021
--TM14:48:01
GPS,PN22,LA56.534208496110,LN14.580317734452,EL233.250896,--K
--GS,PN22,N 6305701.0062,E 498023.1394,EL198.6970,--K
--GT,PN22,SW2149,ST306112000,EW2149,ET306112000
--HSDV:0.011, VSDV:0.017, STATUS:FIXED, SATS:22, PDOP:1.264, HDOP:0.674, VDOP:1.069, TDOP:1.032, GDOP:1.632, NSDV:0.007, ESDV:0.008
--DT03-17-2021
--TM14:48:01
GPS,PN23,LA56.534208496110,LN14.580317734452,EL233.250896,--K
--GS,PN23,N 6305701.0062,E 498023.1394,EL198.6970,--K
--GT,PN23,SW2149,ST306112000,EW2149,ET306112000
--HSDV:0.011, VSDV:0.017, STATUS:FIXED, SATS:22, PDOP:1.264, HDOP:0.674, VDOP:1.069, TDOP:1.032, GDOP:1.632, NSDV:0.007, ESDV:0.008
--DT03-17-2021
--TM14:48:01
"""


def test_get_point():
    # Testar om vi kan hämta en specifik punkt (t.ex. PN1)
    point = get_point(data, 4)
    assert point.startswith("GPS,PN4")
    assert point.endswith("--TM14:47:55\n")

    # Testa en annan punkt (t.ex. PN23)
    point = get_point(data, 23)
    assert point.startswith("GPS,PN23")
    assert point.endswith("--TM14:48:01\n")


def test_get_all_points():
    # Kontrollera om alla punkter kan hämtas
    points = get_all_points(data)
    assert len(points) == 8  # Kontrollera att vi har fått flera punkter


def test_get_rw5_header():
    # Testa om vi kan hämta rubriken från data
    header = get_rw5_header(data)
    assert header.startswith("JB,NMNYADAL,DT03-17-2021,TM14:45:50")
    assert header.endswith("LS,HR2.0591\n")


def test_change_jobb_name():
    # Testa om vi kan ändra jobbnamnet
    updated_data = change_jobb_name(get_rw5_header(data), "0003215")
    assert "JB,NM0003215" in updated_data


def test_change_point_id():
    # Testa om vi kan ändra ID på en punkt (t.ex. PN5)
    updated_data = change_point_id(data, 2, 5)
    point = get_point(updated_data, 7)
    assert point.startswith("GPS,PN7")


def test_rw5_to_json_and_back():
    # Testa om vi kan konvertera till JSON och tillbaka till RW5
    json_data = rw5_to_json(data)
    rw5_data = json_to_rw5(json_data)
    assert "JB,NMNYADAL,DT03-17-2021,TM14:45:50" in rw5_data
    assert "GPS,PN1,LA56.534182082079,LN14.580282246876,EL233.590624" in rw5_data
