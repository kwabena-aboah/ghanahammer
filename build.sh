#!/bin/bash
set -e

echo "Running Django collectstatic..."

python3 -m pip install --break-system-packages -r requirements.txt

python3 manage.py collectstatic --noinput --clear

echo "Collectstatic completed."

echo "Running Setup Data..."

python3 manage.py shell -c "exec(open('setup_data.py').read()); create_initial_data()"

echo "Setup Data completed."