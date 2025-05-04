import json
import os
import tempfile
from datetime import datetime, timedelta

from flask import (
    Blueprint,
    current_app,
    jsonify,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from ..config import (
    login_required,
)
from ..db import db
from ..jocoding import validate_license_and_email
from ..tasks import celery
from .bbox import degrees_to_meters
from .models import TaskTracker

fastighetsindelning_bp = Blueprint(
    'fastighet',
    __name__,
    url_prefix='/fastighet',
    template_folder='templates'
)

# En global dictionary för att hålla koll på temporära filer och deras utgångstid
TEMP_FILES = {}

MAX_METERS = 1000


# Funktion för att hämta användarens ID från Flask-sessionen
def get_user_key():
    # Fallback till IP om "user" saknas
    return session.get("user", {}).get("id", get_remote_address())


# Skapa en Limiter-instans
limiter = Limiter(
    key_func=get_user_key,
)


@fastighetsindelning_bp.route('/')
@login_required
def index():
    trackers = TaskTracker.query.filter(
        TaskTracker.user_id == session["user"]['email'],
        TaskTracker.rate_limit_reset >= datetime.now()
    ).order_by(TaskTracker.created_at.desc()).all()

    tracker = trackers[0] if trackers else None
    if tracker:
        rate_info = {
            "remaining": tracker.rate_limit_remaining,
            "limit": tracker.rate_limit_total,
            "reset": int(tracker.rate_limit_reset.timestamp()),
            "task_id": tracker.task_id
        }
    else:
        rate_info = None

    return render_template('fastighet.html', rate_info=rate_info)


@fastighetsindelning_bp.route('/download', methods=['POST'])
@limiter.limit("5 per hour")
@login_required
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
    task = celery.send_task(
        "fastighet.routes.download_and_create_dxf", args=[bbox])

    # Hämta rate-limit-information från Flask-Limiter
    limit = limiter.current_limit
    remaining = limit.remaining
    reset_at = limit.reset_at

    # Spara task info i DB
    tracker = TaskTracker(
        # Du använder session['user']['email']
        user_id=session["user"]['email'],
        task_id=task.id,
        rate_limit_remaining=remaining,
        rate_limit_total=limit.limit.amount,
        rate_limit_reset=datetime.fromtimestamp(reset_at),
        bbox=bbox,
    )
    db.session.add(tracker)
    db.session.commit()

    return jsonify({
        "task_id": task.id,
        "rate_limit": {
            "remaining": remaining,
            "limit": limit.limit.amount,
            "reset": reset_at
        }
    }), 202


@fastighetsindelning_bp.route('/api/download', methods=['POST'])
@limiter.limit("5 per hour", key_func=get_remote_address)
def api_download_dxf():
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return jsonify({"error": "Missing Authorization header"}), 401

    try:
        token_type, credentials = auth_header.split(" ")
        license_key, email = credentials.split("|")
    except ValueError:
        return jsonify({"error": "Invalid Authorization header format"}), 401

    if not validate_license_and_email(license_key, email):
        return jsonify({"error": "Invalid license or email"}), 401

    bbox_str = request.json.get("bbox")
    if not bbox_str:
        return jsonify({"error": "Bounding box (bbox) parameter is required"}), 400

    try:
        minx, miny, maxx, maxy = map(float, bbox_str.split(","))
    except ValueError:
        return jsonify({"error": "Invalid bbox format"}), 400

    width_m, height_m = degrees_to_meters(minx, miny, maxx, maxy)
    if width_m > MAX_METERS or height_m > MAX_METERS:
        return jsonify({"error": "Bounding box exceeds 1000x1000 meter limit"}), 400

    try:
        cleanup_temp_files()
    except Exception as e:
        print("Unable to clean temp files: " + str(e))

    task = celery.send_task(
        "fastighet.routes.download_and_create_dxf", args=[bbox_str])

    limit = limiter.current_limit
    remaining = limit.remaining
    reset_at = datetime.fromtimestamp(limit.reset_at)

    # Spara task info i DB
    tracker = TaskTracker(
        user_id=email,
        task_id=task.id,
        rate_limit_remaining=remaining,
        rate_limit_total=limit.limit.amount,
        rate_limit_reset=reset_at,
        bbox=bbox_str,
    )
    db.session.add(tracker)
    db.session.commit()

    return jsonify({
        "task_id": task.id,
        "rate_limit": {
            "remaining": remaining,
            "limit": limit.limit.amount,
            "reset": reset_at
        }
    }), 202


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
    task = celery.AsyncResult(task_id)

    if task.state == 'PENDING':
        response = {"state": task.state, "status": "Task is pending..."}
    elif task.state == 'SUCCESS':
        # Skapa en temporär fil för DXF-innehållet
        if task_id not in TEMP_FILES:
            # result = task.info

            # Skapa en temporär fil med mkstemp
            fd, temp_file_path = tempfile.mkstemp(
                prefix="fastighet_",
                suffix=".dxf",
                dir="/tmp"
            )
            with os.fdopen(fd, 'wb') as temp_file:
                temp_file.write(task.info["dxf"])

            # Lägg till filen i TEMP_FILES med en utgångstid på 24 timmar
            TEMP_FILES[task_id] = {
                "file_path": temp_file_path,
                "expires_at": datetime.now() + timedelta(hours=24)
            }

            # Uppdatera TaskTracker med filens sökväg
            tracker = TaskTracker.query.filter_by(task_id=task_id).first()
            if tracker and not tracker.file_path:
                tracker.file_path = temp_file_path
                tracker.expires_at = datetime.now() + timedelta(hours=24)
                tracker.geojson = json.dumps(task.info["geojson"])
                db.session.commit()

        # Returnera filens URL
        file_url = url_for("fastighet.download_file", task_id=task_id)
        response = {
            "state": task.state,
            "status": "Task completed!",
            "file_url": file_url,
            "geojson": task.info["geojson"]
        }
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
