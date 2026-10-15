#!/usr/bin/env bash
# exit on error
set -o errexit

# Install dependencies
pip install -r requirements.txt

# Collect static files
python manage.py collectstatic --no-input

# Run migrations
python manage.py migrate

# Create the admin superuser automatically using env variables
python manage.py createsuperuser --no-input || true

# Load seed
python seed_demo_data.py