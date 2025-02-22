#!/bin/bash
sudo chown vscode -R /workspace

# Gå till arbetskatalogen
cd /workspace

echo "Installerar Python-bibliotek från requirements.txt..."
pip3 install --user -r requirements.txt
pip3 install --user -r requirements_dev.txt

echo "Setup är klar."
