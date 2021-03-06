#!/usr/bin/env python3

"""
Version         :       1.0.0
Developed by    :       Justin Henderson

Automating file extraction submission and analysis to
Cuckoo Sandbox from Zeek

Based on BroCoo from Davy Boekhout (https://github.com/dboekhout/BroCoo)

"""

from pathlib import Path
import requests
import os.path
import time
import sys
import hashlib
import systemd.daemon

print("Starting up")
time.sleep(5)
print("Startup complete")
systemd.daemon.notify('READY=1')

# -------------------------------These values can be safely changed-------------------------------
# Set to 1 for verbose logging
debug = 1
# Location of the Cuckoo API and Cuckoo webinterface to send requests to.
# Requires backslash at the end
api_address = "http://CUCKOO_SANDBOX_HOST:PORT"

# Bearor authorization token to authentication to the cuckoo API
bearer_token = "AUTH_TOKEN_GOES_HERE"

# List of files you do not want cuckoo to analyze
disallowed_files = ["zip"]

# How long can cuckoo analyze a file before a timeout should occur
cuckoo_timeout = 300

# Set the threshold to ignore files that rank below the score_threshold level
# Low threshold values will cause more false positives
score_threshold = 4.0

# Location to output logs to
log_dir = "/tmp/cuckoo"

# Set this to the folder that contains files to monitor
folder_to_analyze = "/nsm/bro/extracted"

# ---------------------------These values should NOT be changed-----------------------------------
header_settings = {'Authorization': "Bearer " + str(bearer_token)}

# API address to submit files to Cuckoo
create_url = api_address + "/tasks/create/file"

# API address to check if a file was already analyzed by Cuckoo based on a SHA256 hash
hash_url = api_address + "/files/view/sha256/"

# Used to determine the score of the given file
report_url = api_address + "/tasks/report/"

# Used to determine if the analysis failed
task_list = api_address + "/tasks/list/"

# Get the status information for a specific task
task_view = api_address + "/tasks/view/"

# Determine the SHA256 hash of the file that Bro extracted and return it
def get_hash():
    hash_256 = hashlib.sha256()
    with open(file, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_256.update(chunk)
    return hash_256.hexdigest()


# Based on a given hash, determine if the file has been analyzed before by Cuckoo,
# If it was analyzed before, return the score that it got the previous time.
def file_unique(sha_hash):
    request_results = requests.get(hash_url + sha_hash, headers=header_settings).json()
    if "sample" in request_results: 
        hash_task_id = request_results["sample"]["tasks"][0]
        return hash_task_id
    else:    
        submit_task_id = submit_file(file)
        return submit_task_id


# Submit file to Cuckoo Sandbox for analysis
def submit_file(file_path):
    print("Submitting file to cuckoo: " + file_path)
    with open(file_path, "rb") as sample:
        multipart_file = {"file": (file_name, sample)}
        results = requests.post(create_url, files=multipart_file, headers=header_settings).json()
        retrieved_task_id = results["task_id"]
    return retrieved_task_id


# Try to get the report generated by Cuckoo and determine assigned score,
# if the file that was submitted is queued, wait for it to lose the "pending" status.
# Once the pending status is dropped, start the timer to determine if the cuckoo timeout has been reached
# if score is retrieved within the timeout frame, return it.
# Finally, if the score cannot be retrieved or some other timeout / error occurs, assume the analysis failed and
# return a score of 0.0.
def get_score(task_id):
    try:
        while requests.get(task_view + str(task_id), headers=header_settings).json()["task"]["status"] == 'pending':
            time.sleep(20)
    except ValueError:
            return 0.0
    analysis_start = time.time()
    while (time.time() - analysis_start) < cuckoo_timeout:
        try:
            return requests.get(report_url + str(task_id), headers=header_settings).json()["info"]["score"]
        except KeyError:
            time.sleep(20)
    return 0.0

while True:
    files = []
    submitted_tasks = []
    for path in Path(folder_to_analyze).glob('**/*'):
        files.append(str(path.resolve()))

    for file in files:
        # Get the full file name without other path values
        file_name = os.path.basename(file)

        # File extension is split from file_name to determine what kind of file we are dealing with
        file_extension = file_name.split(".", 1)[1]
        if file_extension not in disallowed_files:
            if debug == 1:
                print("File name is " + file_name + " with an extension of " + file_extension)
            sha256hash = get_hash()
            if debug == 1:
                print("File has a sha256 hash of : " + sha256hash)
            task_id = file_unique(sha256hash)
            submitted_tasks.append(task_id)
            if debug == 1:
                print("Task ID is : " + str(task_id))
            score = get_score(task_id)
            print("File score is " + str(score))
    print('Files processed. Sleeping for 60 seconds')
    time.sleep(60)
