#!/bin/bash
sudo chown vscode -R /workspace
sudo mkdir -p /app/data
sudo chown vscode -R /app/data

# Gå till arbetskatalogen
cd /workspace

# Add to PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:/workspace/src"

echo "Installerar Python-bibliotek från requirements.txt..."
pip3 install --user -r requirements.txt
pip3 install --user -r requirements_dev.txt

echo "Setup är klar."
