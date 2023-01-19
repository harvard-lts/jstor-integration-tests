from listener.celery import celery
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import celery as celeryapp
import os

incoming_queue = os.environ.get('FIRST_QUEUE_NAME', 'first_queue_itest')
transform_jstorforum_queue = os.environ.get('SECOND_QUEUE_NAME', 'transform_jstorforum_itest')
publish_jstorforum_queue = os.environ.get('THIRD_QUEUE_NAME', 'publish_jstorforum_itest')
completed_jstorforum_queue = os.environ.get('LAST_QUEUE_NAME', 'completed_jstorforum_itest')

retry_strategy = Retry(
    total=3,
    status_forcelist=[429, 500, 502, 503, 504],
    backoff_factor=1
)
adapter = HTTPAdapter(max_retries=retry_strategy)
http_client = requests.Session()
http_client.mount("https://", adapter)
http_client.mount("http://", adapter)

@celery.task(ignore_result=False, acks_late=True)
def do_task(message):
    response = celeryapp.execute.send_task("tasks.tasks.do_task", args=[message], kwargs={}, queue=incoming_queue)
    return response

@celery.task(queue=completed_jstorforum_queue)
def get_end_message(message):
    return message