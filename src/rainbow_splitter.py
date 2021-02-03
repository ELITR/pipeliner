#!/usr/bin/python3
# Usage; ./rainbow-splitter.py [LIST_OF_LANGS] [LIST_OF_PORTS]
# Splits a rainbow MT packet into individual languages , outputting on ports
import sys
import math
import socket

args = sys.argv[1:]
half = len(args) // 2
langs = args[:half]
ports = map(lambda x: int(x), args[half:])

sockets = {}

for lang, port in zip(langs, ports):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    s.connect(("127.0.0.1", port))
    sockets[lang] = s

for line in sys.stdin:
    timestamp = " ".join(line.split(" ")[:2])
    packets = line.split("\t")
    packets[0] = packets[0].split(" ")[2] # Strip the timestamp from the first column
    pairs = zip(packets[0::2], packets[1::2])
    for lang, sentence in pairs:
        if lang in langs:
            print(sentence)
            sockets[lang].send(f"{timestamp} {sentence}\n".encode())