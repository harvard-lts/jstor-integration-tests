
import re
import glob
import shutil
import time
import requests
from flask_restx import Resource, Api
from flask import render_template, current_app
import os, os.path, json
import certifi
import ssl
from pymongo import MongoClient
#from celery import Celery
from tasks.tasks import do_task, get_end_message
import random

#celery_client = Celery('tasks')
#celery_client.config_from_object('celeryconfig')

incoming_queue = os.environ.get('FIRST_QUEUE_NAME', 'first_queue')
transform_jstorforum_queue = os.environ.get('SECOND_QUEUE_NAME', 'transform_jstorforum')
publish_jstorforum_queue = os.environ.get('THIRD_QUEUE_NAME', 'publish_jstorforum')
completed_jstorforum_queue = os.environ.get('LAST_QUEUE_NAME', 'completed_jstorforum')


def define_resources(app):
    api = Api(app, version='1.0', title='JSTOR Integration Tests',
              description='This project contains the integration tests for the JSTOR project')
    dashboard = api.namespace('/', description="This project contains the integration tests for the JSTOR project")

    # Env vars
    harvester_endpoint = os.environ.get('HARVESTER_ENDPOINT')
    publisher_endpoint = os.environ.get('PUBLISHER_ENDPOINT')
    transformer_endpoint = os.environ.get('TRANSFORMER_ENDPOINT')
    mongo_url = os.environ.get('MONGO_URL')
    mongo_dbname = os.environ.get('MONGO_DBNAME')
    mongo_collection = os.environ.get('MONGO_COLLECTION')
    mongo_ssl_cert = os.environ.get('MONGO_SSL_CERT')
    sleep_secs = int(os.environ.get('SLEEP_SECS', 2))

    # Version / Heartbeat route
    @dashboard.route('/version', endpoint="version", methods=['GET'])
    class Version(Resource):
        def get(self):
            version = os.environ.get('APP_VERSION', "NOT FOUND")
            return {"version": version}


    @app.route('/integration')
    def integration_test():
        num_failed_tests = 0
        tests_failed = []
        result = {"num_failed": num_failed_tests, "tests_failed": tests_failed, "info": {}}

        # Send a simple task (create and send in 1 step)
        #res = client.send_task('tasks.tasks.do_task', args=[{"job_ticket_id":"123","hello":"world"}], kwargs={}, queue=incoming_queue)
        #read from 'final_queue' to see that it went through the pipeline
        job_ticket_id = str(random.randint(1, 4294967296))
        test_message = {"job_ticket_id":job_ticket_id, "hello":"world"}
        task_result = do_task(test_message)
        task_id = task_result.id

        #read from mongodb
        try:
            mongo_url = os.environ.get('MONGO_URL')
            mongo_dbname = os.environ.get('MONGO_DBNAME')
            mongo_client = MongoClient(mongo_url, maxPoolSize=1)

            mongo_db = mongo_client[mongo_dbname]
            integration_collection = mongo_db['integration_test']

            harvester_filter = {"id": "harvester-" + job_ticket_id, "name": "Harvester"}
            transformer_filter = {"id": "transformer-" + job_ticket_id, "name": "Transformer"}
            publisher_filter = {"id": "publisher-" + job_ticket_id, "name": "Publisher"}

            filters = [harvester_filter, transformer_filter, publisher_filter]
            time.sleep(sleep_secs) #wait for queue 
            for component_filter in filters:
                query  = { "id": component_filter["id"] }
                itest_record = integration_collection.find_one(query)
                if (itest_record == None):
                    result["num_failed"] += 1
                    result["tests_failed"].append(component_filter["name"])

            mongo_client.close()
        except Exception as err:
            result["num_failed"] += 1
            result["tests_failed"].append("Mongo")
            result["Failed Mongo"] = {"status_code": 500, "text": "Failed mongo connection"}
            mongo_client.close()

        return json.dumps(result)



    

