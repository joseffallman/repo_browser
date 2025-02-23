from flask import Blueprint, jsonify, request, url_for

from tasks import (
    add,
)

tasks_routes = Blueprint("tasks", __name__)


@tasks_routes.route("/start-task", methods=["GET"])
def start_task():
    x = request.args.get("x", 0, type=int)
    y = request.args.get("y", 0, type=int)

    # Starta Celery-jobbet asynkront
    task = add.delay(x, y)

    # Generera en länk till taskens status
    status_url = url_for(
        "routes.get_task_status",
        task_id=task.id,
        _external=True
    )

    return jsonify({
        "task_id": task.id,
        "status_url": status_url  # Länk till taskens status
    }), 202


@tasks_routes.route("/task-status/<task_id>", methods=["GET"])
def get_task_status(task_id):
    """ Kontrollera status på en Celery-task """
    task = add.AsyncResult(task_id)

    if task.state == "PENDING":
        response = {"state": task.state, "status": "Jobb i kö"}
    elif task.state == "SUCCESS":
        response = {"state": task.state, "result": task.result}
    elif task.state == "FAILURE":
        response = {"state": task.state, "status": "Jobbet misslyckades"}
    else:
        response = {"state": task.state, "status": "Jobb pågår"}

    return jsonify(response)
