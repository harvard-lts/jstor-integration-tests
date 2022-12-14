import re
import glob
import shutil
import time
import requests
from flask_restx import Resource, Api
from flask import render_template
import os, os.path, json
import certifi
import ssl
from pymongo import MongoClient


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

        # check mongo connectivity
        # client = MongoClient(mongo_url, maxPoolSize=1)
        # server_info = client.server_info()
        # result["server_info"] = server_info
        # if server_info == None:
        #     result["num_failed"] += 1
        #     result["tests_failed"].append("Mongo")
        #     result["Failed Harvester"] = {"status_code": 500, 
        #         "text": "Failed mongo connection"}
        # client.close()


        app.logger.debug("starting integration test")
        # harvester
        harvester_msg = {"job_ticket_id":"123","hello":"harvester"}
        harvester_response = requests.post(
            harvester_endpoint + '/do_task',
            json=harvester_msg,
            verify=False)
        harvester_json = harvester_response.json()
        if harvester_response.status_code != 200:
            result["num_failed"] += 1
            result["tests_failed"].append("Harvester")
            result["Failed Harvester"] = {"status_code": harvester_response.status_code,
                                               "text": harvester_json["message"]}

        
        # transformer
        transformer_msg = {"job_ticket_id":"123","hello":"transformer"}
        transformer_response = requests.post(
            transformer_endpoint + '/do_task',
            json=transformer_msg,
            verify=False)
        transformer_json = transformer_response.json()
        if transformer_response.status_code != 200:
            result["num_failed"] += 1
            result["tests_failed"].append("Transformer")
            result["Failed Transformer"] = {"status_code": transformer_response.status_code,
                                               "text": transformer_json["message"]}

        
        # publisher
        publisher_msg = {"job_ticket_id":"123","hello":"publisher"}
        publisher_response = requests.post(
            publisher_endpoint + '/do_task',
            json=publisher_msg,
            verify=False)
        publisher_json = publisher_response.json()
        if publisher_response.status_code != 200:
            result["num_failed"] += 1
            result["tests_failed"].append("Publisher")
            result["Failed Publisher"] = {"status_code": publisher_response.status_code,
                                               "text": publisher_json["message"]}

        return json.dumps(result)

