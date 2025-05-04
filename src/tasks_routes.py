from flask import Blueprint, jsonify, request, url_for

from .tasks import (
    add,
    edit_file_task,
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
        "tasks.get_task_status",
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


@tasks_routes.route('/status/<task_id>')
def task_status(task_id):
    task = edit_file_task.AsyncResult(task_id)
    if task.state == 'PENDING':
        response = {
            'state': task.state,
            'status': 'Pending...',
            'message': "Uppgift är i kö"
        }
    elif task.state == 'SUCCESS':
        response = {
            'state': task.state,
            'status': task.info.get('status', 'COMPLETED'),
            'message': task.info.get('message', 'Task completed successfully.')
        }
    elif task.state != 'FAILURE':
        response = {
            'state': task.state,
            'status': task.info.get('status', ''),
            'message': task.info.get('message', str(task.info)),
        }
        if 'result' in task.info:
            response['result'] = task.info['result']
    else:
        response = {
            'state': task.state,
            'status': str(task.info),
            'message': task.message
        }
    return jsonify(response)
