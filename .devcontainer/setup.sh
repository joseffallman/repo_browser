#!/bin/bash
sudo chown vscode -R /workspace
sudo mkdir -p /app/data
sudo chown vscode -R /app/data

# Sätt FLASK_APP-miljövariabeln
cd /workspace/src
export FLASK_APP=src/app.py

# Gå till arbetskatalogen
cd /workspace

python -m venv .venv
source .venv/bin/activate

echo "Installerar Python-bibliotek från requirements.txt..."
pip3 install -r requirements.txt
pip3 install -r requirements_dev.txt

echo "Setup är klar."
