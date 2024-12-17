import os
import time

from celery import Celery

# Konfigurera Celery med Redis som broker och backend
celery = Celery("tasks", broker="redis://redis:6379/0", backend="redis://redis:6379/0")

if os.environ.get("FLASK_ENV") == "development":
    import debugpy

    debugpy.listen(("0.0.0.0", 5678))
    print("Waiting for debugger attach...")
    debugpy.wait_for_client()


@celery.task(bind=True)
def add(self, x, y):
    time.sleep(5)  # Simulera en lång körning
    result = x + y
    print(f"Debug: Adding {x} + {y} = {result}")
    return result
