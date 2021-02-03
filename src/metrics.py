'''
Measure the throughput on a pipeline using the TICK stack (InfluxDB)
'''

import time
import sys
import os
import requests

INFLUXDB_URL = "http://localhost:8086/write?db=elitr"
BYTE_SIZE = 1024
PIPELINE_NAME = sys.argv[1]

while True:
    time_end = time.time() + 1 # 1 second
    read = 0
    while time.time() < time_end:
        os.read(0, BYTE_SIZE)
        read += 1
    requests.post("http://localhost:8086/write?db=elitr", data=f"{PIPELINE_NAME} value={BYTE_SIZE * read} {time.time_ns()}") 