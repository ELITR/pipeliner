#!/usr/bin/python3

# Usage: python3 pids.py <pid-files>
"""
This script accepts paths to files with component PIDs and monitors if the components are alive.

Probably will not work on Windows.
"""

import sys
import os
import time
import subprocess as sb

class bcolors:
    OKGREEN = '\033[92m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'

clear = lambda: os.system('clear')
green = lambda msg: bcolors.OKGREEN + msg + bcolors.ENDC
red = lambda msg: bcolors.FAIL + msg + bcolors.ENDC

args = sys.argv[1:]
pids = {}
min_padding = 0

for file in args:
    with open(file) as f:
        pid = int(f.read())
        node_name = os.path.basename(file)
        pids[node_name] = pid
        min_padding = max(min_padding, len(node_name))

while True:
    clear()
    proc_list = [int(pid) for pid in sb.run("ps -ef | awk '{print $2}'", shell=True, capture_output=True).stdout.decode().split("\n")[1:-1]]
    for name, pid in pids.items():
        padding = " " * (min_padding - len(name))
        message = ""
        if pid in proc_list:
            message = green("ALIVE")
        else:
            message = red("DEAD")

        print(f"{name}:{padding} {message}")
    time.sleep(0.5)
    
