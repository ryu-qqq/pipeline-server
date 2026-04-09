import os

from celery import Celery

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1")

celery_app = Celery(
    "pipeline",
    broker=CELERY_BROKER_URL,
    include=["app.adapter.inbound.worker.pipeline_task"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Seoul",
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)
