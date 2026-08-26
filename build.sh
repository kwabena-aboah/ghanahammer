#!/bin/bash
set -e

echo "Running Django collectstatic..."

python manage.py collectstatic --noinput

echo "Collectstatic completed."