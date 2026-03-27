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

from config import login_required
from db import TaskTracker, db
from jocoding import validate_license_and_email
from tasks import celery

# from .tasks import download_and_create_hojd

hojd_bp = Blueprint(
    "hojd",
    __name__,
    url_prefix="/hojd",
    template_folder="templates",
)

MAX_METERS = 1000


def get_user_key():
    return session.get("user", {}).get("id", get_remote_address())


def get_user_email() -> str:
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return get_remote_address()

    try:
        token_type, credentials = auth_header.split(" ")
        license_key, email = credentials.split("|")
    except ValueError:
        return get_remote_address()

    return email


limiter = Limiter(
    key_func=get_user_key,
    storage_uri="redis://redis:6379/1",
)


@hojd_bp.route("/")
@login_required
def index():
    cleanup_temp_files()
    return render_template("hojd.html")


@hojd_bp.route("/api/trackers", methods=["GET"])
@login_required
def get_trackers():
    cleanup_temp_files()
    trackers = TaskTracker.query.filter(
        TaskTracker.user_email == session["user"]["email"],
        TaskTracker.rate_limit_reset >= datetime.now(),
    ).order_by(TaskTracker.created_at.asc()).all()

    tracker = trackers[0] if trackers else None
    if tracker:
        rate_info = {
            "remaining": tracker.rate_limit_remaining,
            "limit": tracker.rate_limit_total,
            "reset": int(tracker.rate_limit_reset.timestamp()),
            "task_id": tracker.task_id,
        }
    else:
        rate_info = None

    tracker_list = [
        {
            "task_id": t.task_id,
            "created_at": t.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "reset": int(t.rate_limit_reset.timestamp()),
            "bbox": t.bbox,
            "geojson": t.geojson,
            "file_path": t.file_path,
            "download_url": url_for("hojd.download_file", task_id=t.task_id),
        }
        for t in trackers
    ]

    return jsonify({"trackers": tracker_list, "rate_info": rate_info})


@hojd_bp.route("/api/get_working_tasks")
@login_required
def get_working_tasks():
    trackers = TaskTracker.query.filter(
        TaskTracker.user_email == session["user"]["email"],
        TaskTracker.expires_at == None,
        TaskTracker.file_path == None,
    ).all()

    if not trackers:
        return jsonify({"tasks": []}), 200

    task_ids = [tracker.task_id for tracker in trackers]
    return jsonify({"tasks": task_ids}), 200


@hojd_bp.route("/download", methods=["POST"])
@limiter.limit("5 per hour")
@login_required
def download_hojd():
    bbox = request.json.get("bbox")
    if not bbox:
        return jsonify({"error": "Bounding box (bbox) parameter is required"}), 400

    try:
        cleanup_temp_files()
    except Exception as e:
        print("Unable to clean temp files", e)

    task = celery.send_task("hojd.routes.download_and_create_hojd", args=[bbox])

    limit = limiter.current_limit
    if limit is None:
        remaining = None
        reset_at = datetime.now().timestamp() + 3600
        limit_amount = None
    else:
        remaining = limit.remaining
        reset_at = limit.reset_at
        limit_amount = limit.limit.amount

    tracker = TaskTracker(
        user_email=session["user"]["email"],
        task_id=task.id,
        rate_limit_remaining=remaining,
        rate_limit_total=limit_amount,
        rate_limit_reset=datetime.fromtimestamp(reset_at),
        bbox=bbox,
    )
    db.session.add(tracker)
    db.session.commit()

    return jsonify({
        "task_id": task.id,
        "rate_limit": {
            "remaining": remaining,
            "limit": limit_amount,
            "reset": int(reset_at) if isinstance(reset_at, (int, float)) else int(datetime.now().timestamp()),
        },
    }), 202


@hojd_bp.route("/api/download", methods=["POST", "GET"])
@limiter.limit("5 per hour", key_func=get_user_email, deduct_when=lambda r: r.status_code == 202)
def api_download_hojd():
    """Api-endpoint to start download of 'markhöjdmodell' through STAC.
    Need Authorization header with valid license and email.
    bbox parameter in EPSG:4326 is required."""

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
    else:
        bbox_str = request.args.get("bbox")
    if not bbox_str:
        return jsonify({"error": "Bounding box (bbox) parameter is required"}), 400

    try:
        minx, miny, maxx, maxy = map(float, bbox_str.split(","))
    except ValueError:
        return jsonify({"error": "Invalid bbox format"}), 400

    # from .bbox import degrees_to_meters

    # width_m, height_m = degrees_to_meters(minx, miny, maxx, maxy)
    # if width_m > MAX_METERS or height_m > MAX_METERS:
    #     return jsonify({"error": f"Bounding box with {width_m}x{height_m} exceeds 1000x1000 meter limit"}), 400

    try:
        cleanup_temp_files()
    except Exception as e:
        print("Unable to clean temp files: " + str(e))

    task = celery.send_task("hojd.routes.download_and_create_hojd", args=[bbox_str])

    limit = limiter.current_limit
    if limit is None:
        remaining = None
        reset_datetime = datetime.now() + timedelta(hours=1)
        limit_amount = None
    else:
        remaining = limit.remaining
        reset_datetime = datetime.fromtimestamp(limit.reset_at)
        limit_amount = limit.limit.amount

    tracker = TaskTracker(
        user_email=email,
        task_id=task.id,
        rate_limit_remaining=remaining,
        rate_limit_total=limit_amount,
        rate_limit_reset=reset_datetime,
        bbox=bbox_str,
    )
    db.session.add(tracker)
    db.session.commit()

    return jsonify({
        "task_id": task.id,
        "rate_limit": {
            "remaining": remaining,
            "limit": limit_amount,
            "reset": int(reset_datetime.timestamp()),
        },
    }), 202


def cleanup_temp_files():
    now = datetime.now()
    expired_trackers = TaskTracker.query.filter(TaskTracker.expires_at < now).all()

    for tracker in expired_trackers:
        if tracker.file_path and os.path.exists(tracker.file_path):
            os.remove(tracker.file_path)
        tracker.file_path = None
        tracker.geojson = None
        tracker.expires_at = None

    db.session.commit()


@hojd_bp.route("/task_status/<task_id>", methods=["GET"])
def task_status(task_id):
    task = celery.AsyncResult(task_id)

    if task.state == "PENDING":
        response = {"state": task.state, "status": "Task is pending..."}
    elif task.state == "SUCCESS":
        tracker = TaskTracker.query.filter_by(task_id=task_id).first()
        if tracker and not tracker.file_path:
            fd, temp_file_path = tempfile.mkstemp(prefix="hojd_", suffix=".zip", dir="/tmp")
            with os.fdopen(fd, "wb") as temp_file:
                temp_file.write(task.info["zip"])

            tracker.file_path = temp_file_path
            tracker.expires_at = datetime.now() + timedelta(hours=24)
            tracker.geojson = json.dumps(task.info["geojson"])
            db.session.commit()

        file_url = url_for("hojd.download_file", task_id=task_id)
        response = {
            "state": task.state,
            "status": "Task completed!",
            "file_url": file_url,
            "geojson": task.info["geojson"],
        }
    elif task.state == "FAILURE":
        response = {"state": task.state, "status": str(task.info)}
    else:
        response = {"state": task.state, "status": "Task is in progress..."}

    return jsonify(response)


@hojd_bp.route("/download_file/<task_id>", methods=["GET"])
def download_file(task_id):
    cleanup_temp_files()

    tracker = TaskTracker.query.filter_by(task_id=task_id).first()
    if not tracker:
        return jsonify({"error": "Task not found"}), 404

    if not tracker.file_path or not os.path.exists(tracker.file_path):
        return jsonify({"error": "File not found or expired"}), 404

    return send_file(tracker.file_path, as_attachment=True)
