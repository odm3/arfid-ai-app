web: gunicorn app:app --log-file=-
web: gunicorn app:app --timeout 180
celery -A app.celery worker --loglevel=info