#!/bin/bash
set -e

echo "Running Django collectstatic..."

python3 -m pip install --break-system-packages -r requirements.txt

python3 manage.py collectstatic --noinput --clear

echo "Collectstatic completed."