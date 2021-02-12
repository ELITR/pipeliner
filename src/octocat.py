#!/usr/bin/python3

'''
# OCTOCAT
CATs inputs specified in *.in files. Selects one output (specified in SELECT) at time.

USAGE
args: --interval - interval to check the SELECT file

Inputs:
*.in files with port adderess
SELECT - current input to be selected and outputted to STDOUT; default: first input

Outputs:
*.preview for each input

Concatenated output is written to the STDOUT
'''

import argparse
import glob
import sys
import socket
import threading
import queue
import time
import select

class Socket(threading.Thread):
    def __init__(self, preview, port):
        threading.Thread.__init__(self)
        self.preview = preview
        self.port = port
        self.queue = queue.Queue()
        self.read = False
        self.is_running = True

    def run(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setblocking(False)
        server.bind(('0.0.0.0', self.port))
        server.listen()

        with open(self.preview, 'wb') as preview:
            while self.is_running:
                try:
                    ready = select.select([server],[],[],1)
                    if not ready[0]:
                        continue
                    conn, _ = server.accept()
                    conn.setblocking(False)
                    with conn:
                        while self.is_running:
                            ready = select.select([conn],[],[],1)
                            if not ready[0]:
                                continue
                            data = conn.recv(1024)
                            if not data:
                                break
                            if self.read:
                                self.queue.put(data)
                            preview.write(data)
                            preview.flush()
                except socket.error:
                    continue

class Stdin(threading.Thread):
    def __init__(self, preview):
        threading.Thread.__init__(self)
        self.preview = preview
        self.queue = queue.Queue()
        self.read = False

    def run(self):
        with open(self.preview, 'wb') as preview:
            while True:
                data = sys.stdin.buffer.read(1024)
                if self.read:
                    self.queue.put(data)
                preview.write(data)
                preview.flush()

def load_inputs():
    inputs = {}
    for i in glob.glob('*.in'):
        f = open(i).readline().strip()
        preview = i.replace('.in', '.preview')
        name = i.split('/')[-1].replace('.in', '')
        if f == 'stdin':
            inputs[name] = Stdin(preview)
        else:
            port = int(f)
            inputs[name] = Socket(preview, port)
    return inputs

def read_select(inputs):
    try:
        s = open('SELECT').readline().strip()
        if s in inputs.keys():
            return inputs[s]
    except:
        return list(inputs)[0]

def main(args):
    inputs = load_inputs()

    for _, input in inputs.items():
        input.start()

    select = read_select(inputs)
    select.read = True
    select2 = None
    while True:    
        try:
            start = time.time()
            while True:
                try:
                    data = select.queue.get(timeout=args.interval)
                    sys.stdout.buffer.write(data)
                    sys.stdout.buffer.flush()
                except queue.Empty:
                    if select2 is not None:
                        select = select2
                        select2 = None
                if time.time() - start > args.interval:
                    select2 = read_select(inputs)
                    if select2 != select:
                        select.read = False
                        select2.read = True
                    else:
                        select2 = None
        except KeyboardInterrupt:
            for _, input in inputs.items():
                input.is_running = False
            for _, input in inputs.items():
                input.join()
            break

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--interval', default=0.5, type=int)

    args = parser.parse_args()
    main(args)
