#!/usr/bin/python3
'''
Usage: python3 replay.py <replay_file>
Accepts a file with timestamped logs and outputs the logs in real time, according to the logs.
Timestamps in replay file are expected to be monotonicaly increasing.
Lines can contain multiple square brackets.
Examples of file format:
	[2021-06-23 18:09:46] 3450 3970 Thank [you]. 
	[2021-06-23 18:09:49] 5850 7010 Cool. 
	[2021-06-23 18:09:50] 5850 7570 Good morning. 
	[2021-06-23 18:09:51] 5850 8290 Good morning. 
'''
import time
import datetime
import argparse

parser = argparse.ArgumentParser(description='Replay logs')
parser.add_argument('replay_file', help='The file to replay')
args = parser.parse_args()
replay_file = args.replay_file

# Timestamp of the last log printed
last_timestamp = None

# Open the file and iterate over lines
with open(replay_file, 'r') as f:
  for line in f:
    # Split the line into two columns: timestamp and log
    timestamp, log = line.split(']', 1)
    timestamp = timestamp[1:]
    # Strip the leading whitespace from the log
    log = log.lstrip()

    # Convert timestamp to datetime object
    timestamp = datetime.datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')

    # If it it's the first log, print it and set last_timestamp
    if last_timestamp is None:
      print(log, end='')
      last_timestamp = timestamp
    # If the timestamp is the same as the last timestamp, print the log
    elif timestamp == last_timestamp:
      print(log, end='')
    # Otherwise, wait the difference, print the log and set the last timestamp
    else:
      diff = timestamp - last_timestamp
      time.sleep(diff.total_seconds())
      print(log, end='')
      last_timestamp = timestamp
