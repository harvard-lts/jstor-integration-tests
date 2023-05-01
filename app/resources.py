import re
import glob
import shutil
import time
import requests, traceback
from flask_restx import Resource, Api
from flask import render_template, current_app
import os, os.path, json
import certifi
import ssl
from pymongo import MongoClient
#from celery import Celery
from tasks.tasks import do_task, get_end_message
import random, boto3


incoming_queue = os.environ.get('FIRST_QUEUE_NAME', 'first_queue')
transform_jstorforum_queue = os.environ.get('SECOND_QUEUE_NAME', 'transform_jstorforum')
publish_jstorforum_queue = os.environ.get('THIRD_QUEUE_NAME', 'publish_jstorforum')
completed_jstorforum_queue = os.environ.get('LAST_QUEUE_NAME', 'completed_jstorforum')


def define_resources(app):
    api = Api(app, version='1.0', title='JSTOR Integration Tests',
              description='This project contains the integration tests for the JSTOR project')
    dashboard = api.namespace('/', description="This project contains the integration tests for the JSTOR project")

    # Env vars
    mongo_url = os.environ.get('MONGO_URL')
    mongo_dbname = os.environ.get('MONGO_DBNAME')
    mongo_collection_name = os.environ.get('MONGO_COLLECTION')
    mongo_ssl_cert = os.environ.get('MONGO_SSL_CERT')
    sleep_secs = int(os.environ.get('SLEEP_SECS', 2))

    via_access_key = os.environ.get('S3_VIA_ACCESS_KEY')
    via_secret_key = os.environ.get('S3_VIA_SECRET_KEY')
    via_bucket_name = os.environ.get('S3_VIA_BUCKET')
    via_s3_endpoint = os.environ.get('S3_VIA_ENDPOINT')
    via_s3_region = os.environ.get('S3_VIA_REGION')
    via_test_object = os.environ.get('S3_VIA_TEST_OBJECT')

    ssio_access_key = os.environ.get('S3_SSIO_ACCESS_KEY')
    ssio_secret_key = os.environ.get('S3_SSIO_SECRET_KEY')
    ssio_bucket_name = os.environ.get('S3_SSIO_BUCKET')
    ssio_s3_endpoint = os.environ.get('S3_SSIO_ENDPOINT')
    ssio_s3_region = os.environ.get('S3_SSIO_REGION')
    ssio_test_object = os.environ.get('S3_SSIO_TEST_OBJECT')

    aspace_access_key = os.environ.get('S3_ASPACE_ACCESS_KEY')
    aspace_secret_key = os.environ.get('S3_ASPACE_SECRET_KEY')
    aspace_bucket_name = os.environ.get('S3_ASPACE_BUCKET')
    aspace_s3_endpoint = os.environ.get('S3_ASPACE_ENDPOINT')
    aspace_s3_region = os.environ.get('S3_ASPACE_REGION')
    aspace_test_object = os.environ.get('S3_ASPACE_TEST_OBJECT')

    s3_test_prefix = os.environ.get('S3_TEST_PREFIX')

    dashboard_url = os.environ.get('DASHBOARD_URL')

    harvest_records_collection_name = os.environ.get('JSTOR_HARVESTED_RECORDS', 'jstor_harvested_records')
    transform_records_collection_name = os.environ.get('JSTOR_TRANSFORMED_RECORDS', 'jstor_transformed_records')
    publish_records_collection_name = os.environ.get('JSTOR_PUBLISHED_RECORDS', 'jstor_published_records')

    harvest_summary_collection_name = os.environ.get('JSTOR_HARVESTED_SUMMARY', 'jstor_harvested_summary')
    transform_summary_collection_name = os.environ.get('JSTOR_TRANSFORMED_SUMMARY', 'jstor_transformed_summary')
    publish_summary_collection_name = os.environ.get('JSTOR_PUBLISHED_SUMMARY', 'jstor_published_summary')

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
        test_message = {"job_ticket_id":job_ticket_id, "integration_test": True}
        task_result = do_task(test_message)
        task_id = task_result.id
        #dump json
        current_app.logger.info("job ticket id: " + job_ticket_id)

        #read from mongodb
        try:
            mongo_client = MongoClient(mongo_url, maxPoolSize=1)
            mongo_db = mongo_client[mongo_dbname]
            
            harvest_records_collection = mongo_db[harvest_records_collection_name]
            transform_records_collection = mongo_db[transform_records_collection_name]
            publish_records_collection = mongo_db[publish_records_collection_name]

            harvest_summary_collection = mongo_db[harvest_summary_collection_name]
            transform_summary_collection = mongo_db[transform_summary_collection_name]
            publish_summary_collection = mongo_db[publish_summary_collection_name]

            time.sleep(sleep_secs) #wait for queue 

            components = [{"name": "Harvester",  "collection": harvest_records_collection}, 
                {"name": "Transformer", "collection": transform_records_collection}, 
                {"name": "Publisher", "collection": publish_records_collection}]
            query = {"harvest_id": job_ticket_id}
            for component in components:
                col = component["collection"]
                itest_record = col.find_one(query)
                shortname = itest_record["repo_short_name"]
                status = itest_record["status"]
                if (itest_record == None): #check for connectivity
                    result["num_failed"] += 1
                    result["tests_failed"].append(component["name"])
                if (shortname == None): #check for repository shortname
                    result["num_failed"] += 1
                    result["tests_failed"].append(component["name"])
                    result["missing_shortname"] = {"text": "repository_shortname not found in record"}
                if ((status != "harvested") and (status != "add_update")): #  "status": "add_update" or "harvested"
                    result["num_failed"] += 1
                    result["tests_failed"].append(component["name"])
                    result["missing_status"] = {"text": "incorrect status in record"}
            # test to see if publish records are correct 
            dest_query1 = {"harvest_id": job_ticket_id, "destination": "SSIO"}
            dest_query2 = {"harvest_id": job_ticket_id, "destination": "VIA"}
            dest_query3 = {"harvest_id": job_ticket_id, "destination": "primo"}
            dest_query4 = {"harvest_id": job_ticket_id, "destination": "lc"}
            dest_rec1 = publish_records_collection.find_one(dest_query1)
            if (dest_rec1 == None):
                result["num_failed"] += 1
                result["tests_failed"] = {"text": "No records found w/ SSIO destination"}
            dest_rec2 = publish_records_collection.find_one(dest_query2)
            if (dest_rec2 == None):
                result["num_failed"] += 1
                result["tests_failed"] = {"text": "No records found w/ VIA destination"}
            dest_rec3 = publish_records_collection.find_one(dest_query3)
            if (dest_rec3 == None):
                result["num_failed"] += 1
                result["tests_failed"] = {"text": "No records found w/ Primo destination"}
            dest_rec4 = publish_records_collection.find_one(dest_query4)
            if (dest_rec4 == None):
                result["num_failed"] += 1
                result["tests_failed"] = {"text": "No records found w/ Librarycloud destination"}
            #test for dropped records
            drop_query = {"harvest_id": job_ticket_id, "status": "drop"}
            dropped_xform_rec = transform_records_collection.find_one(drop_query)
            if (dropped_xform_rec == None):
                result["num_failed"] += 1
                result["tests_failed"] = {"text": "No dropped records found in jstor_transformed_records collection"}
            #test for deleted records
            del_query = {"harvest_id": job_ticket_id, "status": "delete"}
            deleted_xform_rec = transform_records_collection.find_one(del_query)
            if (deleted_xform_rec == None):
                result["num_failed"] += 1
                result["tests_failed"] = {"text": "No deleted records found in jstor_transformed_records collection"}
            deleted_publish_rec = publish_records_collection.find_one(del_query)
            if (deleted_publish_rec == None):
                result["num_failed"] += 1
                result["tests_failed"] = {"text": "No deleted records found in jstor_published_records collection"}
            #test to see that there are no dupe entries in jstor_published summary
            check_pub_query = {"id": job_ticket_id, "jobname": "jstorforum"}
            pub_summary_recs = publish_summary_collection.count_documents(check_pub_query)
            if (pub_summary_recs > 2): #incr and full jstorforum harvests
                result["num_failed"] += 1
                result["tests_failed"] = {"text": "Duplicate records found in jstor_published_summary collection"}
            elif (pub_summary_recs == 0):
                result["num_failed"] += 1
                result["tests_failed"] = {"text": "No records found in jstor_published_summary collection"}
            mongo_client.close()
        except Exception as err:
            result["num_failed"] += 1
            result["tests_failed"].append("Mongo")
            result["Failed Mongo"] = {"status_code": 500, "text": str(err) }
            mongo_client.close()

        #Check S3 buckets
        try:
            via_boto_session = boto3.Session(aws_access_key_id=via_access_key, aws_secret_access_key=via_secret_key)
            via_s3_resource = via_boto_session.resource('s3')
            via_s3_bucket = via_s3_resource.Bucket(via_bucket_name)

            try:
                via_s3_bucket.Object(via_test_object).last_modified
            except Exception as err:
                result["num_failed"] += 1
                result["tests_failed"].append("VIA")
                result["Failed VIA bucket"] = {"status_code": 500, "text": str(err) }
                traceback.print_exc()

            ssio_boto_session = boto3.Session(aws_access_key_id=ssio_access_key, aws_secret_access_key=ssio_secret_key)
            ssio_s3_resource = ssio_boto_session.resource('s3')
            ssio_s3_bucket = ssio_s3_resource.Bucket(ssio_bucket_name)

            try:
                ssio_s3_bucket.Object(ssio_test_object).last_modified
            except Exception as err:
                result["num_failed"] += 1
                result["tests_failed"].append("SSIO")
                result["Failed SSIO bucket"] = {"status_code": 500, "text": str(err) }
                traceback.print_exc()

            aspace_boto_session = boto3.Session(aws_access_key_id=aspace_access_key, aws_secret_access_key=aspace_secret_key)
            aspace_s3_resource = aspace_boto_session.resource('s3')
            aspace_s3_bucket = aspace_s3_resource.Bucket(aspace_bucket_name)

            #todo: since aspace harvests are unpredictable, query mongo to see if it actually harvested anything.
            # if so, then check to see if those records are in S3
            # try:
            #     aspace_s3_bucket.Object(aspace_test_object).last_modified
            # except Exception as err:
            #     result["num_failed"] += 1
            #     result["tests_failed"].append("Aspace")
            #     result["Failed Aspace bucket"] = {"status_code": 500, "text": str(err) }
            #     traceback.print_exc()

            # delete contents of s3 test export folder to reset test
            via_s3_bucket.objects.filter(Prefix=s3_test_prefix).delete()
            ssio_s3_bucket.objects.filter(Prefix=s3_test_prefix).delete()
            #aspace_s3_bucket.objects.filter(Prefix="").delete()

        except Exception as err:
            result["num_failed"] += 1
            result["tests_failed"].append("S3")
            result["Failed S3"] = {"status_code": 500, "text": str(err) }

        #check if dashboard is running
        try:
            dashboard_response = requests.get(dashboard_url, verify=False)
            if dashboard_response.status_code != 200:
                result["num_failed"] += 1
                result["tests_failed"].append("Dashboard")
                result["Dashboard HTTP Error"] = {"status_code": dashboard_response.status_code}
        except Exception as err:
            result["num_failed"] += 1
            result["tests_failed"].append("Dashboard")
            result["Dashboard HTTP Error"] = {"status_code": 500, "text": str(err) }


        return json.dumps(result)



    

