#!/bin/bash

# Gå till arbetskatalogen
cd /workspace

echo "Installerar Python-bibliotek från requirements.txt..."
pip3 install --user -r requirements.txt
pip3 install --user -r requirements_dev.txt

echo "Startar Celery worker..."
celery -A src.tasks worker -n worker1 --loglevel=info --detach

echo "Startar Flower för Celery-administration..."
# celery -A src.tasks flower --port=5555 --detach

echo "Setup är klar. Flask-appen kan startas manuellt med 'flask run'."
