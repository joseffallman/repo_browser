import base64
import io

import ezdxf
import requests
from flask import Blueprint, current_app, jsonify, render_template, request, send_file

fastighetsindelning_bp = Blueprint(
    'fastighetsindelning',
    __name__,
    url_prefix='/fastighet',
    template_folder='templates'
)

LANTMATERIET_TOKEN_URL = "https://apimanager.lantmateriet.se/oauth2/token"
LANTMATERIET_API_URL = "https://api.lantmateriet.se/ogc-features/v1/fastighetsindelning/collections/registerenhetsomradesytor/items"


def get_access_token():
    """ Hämtar OAuth2 access token från Lantmäteriets API """
    client_id = current_app.config['LM_consumer_key']
    client_secret = current_app.config['LM_consumer_secret']
    credentials = f"{client_id}:{client_secret}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()

    headers = {
        "Authorization": f"Basic {encoded_credentials}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = "grant_type=client_credentials&scope=ogc-features:fastighetsindelning.read"

    response = requests.post(LANTMATERIET_TOKEN_URL,
                             headers=headers, data=data)
    response.raise_for_status()
    return response.json().get('access_token')


def fetch_property_data(bbox):
    """ Hämtar registerenhetsomradesytor från Lantmäteriets API baserat på bbox """
    token = get_access_token()
    headers = {"Authorization": f"Bearer {token}"}
    all_features = []  # För att lagra alla objekt

    offset = 0  # Börja från första sidan
    limit = 100  # Antal objekt per begäran (kan justeras om det behövs)

    while True:
        params = {
            "bbox": bbox,
            "crs": "http://www.opengis.net/def/crs/EPSG/0/3006",
            "offset": offset,
            "limit": limit
        }

        response = requests.get(LANTMATERIET_API_URL,
                                headers=headers, params=params)
        response.raise_for_status()

        data = response.json()
        features = data.get("features", [])

        all_features.extend(features)

        # Om antalet returnerade objekt är mindre än 'limit', har vi hämtat alla objekt
        if len(features) < limit:
            break

        offset += limit

    return all_features
    params = {
        "bbox": bbox,
        "crs": "http://www.opengis.net/def/crs/EPSG/0/3006"
    }
    response = requests.get(LANTMATERIET_API_URL,
                            headers=headers, params=params)
    response.raise_for_status()
    return response.json()


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


@fastighetsindelning_bp.route('/')
def index():
    return render_template('index.html')


@fastighetsindelning_bp.route('/download', methods=['GET'])
def download_dxf():
    bbox = request.args.get("bbox")
    if not bbox:
        return jsonify({"error": "Bounding box (bbox) parameter is required"}), 400

    data = fetch_property_data(bbox)
    dxf_stream = create_dxf(data)

    # Konvertera textströmmen till binärt format
    binary_stream = io.BytesIO(dxf_stream.encode('utf-8'))

    return send_file(binary_stream, as_attachment=True, download_name="fastighetsdata.dxf", mimetype="application/dxf")
