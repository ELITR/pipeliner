# Overview
This repository contains tools to create and execute a *pipeline* -- various components, such as ASR, MT and many other processing and monitoring utilities, all connected to each other. Typical use cases are deployment for a given event, or evaluation of different components. The generated pipeline is a `bash` script that heavily utilizes `netcat`, using localhost ports and `tee` for the data flow.

## Requirements + installation
- Python 3
- networkx 
- (optional, for visualization) matplotlib

`pip3 install -r requirements.txt`

## How it works
A pipeline is represented as a directed acyclic multigraph, whose vertices are individual components and edges are the connection between those components. Each component can have multiple inputs and multiple outputs. As mentioned before, almost all of the communication is done using localhost networking with ports. Each node gets assigned ports for it's inputs and outputs. For each outgoing edge from an output, that output gets a port. Similarly, each input also gets a port. The edges merely connect those assigned ports. This approach allows for easy debugging and logging by tapping into the connecting edge, where we can insert arbitrary tools, such as logging the traffic or measuring the throughput. 

First, import the `Pipeliner` class from `pipeliner.py` and instantiate it. The finished example script described in this section is located at `src/example.py`.

```python
import pipeliner from Pipeliner

p = Pipeliner()
```

Each component consists of four declarations:
 - Name (for logging purposes)
 - Ingress (component inputs represented as a dict)
 - Egress (component outputs represented as a dict)
 - Code (How to actually execute the component) 

### Ingress and Egress

The dicts consists of input/output *names* and their *types*. The output name is used to declare edges, for better readability. The type can be one of the following: `stdin`, `stdout` or a `port number`.

Let's add a simple component that accepts input on `stdin`, transforms the input to uppercase and outputs it on `stdout`.

```python
uppercaser = p.addLocalNode("uppercaser", {"rawText": "stdin"}, {"uppercased": "stdout", "tr [:lower:] [:upper:]"})
```

What happens when we try to execute it?

```python
p.createPipeline()
```

Nothing gets generated! This is because we didn't specify any edge from or to the resource. If no other component cares about our `uppercaser` node, why bother executing it? The solution is to add another node that will connect to our `uppercaser` node and will do something with it, such as save it to a file.

```python
logger = p.addLocalNode("logger", {"toBeLogged": "stdin"}, {}, "cat >/tmp/saved.txt")
```

Now, add an edge between those two components. We want to connect the `uppercaser`'s `uppercased` output to `logger`'s `toBeLogged` input.

```python
p.addEdge(uppercaser, "uppercased", logger, "toBeLogged")
```

When we create the pipeline with `createPipeline()` now, you'll see something like this printed out:

```bash
# uppercaser entrypoint: [9199]
nc -lk localhost 9199 | stdbuf -o0 tr [:lower:] [:upper:] | tee >(while ! nc -z localhost 9198; do sleep 1; done; nc localhost 9198) 1>/dev/null &
nc -lk localhost 9197 | stdbuf -o0 cat >/tmp/saved.txt &
nc -lk localhost 9198 | (while ! nc -z localhost 9197; do sleep 1; done; nc localhost 9197)
```

The first line tells us the entrypoint of the `uppercaser` component - a port number on localhost. On the second and third line our two components are executed, and the last line is the edge connecting those two components together. To try it out, save the input into `pipeline.sh`,execute the pipeline with `bash pipeline.sh` and connect to the `uppercaser`'s entrypoint with `nc localhost 9199`, while observing the log file with `tail -F /tmp/saved.txt`. Type something to the `nc` and you should see that text uppercased in the `tail`.

# TODO (documentation)
- docker nodes
- forking
- logging
- metrics

# TODO (code)
- crash on failure
- kill all processes on exiting