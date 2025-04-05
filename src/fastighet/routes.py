import base64
import io
import os
import tempfile
from datetime import datetime, timedelta

import ezdxf
import requests
from flask import Blueprint, jsonify, render_template, request, send_file, url_for

# from tasks import celery
from config import (
    LM_consumer_key,
    LM_consumer_secret,
)

fastighetsindelning_bp = Blueprint(
    'fastighet',
    __name__,
    url_prefix='/fastighet',
    template_folder='templates'
)

LANTMATERIET_TOKEN_URL = "https://apimanager.lantmateriet.se/oauth2/token"
LANTMATERIET_API_URL = "https://api.lantmateriet.se/ogc-features/v1/fastighetsindelning/collections/registerenhetsomradesytor/items"

# En global dictionary för att hålla koll på temporära filer och deras utgångstid
TEMP_FILES = {}


def get_access_token():
    """ Hämtar OAuth2 access token från Lantmäteriets API """
    client_id = LM_consumer_key
    client_secret = LM_consumer_secret
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
    return dxf_str.encode('utf-8')


@fastighetsindelning_bp.route('/')
def index():
    return render_template('index.html')


@fastighetsindelning_bp.route('/download', methods=['POST'])
def download_dxf():
    bbox = request.json.get("bbox")
    if not bbox:
        return jsonify({"error": "Bounding box (bbox) parameter is required"}), 400

    # Rensa upp gamla temporära filer
    try:
        cleanup_temp_files()
    except Exception as e:
        print("Unable to clean temp files" + e)

    # Starta Celery-task
    from tasks import celery
    task = celery.send_task(
        "fastighet.routes.download_and_create_dxf", args=[bbox])
    return jsonify({"task_id": task.id}), 202


def cleanup_temp_files():
    """Rensar temporära filer som har gått ut"""
    now = datetime.now()
    expired_files = [task_id for task_id,
                     info in TEMP_FILES.items() if info["expires_at"] < now]

    for task_id in expired_files:
        file_path = TEMP_FILES[task_id]["file_path"]
        if os.path.exists(file_path):
            os.remove(file_path)
        del TEMP_FILES[task_id]


@fastighetsindelning_bp.route('/task_status/<task_id>', methods=['GET'])
def task_status(task_id):
    """Kontrollerar status för en Celery-task och hanterar temporära filer"""
    from tasks import celery
    task = celery.AsyncResult(task_id)

    if task.state == 'PENDING':
        response = {"state": task.state, "status": "Task is pending..."}
    elif task.state == 'SUCCESS':
        # Skapa en temporär fil för DXF-innehållet
        if task_id not in TEMP_FILES:
            # Skapa en temporär fil med mkstemp
            fd, temp_file_path = tempfile.mkstemp(
                prefix="fastighet_",
                suffix=".dxf",
                dir="/tmp"
            )
            with os.fdopen(fd, 'wb') as temp_file:
                temp_file.write(task.result)

            # Lägg till filen i TEMP_FILES med en utgångstid på 24 timmar
            TEMP_FILES[task_id] = {
                "file_path": temp_file_path,
                "expires_at": datetime.now() + timedelta(hours=24)
            }

        # Returnera filens URL
        file_url = url_for("fastighet.download_file", task_id=task_id)
        response = {"state": task.state,
                    "status": "Task completed!", "file_url": file_url}
    elif task.state == 'FAILURE':
        response = {"state": task.state, "status": str(task.info)}
    else:
        response = {"state": task.state, "status": "Task is in progress..."}

    return jsonify(response)


@fastighetsindelning_bp.route('/download_file/<task_id>', methods=['GET'])
def download_file(task_id):
    """Returnerar filen för nedladdning baserat på task_id"""
    if task_id not in TEMP_FILES:
        return jsonify({"error": "File not found or expired"}), 404

    file_path = TEMP_FILES[task_id]["file_path"]
    if not os.path.exists(file_path):
        return jsonify({"error": "File not found"}), 404

    # Returnera filen som en nedladdning
    return send_file(file_path, as_attachment=True)
