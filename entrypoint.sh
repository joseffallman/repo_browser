#!/bin/bash
# Kör DB-migreringar
cd src/
flask db upgrade
cd ..

# Starta Gunicorn
exec gunicorn --bind 0.0.0.0:8000 "src.app:app"
