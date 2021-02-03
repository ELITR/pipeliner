#!/usr/bin/python3
'''
ASR can produce output in a .ctm format (hypothesis about the current audio). 
This script converts the .ctm input (on stdin) to a segmented output, ready to be consumed by online-text-flow-events.
Usage: ./python3 ctm_segmenter.py
'''
import sys
from math import trunc

hypothesis = []
hypothesisStart = 0.0
hypothesisEnd = 0.0

# "for line in sys.stdin" is buffered and will not read/write smoothly
# https://stackoverflow.com/a/18235323/
while True:
    line = sys.stdin.readline()
    if line.startswith("#") or not line:
        if len(hypothesis) > 0:
            print(f"0 {trunc(hypothesisEnd * 10)} {' '.join(hypothesis)}", flush=True)
        hypothesis = []
        if line:
            continue
        else:
            exit(0)
    # Line format:
    # conv 1 3.79 0.23 they -1.00
    _, _, start, end, word, _ = line.split()

    if len(hypothesis) == 0:
        hypothesisStart = float(start)
    hypothesisEnd = float(start) + float(end)
    # Ignore non-word tokens like <sil>
    if not word.startswith("<"):
        hypothesis.append(word)
    


