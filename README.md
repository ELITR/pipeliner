# Overview
This repository contains tools to create and execute a *pipeline* -- various components, such as ASR, MT and many other processing and monitoring utilities, all connected to each other. Typical use cases are deployment for a given event, or evaluation of different components. The generated pipeline is a `bash` script that heavily utilizes `netcat`, using localhost ports and `tee` for the data flow.

## Requirements + installation
- Python 3
- networkx 
- (optional, for visualization) matplotlib
- SLTev installed (when using component evaluation)
- `ss` command (located in `iproute2` package)

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

## From Pipelines to Directed Acyclic Graphs

Pipeliner allows to construct complex setups, beyond a linear chain of producers and consumers.

### Pipeline Forking

Suppose we want to add another logger. Simply create another node and edge, and the `Pipeliner` will automatically "fork" the pipeline and send the data to all paths.

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

### Pipeline Merging

The converse of forking is merging, taking multiple inputs and producing a single output.

Specifying such a merge at the level of the abstract pipeline is easy, simply list multiple items in the Ingress list of a node (one of them can be ``stdin``, others have to be ports).

Unlike forking, which can be done simply by duplicating the content, merging requires application-dependent logic, so the code you implement has to somehow handle the more incoming streams. It is up to the provided code to ensure correct data processing including the avoidance of deadlocks.

We provide an example of pipeline merging using a simple tool ``octocat.py`` which is included with `Pipeliner` in ``src/``. Octocat is a manually-controlled `cat`, which allows to dynamically switch the input stream while the pipeline is running. ``src/octocat-sample-dir/README.md`` contains a guide how to work with octocat.

Octocat is line-oriented.

The manual steering happens in an "octocat directory" where the input streams get printed to "preview" files, and by writing the name of one of the streams, the user can select which of them should be passed to the output at any point in time.

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

## Free ports
If you need to grab a port that is guaranteed to be free, use the `AVAILABLE_PORTS` global variable in the `pipeliner` script.

```python
from pipeliner import AVAILABLE_PORTS
free_port = AVAILABLE_PORTS.pop()
```

## Visualization
To see a (bit crude) visualization of the created graph, use `p.draw` (make sure you got `matplotlib` installed).

## Usage for ELITR deployment
Typically, this tool is used together with other ELITR tools, such as `online-text-flow`. The `cruise-control` repository contains a Dockerfile you can use to have an image with all the tools built. Then, you can use the `docker-compose.yaml` file, start up a `cruise-control` container and execute the bash script generated by the pipeliner there. This has the advantage of the container having "clean" network, so you don't have to worry about the ports not being available. Make sure you have the directory with logs and all scripts you want to run bind-mounted.

You will need to open some ports to the container, to provide input(s) to the pipeline. I usually do this setup (with having the port 5000 open):
```python
audioRecording = p.addLocalNode("audioRecording", {}, {"audiorecord": "stdout"}, "nc -lk 5000")
```
and then from the host machine, run `arecord -f S16_LE -c1 -r 16000 -t raw -D default | nc localhost 5000`, which transmits the audio to the container. One upside of this port-based approach is you can start and stop the `arecord` without bringing the whole pipeline down. 

# Evaluation
Pipeliner supports evaluation of parts of the pipeline using SLTev. A part of a pipeline that is evaluated is called a `component`. First, specify the components you want to evaluate. Provide the start node (the one consuming the input) and the end node (the one outputting the results to be evaluated), along with the input and output names. Specify the path to the index file, and the type of the component (`slt, mt, asr`). The type determines how the resulting files are going to be evaluated with SLTev. See the full example in the `examples/` directory.

```python
p.addComponent(componentName, startNode, inputName, endNode, outputName, indexFile, type)
```

Once all components are added, the following command will prepare the files for evaluation. 

```python
p.createEvaluations(hostDirectory, containerDirectory, testsetDirectory)
```

- `hostDirectory` is the folder on the host where the directories for evaluation purposes are going to be generated. Each component will get it's folder and each file in the corresponding index file will also get it's folder.
- `containerDirectory` is where the hostDirectory is bind-mounted to the container. This is so the pipeline script knows where to store log files for the pipeline execution.
- `testsetDirectory` is the base location of the path the index file refers to. For example, SLTEv index files look like this: `elitr-testset/documents/wmt18-newstest-sample-read`. `testsetDirectory` would then be a folder containing the `elitr-testset` folder on the host.

If the pipelines won't be executed in the container, simply set the `containerDirectory` to the same value as the `hostDirectory`. 

Each final folder (of a file of a component) will contain `SRC`, `REF` and `pipeline.sh` files, and possibly some other files used for the evaluation. The `pipeline.sh` is a pipeline that stores the results of processing the `SRC` file  to a `RES` file.

## Running on cluster
`qruncmd` (from https://github.com/ufal/ufal-tools) is a tool to execute multiple jobs in parallel on the UFAL cluster. Run the following command and substitute `<MAX_JOBS>` for the count of maximum jobs that can be ran at once (typically limited by a worker on Mediator). Run the command in the dir where the pipelines are generated (typically `containerDirectory`), or change the `find` command appropriately.

`find ~+ -name pipeline.sh | qruncmd --jobs=<MAX_JOBS> --split-to-size=1 --logdir=<LOG_DIR> bash`

Make sure your `PATH` contains all of the tools used in the pipeline -- this usually means having the `ebclient` to connect to the mediator. You can use Vojtech's virtualenv that has all the Python tools needed to execute the pipeliner: `source /home/srdecny/personal_work_ms/evaluation/.venv/bin/activate`. 

If you don't want to receive emails when a job crashes, use this parameter: `--sge-flags="-m n"`.

## Pipeline termination
Currently, the pipeline watches the `OUT` file and when it hasn't been modified for 30 seconds, it waits for another 30 seconds and then terminates the pipeline. This mechanism is not final and it's certainly possible the numbers are wrong.

# Development
There's a `docker-compose.yaml` file included in the repo intended for developmental work. It's main use is to bind-mount the Python scripts to the cruise-control image, so the compiled tools are available for debugging when developing.

# Monitoring
The `src/monitor.py` script accepts paths to files to be monitored. It displays size of the files, last modification time and the average time between modifications. It shows whether or not the file has been "recently" modified, where recently is with respect to the average time. It's purpose is to measure the log files generated by the pipeline, so the pipeline operator is able to monitor the data flow in the pipeline and see which parts are up and running and which parts are struggling.

The `src/pids.py` does the same thing but for `*.pid` files generated by the pipeline that contain pids of the components of the pipeline.
# TODO (documentation)
- metrics
- stderr output
- kill all workers on exit
- component evaluation

# TODO (code)
- nodes import+exporting.
