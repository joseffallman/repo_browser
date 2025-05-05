#!/bin/bash
# Kör DB-migreringar
flask db upgrade

# Starta Gunicorn
exec gunicorn --bind 0.0.0.0:8000 "app:app"
