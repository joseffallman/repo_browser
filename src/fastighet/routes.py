import json
import os
import tempfile
from datetime import datetime, timedelta

from flask import (
    Blueprint,
    jsonify,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from config import (
    login_required,
)
from db import TaskTracker, db
from jocoding import validate_license_and_email
from tasks import celery

from .bbox import degrees_to_meters

fastighetsindelning_bp = Blueprint(
    'fastighet',
    __name__,
    url_prefix='/fastighet',
    template_folder='templates'
)

MAX_METERS = 1000


# Funktion för att hämta användarens ID från Flask-sessionen
def get_user_key():
    # Fallback till IP om "user" saknas
    return session.get("user", {}).get("id", get_remote_address())


def get_user_email() -> str:
    """Return User email from Authorization-headern, fallback to IP."""
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return get_remote_address()

    try:
        token_type, credentials = auth_header.split(" ")
        license_key, email = credentials.split("|")
    except ValueError:
        return get_remote_address()

    return email


# Skapa en Limiter-instans
limiter = Limiter(
    key_func=get_user_key,
    storage_uri="redis://redis:6379/1",
)


@fastighetsindelning_bp.route('/')
@login_required
def index():
    cleanup_temp_files()
    return render_template('fastighet.html')


@fastighetsindelning_bp.route('/api/trackers', methods=['GET'])
@login_required
def get_trackers():
    cleanup_temp_files()
    trackers = TaskTracker.query.filter(
        TaskTracker.user_email == session["user"]['email'],
        TaskTracker.rate_limit_reset >= datetime.now()
    ).order_by(TaskTracker.created_at.asc()).all()

    tracker: TaskTracker = trackers[0] if trackers else None
    if tracker:
        rate_info = {
            "remaining": tracker.rate_limit_remaining,
            "limit": tracker.rate_limit_total,
            "reset": int(tracker.rate_limit_reset.timestamp()),
            "task_id": tracker.task_id
        }
    else:
        rate_info = None

    tracker_list = [
        {
            "task_id": t.task_id,
            "created_at": t.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            "reset": int(t.rate_limit_reset.timestamp()),
            "bbox": t.bbox,
            "geojson": t.geojson,
            "file_path": t.file_path,
            "download_url": url_for("fastighet.download_file", task_id=t.task_id)
        }
        for t in trackers
    ]

    return jsonify({"trackers": tracker_list, "rate_info": rate_info})


@fastighetsindelning_bp.route('/api/get_working_tasks')
@login_required
def get_working_tasks():
    # Hämta alla aktiva tasks för den inloggade användaren
    trackers = TaskTracker.query.filter(
        TaskTracker.user_email == session["user"]['email'],
        TaskTracker.expires_at == None,
        TaskTracker.file_path == None,
    ).all()

    if not trackers:
        return jsonify({"tasks": []}), 200

    # Skapa en lista med task_id:n
    task_ids = [tracker.task_id for tracker in trackers]
    return jsonify({"tasks": task_ids}), 200


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
        print("Unable to clean temp files", e)

    # Starta Celery-task
    task = celery.send_task(
        "fastighet.routes.download_and_create_dxf", args=[bbox])

    # Hämta rate-limit-information från Flask-Limiter
    limit = limiter.current_limit
    remaining = limit.remaining
    reset_at = limit.reset_at

    # Spara task info i DB
    tracker = TaskTracker(
        user_email=session["user"]['email'],
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


@fastighetsindelning_bp.route('/api/download', methods=['POST', 'GET'])
@limiter.limit("5 per hour", key_func=get_user_email, deduct_when=lambda r: r.status_code == 202)
def api_download_dxf():
    """API-endpoint för att hämta DXF-data baserat på bbox.
    Använder Authorization-headern för att validera licens och e-post.
    bbox-format: "minx,miny,maxx,maxy" i grader i EPSG:4326"""

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

    if request.method == "POST":
        bbox_str = request.json.get("bbox")
    else:  # GET
        bbox_str = request.args.get("bbox")
    if not bbox_str:
        return jsonify({"error": "Bounding box (bbox) parameter is required"}), 400

    try:
        minx, miny, maxx, maxy = map(float, bbox_str.split(","))
    except ValueError:
        return jsonify({"error": "Invalid bbox format"}), 400

    width_m, height_m = degrees_to_meters(minx, miny, maxx, maxy)
    if width_m > MAX_METERS or height_m > MAX_METERS:
        return jsonify({"error": f"Bounding box with {width_m}x{height_m} exceeds 1000x1000 meter limit"}), 400

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
        user_email=email,
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
    """Tömmer file_path, geojson och expires_at för trackers vars expires_at har passerats."""
    now = datetime.now()
    expired_trackers = TaskTracker.query.filter(
        TaskTracker.expires_at < now).all()

    tracker: TaskTracker
    for tracker in expired_trackers:
        if tracker.file_path and os.path.exists(tracker.file_path):
            os.remove(tracker.file_path)
        tracker.file_path = None
        tracker.geojson = None

    db.session.commit()


@fastighetsindelning_bp.route('/task_status/<task_id>', methods=['GET'])
def task_status(task_id):
    """Kontrollerar status för en Celery-task och hanterar temporära filer"""
    task = celery.AsyncResult(task_id)

    if task.state == 'PENDING':
        response = {"state": task.state, "status": "Task is pending..."}
    elif task.state == 'SUCCESS':
        # Hämta task info från databasen och kontrollera om filen redan finns
        tracker: TaskTracker = TaskTracker.query.filter_by(
            task_id=task_id).first()
        if tracker and not tracker.file_path:

            # Skapa en temporär fil med mkstemp
            fd, temp_file_path = tempfile.mkstemp(
                prefix="fastighet_",
                suffix=".dxf",
                dir="/tmp"
            )
            # Skapa en temporär fil för DXF-innehållet
            with os.fdopen(fd, 'wb') as temp_file:
                temp_file.write(task.info["dxf"])

            # Uppdatera TaskTracker med filens sökväg
            tracker: TaskTracker = TaskTracker.query.filter_by(
                task_id=task_id).first()
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

    cleanup_temp_files()

    # Hämta task från databasen
    tracker = TaskTracker.query.filter_by(task_id=task_id).first()

    if not tracker:
        return jsonify({"error": "Task not found"}), 404

    if not tracker.file_path or not os.path.exists(tracker.file_path):
        return jsonify({"error": "File not found or expired"}), 404

    # Returnera filen som en nedladdning
    return send_file(tracker.file_path, as_attachment=True)
