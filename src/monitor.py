#!/usr/bin/python3
# Usage: python3 pipeliner.py <files-to-watch>
"""
This script accepts paths to files and monitors the rate at which they change.
Specifically, for each file, the time between last X changes is stored and used to compute an average changed time.
For each file, this average is displayed, along with the file size in square brackets
After the brackets, the time for how long the file has been unchanged is also shown.
When the unchanged time is higher than the treshold (see below), the file shows red.
Each file also has a graph showing it's recent status history

Probably will not work on Windows.
"""
# How many durations are used to compute the average?
LAST_X_AVERAGES = 5

# How long is the graph?
GRAPH_LENGTH = 30

# The multiple of the average duration; if the file is unchanged above this multipled duration, it shows red.
TRESHOLD = 2

# Padding in each directory
LEFT_PADDING = "     "

# Number of seconds between each check
REFRESH_RATE = 0.5

import sys
import os
import datetime
import time

class bcolors:
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BACKGROUND_GREEN = '\u001b[42m'
    BACKGROUND_RED = '\u001b[41m'

clear = lambda: os.system('clear')
green = lambda msg: bcolors.OKGREEN + msg + bcolors.ENDC
orange = lambda msg: bcolors.WARNING + msg + bcolors.ENDC
red = lambda msg: bcolors.FAIL + msg + bcolors.ENDC

green_square = bcolors.BACKGROUND_GREEN + bcolors.OKGREEN + "." + bcolors.ENDC
red_square = bcolors.BACKGROUND_RED + bcolors.FAIL + "." + bcolors.ENDC

format_duration = lambda d: f"{int(d.total_seconds() // 60)}:{('0' if d.total_seconds() % 60 < 10 else '') + str(int(d.total_seconds() % 60))}"
# Pretty-print file size in bytes
format_size = lambda bytes: str(bytes) + "B" if bytes < 1024 else str(bytes // 1024) + "kB" if bytes < 1024 * 1024 else str(bytes // (1024 * 1024)) +  "MB"

files = sys.argv[1:]
if len(files) == 0:
    print("No files specified! Specify at least one file.")
    exit(1)

stats = {}
dirs = {}
max_lengths = {}
for file in files:
    stats[file] = {
        "last_time": datetime.datetime.fromtimestamp(os.path.getmtime(file)),
        "previous_times_to_change": [],
        "graph": []
    }
    dir_path = os.path.abspath(os.path.dirname(file))
    if dir_path not in dirs:
        dirs[dir_path] = []
    dirs[dir_path].append(file)

for dir in dirs:
    max_length = 0
    for file in dirs[dir]:
        max_length = max(max_length, len(file))
    max_lengths[dir] = max_length

# Paddings so everything is aligned
max_file_size = 0
max_unchanged_duration = 0

while True:
    clear()
    for dir in dirs:
        print(dir)
        for file in dirs[dir]:
            last_changed = datetime.datetime.fromtimestamp(os.path.getmtime(file))
            file_size = format_size(os.path.getsize(file))
            max_file_size = max(max_file_size, len(file_size))
            s = stats[file]
            
            q = s["previous_times_to_change"]
            change_time = last_changed - s["last_time"]
            # The file has changed
            if s["last_time"] != last_changed:
                # How long it took for the file to change
                q.append(change_time)
                if len(q) > LAST_X_AVERAGES:
                    q.pop(0)
                s["last_time"] = last_changed
            average = datetime.timedelta()
            for previous_size in q:
                average += previous_size
            average = average / max(len(q), 1)
            
            unchanged_duration = datetime.datetime.now() - last_changed
            max_unchanged_duration = max(max_unchanged_duration, len(format_duration(unchanged_duration)))
            graph = s["graph"]
            right_pad = " " * (max_lengths[dir] - len(file))

            color = None
            if unchanged_duration <  TRESHOLD * average:
                graph.append(green_square)
                color = green
            else:
                graph.append(red_square)
                color = red
            
            if len(graph) > GRAPH_LENGTH:
                graph.pop(0)
            print(LEFT_PADDING + f"{os.path.basename(file)}{right_pad} [avg: {format_duration(average)}, size: {file_size}{(max_file_size - len(file_size)) * ' '}]    {color(format_duration(unchanged_duration))}{(max_unchanged_duration - len(format_duration(unchanged_duration))) * ' '} {''.join(graph)}")
    time.sleep(REFRESH_RATE)

        
    