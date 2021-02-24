#!/usr/bin/env python3
# Usage; ./rainbow-splitter.py [LIST_OF_LANGS] [LIST_OF_PORTS]
# Splits a rainbow MT packet into individual languages , outputting on ports
import sys
import math
import socket

import sys
def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)

args = sys.argv[1:]
half = len(args) // 2
langs = args[:half]
ports = list(map(lambda x: int(x), args[half:]))

sockets = {}

eprint("rainbow-splitter starting")
eprint("Expected to receive langs:    ", langs)
eprint("Expected to receive on ports: ", ports)
langsset = " ".join(sorted(langs))

assert len(langs) == len(ports), f"Mismatched lengths of langs and ports: {len(langs)} vs {len(ports)}"

for lang, port in zip(langs, ports):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    s.connect(("127.0.0.1", port))
    sockets[lang] = s

for line in sys.stdin:
    line = line.rstrip("\r\n")
    timestamp = " ".join(line.split(" ")[:2])
      # the timestamp are the first two words on the line
    packets = line.split("\t")
    packets[0] = packets[0].split(" ")[2]
      # strip the timestamp from the first column
    gotlangs = packets[0::2]
    gotlangsset = " ".join(sorted(gotlangs))
    assert langsset == gotlangsset, f"Mismatched set of languages:\nEXP: {langsset}\nGOT: {gotlangsset}"
    pairs = zip(gotlangs, packets[1::2])
    for lang, sentence in pairs:
        if lang in langs:
            print(sentence)
            try:
                sockets[lang].send(f"{timestamp} {sentence}\n".encode())
            except BrokenPipeError:
                eprint(f"Failed to send sentences to {lang}, port {sockets[lang].getnameinfo()[1]}")

