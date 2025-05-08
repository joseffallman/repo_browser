#!/bin/bash
set -e

# Kontrollera första argumentet och starta rätt process
if [ "$1" = "celery" ]; then
    echo "Starting Celery worker..."
    exec celery -A src.tasks.celery worker
else
    # Kör DB-migreringar
    cd /app/src
    flask db upgrade
    cd /app

    # Starta Gunicorn
    exec gunicorn --bind 0.0.0.0:8000 "src.app:app"
fi
