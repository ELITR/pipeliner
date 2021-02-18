# Overview
This repository contains tools to create and execute a *pipeline* -- various components, such as ASR, MT and many other processing and monitoring utilities, all connected to each other. Typical use cases are deployment for a given event, or evaluation of different components. The generated pipeline is a `bash` script that heavily utilizes `netcat`, using localhost ports and `tee` for the data flow.

## Requirements + installation
- Python 3
- networkx 
- (optional, for visualization) matplotlib

`pip install -r requirements.txt`

Make sure the `AVAILABLE_PORTS` variable in `src/pipeliner.py` contains a list of unused ports on the machine where the pipeline will be executed.

## How it works
A pipeline is represented as a directed acyclic multigraph, whose vertices are individual components and edges are the connection between those components. Each component can have multiple inputs and multiple outputs. As mentioned before, almost all of the communication is done using localhost networking with ports. Each node gets assigned ports for it's inputs and outputs. For each outgoing edge from an output, that output gets a port. Similarly, each input also gets a port. The edges merely connect those assigned ports. This approach allows for easy debugging and logging by tapping into the connecting edge, where we can insert arbitrary tools, such as logging the traffic or measuring the throughput. 

First, import the `Pipeliner` class from `pipeliner.py` and instantiate it. The finished example script described in this section is located at `src/example.py`.

```python
from pipeliner import Pipeliner

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

When we create the pipeline with `p.createPipeline()` now, you'll see something like this printed out:

```bash
# uppercaser entrypoint: [9199]
nc -lk localhost 9199 | stdbuf -o0 tr [:lower:] [:upper:] | tee >(while ! nc -z localhost 9198; do sleep 1; done; nc localhost 9198) 1>/dev/null &
nc -lk localhost 9197 | stdbuf -o0 cat >/tmp/saved.txt &
nc -lk localhost 9198 | (while ! nc -z localhost 9197; do sleep 1; done; nc localhost 9197)
```

The first line tells us the entrypoint of the `uppercaser` component - a port number on localhost. On the second and third line our two components are executed, and the last line is the edge connecting those two components together. To try it out, save the input into `pipeline.sh`,execute the pipeline with `bash pipeline.sh` and connect to the `uppercaser`'s entrypoint with `nc localhost 9199`, while observing the log file with `tail -F /tmp/saved.txt`. Type something to the `nc` and you should see that text uppercased in the `tail`.

### Simple Edges
Because most of the edges are between vertices that have a single output and a single input, it can be a bit tedious to specify the name of the output and the input. In this case, you can use the `addSimpleEdge` syntax:
```python
# This is the same as p.addEdge(uppercaser, "uppercased", logger, "toBeLogged")
# Because uppercaser has only one output and logger has only one input
p.addSimpleEdge(uppercaser, logger)
```

## Forking

Suppose we want to add another logger. Simply create another node and edge, and the `Pipeliner` will automatically split the data.

```python
logger2 = p.addLocalNode("logger2", {"toBeLogged": "stdin"}, {}, "cat >/tmp/saved2.txt")
p.addEdge(uppercaser, "uppercased", logger2, "toBeLogged")
```

`createPipeline()` yields the following: 

```bash
# uppercaser entrypoint: [9199]
nc -lk localhost 9199 | stdbuf -o0 tr [:lower:] [:upper:] | tee >(while ! nc -z localhost 9198; do sleep 1; done; nc localhost 9198) >(while ! nc -z localhost 9197; do sleep 1; done; nc localhost 9197) 1>/dev/null &
nc -lk localhost 9196 | stdbuf -o0 cat >/tmp/saved2.txt &
nc -lk localhost 9195 | stdbuf -o0 cat >/tmp/saved.txt &
nc -lk localhost 9197 | (while ! nc -z localhost 9195; do sleep 1; done; nc localhost 9195) &
nc -lk localhost 9198 | (while ! nc -z localhost 9196; do sleep 1; done; nc localhost 9196)
```
Observe that the output of `tr` is captured to two ports, `9198` and `9197`, which are eventually connected to the loggers.


## Logging
To enable automated logging, first provide the directory where the logs should be stored to `Pipeliner`'s constructor (default is `/dev/null`, i.e. no logs). A subdirectory with the current timestamp will be created.

```python
p = Pipeliner(logsDir="./logs")
```

 The data flowing on all edges will also be captured to a file named `{outputName}2{inputName}.log` file in the specified logging folder.

By default, every edge is logged with timestamps per each row. To change this behavior, set the `type` parameter in the `addEdge()` function. Default value is `"text"`. Supported values:
- "none": No timestamps. Suffix: `log`
- "binary": No timestamps. Suffix: `.data`
- "text": Timestamps per row. Suffix: `.log`.

Stderr of each vertex is also captured by default. They're labeled in DFS-preorder order.

## Visualization
To see a (bit crude) visualization of the created graph, use `p.draw` (make sure you got `matplotlib` installed).

## Usage for ELITR deployment
Typically, this tool is used together with other ELITR tools, such as `online-text-flow`. The `cruise-control` repository contains a Dockerfile you can use to have an image with all the tools built. Then, you can use the `docker-compose.yaml` file, start up a `cruise-control` container and execute the bash script generated by the pipeliner there. This has the advantage of the container having "clean" network, so you don't have to worry about the ports not being available. Make sure you have the directory with logs and all scripts you want to run bind-mounted.

You will need to open some ports to the container, to provide input(s) to the pipeline. I usually do this setup (with having the port 5000 open):
```python
audioRecording = p.addLocalNode("audioRecording", {}, {"audiorecord": "stdout"}, "nc -lk 5000")
```
and then from the host machine, run `arecord -f S16_LE -c1 -r 16000 -t raw -D default | nc localhost 5000`, which transmits the audio to the container. One upside of this port-based approach is you can start and stop the `arecord` without bringing the whole pipeline down. 

# Development
There's a `docker-compose.yaml` file included in the repo intended for developmental work. It's main use is to bind-mount the Python scripts to the cruise-control image, so the compiled tools are available for debugging when developing.

# TODO (documentation)
- metrics
- stderr output
- kill all workers on exit

# TODO (code)
- crash on failure
- nodes import+exporting
