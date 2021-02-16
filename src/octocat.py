#!/usr/bin/env python3
# run the python3 from your environment, not forcefully /usr/bin/

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
import logging

class Socket(threading.Thread):
    def __init__(self, preview, port):
        threading.Thread.__init__(self)
        self.preview = preview
        self.port = port
        self.queue = queue.Queue()
        self.read = False
        self.is_running = True

    def run(self):
        while True:
            try:
                server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                server.setblocking(False)
                server.bind(('0.0.0.0', self.port))
                server.listen()
                break
            except:
                logging.error(f'port {self.port} in use, retrying to connect...')
                time.sleep(1)


        with open(self.preview, 'wb') as preview:
            while self.is_running:
                try:
                    ready = select.select([server],[],[],1)
                    logging.debug(f'waiting for a connection on port {self.port}')
                    if not ready[0]:
                        continue
                    conn, _ = server.accept()
                    logging.debug(f'got connection on port {self.port}')
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
                    logging.error(f'connection error on port {self.port}')
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
            logging.debug(f'input {f}: STD IN')
        else:
            port = int(f)
            inputs[name] = Socket(preview, port)
            logging.debug(f'input {f}: socket on port {port}')
    return inputs

def read_select(inputs):
    try:
        s = open('SELECT').readline().strip()
        return inputs[s]
    except:
        logging.error(f'invalid entry in SELECT; valid entries: {list(inputs.keys())}')
        return list(inputs.items())[0][1]

def main(args):
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if args.debug else logging.ERROR)

    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('[%(asctime)12s %(levelname)s %(filename)s:%(lineno)3d] %(message)s')
    handler.setFormatter(formatter)
    root.addHandler(handler)

    inputs = load_inputs()

    for _, input in inputs.items():
        input.start()

    select = read_select(inputs)
    select.read = True
    select2 = None
    while True:    
        try:
            start = time.time()
            read_len = 0
            while True:
                try:
                    data = select.queue.get(timeout=args.interval)
                    read_len += len(data)
                    sys.stdout.buffer.write(data)
                    sys.stdout.buffer.flush()
                except queue.Empty:
                    if select2 is not None:
                        read_len = 0
                        select = select2
                        select2 = None
                        logging.debug('changed source')
                        break
                if time.time() - start > args.interval:
                    logging.debug(f'read {read_len} bytes during last {time.time() - start} seconds')
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
    global args
    parser = argparse.ArgumentParser()
    parser.add_argument('--interval', default=0.5, type=int)
    parser.add_argument('--debug', default=False, action='store_true')

    args = parser.parse_args()
    main(args)
