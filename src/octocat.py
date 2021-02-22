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
import os
import socket
import threading
import queue
import time
import select
import logging
import pathlib

# print to stderr
def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


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

class Selector:
    def __init__(self):
        self.select_last_read_stamp = 0
        self.select_last_read = None

    def read_select(self, inputs):
        try:
            stamp = os.stat('SELECT').st_mtime
            if self.select_last_read_stamp == 0 or stamp != self.select_last_read_stamp:
                s = open('SELECT').readline().strip()
                selected = inputs[s]
                self.select_last_read_stamp = stamp
                self.select_last_read = selected
                logging.info(f'read SELECT, will now follow {s} ({selected})')
                return inputs[s]
            else:
                return self.select_last_read
        except:
            logging.error(f'invalid entry in SELECT; valid entries: {list(inputs.keys())}')
            return self.select_last_read if self.select_last_read is not None else list(inputs.items())[0][1]

def main(args):
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if args.debug else logging.INFO)

    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('[%(asctime)12s %(levelname)s %(filename)s:%(lineno)3d] %(message)s')
    handler.setFormatter(formatter)
    root.addHandler(handler)

    inputs = load_inputs()

    for _, input in inputs.items():
        input.start()

    selector = Selector()
    select = selector.read_select(inputs)
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
                    select2 = selector.read_select(inputs)
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
    parser.add_argument('--clobber', default=False, action='store_true')
    parser.add_argument('vars', nargs='*')
    args = parser.parse_args()

    if len(args.vars) > 0:
        # we should create the directory ourselves
        # usage: dirname port1 port2 port3 ...
        dirname=args.vars[0]
        ports=args.vars[1:]
        eprint("Dirname ", dirname)
        eprint("Ports ", ports)
        pathlib.Path(dirname).mkdir(parents=True, exist_ok=args.clobber)
          # create the directory and deep it ok if exists with --clobber
        os.chdir(dirname)
        for port in ports:
            f = open(port+".in", "w")
            f.write(port+"\n")
            f.close()
        # Now indicate that the first port is the one to be selected
        f = open("SELECT", "w")
        f.write(ports[0]+"\n")
        f.close()

    main(args)
