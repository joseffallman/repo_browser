#!/bin/bash
# Kör DB-migreringar
cd /app/src
flask db upgrade
cd /app

# Starta Gunicorn
exec gunicorn --bind 0.0.0.0:8000 "src.app:app"
