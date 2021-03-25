#!/usr/bin/python3
import networkx as nx
import SLTev.index_parser as index_parser
import psutil
import socket
import os
import time
import copy
import subprocess
import shutil
import matplotlib.pyplot as plt
from functools import reduce
from collections import Counter
from datetime import datetime

# Used for transferring data between stdout and stdins
AVAILABLE_PORTS = list(range(9000, 9999))

# Enable TICK-stack based metrics of all pipes
METRICS = False

# Because Python does not have a default function for list flattening
flatten = lambda t: [item for sublist in t for item in sublist]

class Pipeline:
  def __init__(self, graph, logsDir):
    self.graph = graph
    self._unbuffered = "stdbuf -oL "
    self._timestampFormat = "[%Y-%m-%d %H:%M:%S]"
    self._monitoringPorts = {}
    self.logsDir = logsDir
  
  # Wait for the port to open, before actually connecting to it.
  def _netcat(self, port):
    return f"(while ! ss -lt | grep -q 127.0.0.1:{port}; do sleep 1; done; nc -q 1 localhost {port})"

  # Without the -k flag, nc will exit after being probed by another nc with -z flag.
  def _netcatListen(self, port):
    return f"nc -lk localhost {port}"

  # Redirect tee's stdout to /dev/null, or it's going to pollute the console
  def _splitOutputs(self, portsTo):
    return reduce(lambda acc,port: acc + f">{self._netcat(port)} ", portsTo, f"tee ") + "1>/dev/null"
  
  # If an output is consumed by more than one input, the output needs to be duplicated that many times using tee
  # Similarly, if an output is also an input (in case of ports), a proxy port needs to be used to allow output duplicating
  def _createProxies(self):
    proxies = []
    for node in nx.topological_sort(self.graph):
      
      inputTypes = flatten(node.ingress.values())
      # Check the count of outgoing edges from the outputs of the node
      for oc in Counter([edge[2]["info"]["from"] for edge in self.graph.out_edges(node, data=True)]).items():
        outputName, count = oc
        outputType = node.egress[outputName][0]
        
        # The output is also an input (a socket is both receiving data and sending processed data)
        # Create a proxy port for that input
        if outputType in inputTypes:
          proxyOutputPorts = [AVAILABLE_PORTS.pop() for x in range(count)]
          proxyInputPort = AVAILABLE_PORTS.pop()
          node.egress[outputName] = proxyOutputPorts
          inputName = next((x for x in node.ingress.keys() if outputType in node.ingress[x]))
          node.ingress[inputName] = [proxyInputPort]
          proxies.append(f"{self._netcatListen(proxyInputPort)} | {self._netcat(outputType)} | {self._splitOutputs(proxyOutputPorts)}")
        # Split the output; stdout is handled in _executeLocalResources
        elif count > 1 and outputType != "stdout":
          proxyOutputPorts = [AVAILABLE_PORTS.pop() for x in range(count)]
          node.egress[outputName] = proxyOutputPorts
          proxies.append(f"{self._netcatListen(outputType)} | {self._splitOutputs(proxyOutputPorts)}")

    return proxies

  # Prepare commands for starting LocalResources. Two things need to be handled:
  # 1. Input, if the LocalResource is listening on stdin. Create a port that will forward data to stdin
  # 2. Output, if the LocalResource is outputting to stdout. Capture stdout with a pipe and create sockets for output.
  def _executeLocalResources(self):
    commands = []
    for node in [n for n in nx.topological_sort(self.graph)]:
      command = ""

      # Set up a proxy port and feed it to stdin
      if node.stdinName:
        stdinPort = AVAILABLE_PORTS.pop()
        node.ingress[node.stdinName] = [stdinPort]
        command += f"{self._netcatListen(stdinPort)} | "
      # Don't buffer the component's output
      command += self._unbuffered + node.code

      # Redirect stderr to a subshell to add timestamps
      command += f" 2> >(ts '{self._timestampFormat}' > {self.logsDir}/{node.label}-{node.name}.err)"

      edgesFromStdout = [edge for edge in self.graph.out_edges(node, data=True) if edge[2]["info"]["from"] == node.stdoutName]
      if len(edgesFromStdout) > 0:
        stdoutPorts = [AVAILABLE_PORTS.pop() for e in edgesFromStdout]
        node.egress[node.stdoutName] = stdoutPorts
        command += f" | {self._splitOutputs(stdoutPorts)}"
      
      commands.append(command)
    return commands

  # Print out entrypoints (nodes that have stdin inputs, but no incoming edges)
  def _reportEntrypoints(self):
    entrypoints = []
    for node in self.graph.nodes:
      if self.graph.in_degree(node) == 0 and self.graph.out_degree(node) > 0 and node.stdinName:
        entrypoints.append(f"# {node.name} entrypoint: {node.ingress[node.stdinName]}")
    return entrypoints

  def _sanityCheck(self):
    # Check if there are more than one edge to an ingress.
    # Consider using the octocat tool, if you need to connect more than one outputs to a single input
    for node in self.graph.nodes:
      if self.graph.in_degree(node) > 1:
        inEdges = self.graph.in_edges(node, data=True)
        edgeNames = set(map(lambda e: e[2]["info"]["to"], inEdges))
        if len(edgeNames) < self.graph.in_degree(node):
          raise Exception(f"Multiple incoming outputs: [{' '.join(edgeNames)}] to an input of node {node.name}. Did you mean to use octocat?")

  # Labels the nodes so their logs are roughly in the same order as the dataflow
  def _labelNodes(self):
    counter = 0
    for node in nx.topological_sort(self.graph):
      node.label = str(counter).zfill(2)
      counter += 1

  def _getMonitoringPorts(self):
    for node in self.graph.nodes:
      ports = []
      for ingress_ports in node.ingress.values():
        ports += ingress_ports
      for egress_ports in node.egress.values():
        ports += egress_ports
      self._monitoringPorts[node.name] = ports

  def _bashmonitor(self):
    monitoring = []
    monitoring.append("""
declare -A ports
red=`tput setaf 1`
green=`tput setaf 2`
reset=`tput sgr0`
    """)
    nodeNames = [f'"{node}"' for node in self._monitoringPorts.keys()]
    monitoring.append(f"nodeNames=({' '.join(nodeNames)})")
    for node, usedPorts in self._monitoringPorts.items():
      usedPorts = [str(port) for port in usedPorts]
      monitoring.append(f"ports[{node}]=\"{' '.join(usedPorts)}\"")

    monitoring.append("""
while true; do
  clear
  for name in "${nodeNames[@]}"; do
    echo $name
    p="${ports[$name]}"
    for port in $p; do
      if ss -lt | grep -q 127.0.0.1:$port; then
        echo "  $port ${green}RUNNING${reset}"
      else 
        echo "  $port ${red}FREE${reset}"
      fi 
    done
  done
  sleep 1
done
""")
    return monitoring

  # Create pipes between the components, as specified by the edges of the graph.
  def _createPipes(self):
    pipes = []
    for edge in self.graph.edges(data=True):
      edgeInfo = edge[2]["info"]
      edgeFrom = edgeInfo["from"]
      edgeTo = edgeInfo["to"]
      edgeName = edgeInfo["name"]
      edgeType = edgeInfo["type"]

      teeArgs = []
      logName = f"{self.logsDir}/l_{edge[0].label}-{edge[1].label}-{edgeInfo['name']}"
      if edgeType == "binary": # No timestamps
        teeArgs.append(f"{logName}.data ") 
      elif edgeType == "text": # Timestamp each line
        teeArgs.append(f">(ts '{self._timestampFormat}' > {logName}.log)") 
      elif edgeType == "none":
        teeArgs.append(f"{logName}.log")
      if METRICS:
        teeArgs.append(f">(python3 ./metrics.py {edgeName})")

      portFrom = edge[0].egress[edgeFrom].pop()
      portTo = edge[1].ingress[edgeTo].pop()
      if len(teeArgs) > 0:
        pipes.append(f"{self._netcatListen(portFrom)} | tee {' '.join(teeArgs)} | {self._netcat(portTo)}")
      else:
        pipes.append(f"{self._netcatListen(portFrom)} | {self._netcat(portTo)}")

    return pipes

  # Catch SIGINT and properly terminate all children.
  def _prologue(self):
    return [
      """trap "trap - SIGTERM && kill -- -$$" SIGINT SIGTERM EXIT""",
      """DATE=$(date '+%Y%m%d-%H%M%S')""",
      f"mkdir -p {self.logsDir}"""
    ]

  # Generate a bash pipeline for connecting all of the components
  def createPipeline(self, mode="tail"):
    if mode not in ["tail", "monitor", None]:
      raise Exception(f"Unsupported pipeline mode: ${mode}")

    self._sanityCheck()
    self._labelNodes()
    commands = []
    commands += self._createProxies()
    commands += self._executeLocalResources()
    self._getMonitoringPorts()
    commands += self._createPipes()

    allCommands = [(" &\n".join(commands)  + " &")]
    allCommands += self._prologue()
    allCommands += self._reportEntrypoints()

    allCommands.append(f"cp $0 {self.logsDir}") # make a copy of the script
    allCommands.append(f"( echo Last started pipeline was: > INFO ; echo Container: $(hostname) >> INFO; echo Logdir: {self.logsDir} >> INFO )")
    allCommands.append(f"echo Container $(hostname) is starting, follow logs: {self.logsDir} >&2")
    if mode == "monitor":
      allCommands += self._bashmonitor()
    elif mode == "tail":
      componentCount = len(self.graph.nodes)
      allCommands.append(f"if [ \"$1\" == '--silent' ]; then tail -f /dev/null; else tail -F -n {componentCount} {self.logsDir}/*.err; fi")
    return allCommands

class Pipeliner:
  def __init__(self, logsDir="/dev/null", availablePorts=AVAILABLE_PORTS):
    self.graph = nx.MultiDiGraph()
    self.resources = {}
    self.logsDir = logsDir if logsDir == "/dev/null" else logsDir + "/$DATE"
    self.metrics = False
    self._label = ""
    self._monitoringPorts = {}
    self._components = []

  class Node:
    def __init__(self, name, ingress, egress):
      if len(ingress.items()) == 0 and len(egress.items()) == 0:
        raise Exception(f"Node {name} does not have any input or output.")
      self.name = name
      self.ingress = {key: [val] for key,val in ingress.items()}
      self.stdinName = next((k for k,v in ingress.items() if v == "stdin"), None)
      self.egress = {key: [val] for key, val in egress.items()}
      self.stdoutName = next((k for k,v in egress.items() if v == "stdout"), None)
  class Component:
    def __init__(self, name, sourceNode, sourceInput, targetNode, targetOutput, indexFile, type):
      self.name = name
      self.sourceNode = sourceNode
      self.sourceInput = sourceInput
      self.targetNode = targetNode
      self.targetOutput = targetOutput
      self.indexFile = indexFile
      self.type = type
  class LocalNode(Node):
    def __init__(self, outer_self, name, ingress, egress, code=None, do_format=False):
      super().__init__(name, ingress, egress)
      if do_format:
          # the code contains {...} variables, emulate f-string evaluation
          # on it
          # following https://stackoverflow.com/questions/55457543/trigger-f-string-parse-on-python-string-in-variable
          # (I picked the simple and less controllable solution)
          self.code = eval(f'f{code!r}', outer_self.__dict__)
      else:
          # the code is finished, do not reinterpret it
          self.code = code

  def addLocalNode(self, name, ingress, egress, code, do_format=False):
    return self.LocalNode(self, name, ingress, egress, code, do_format)
      # we pass self to the constructor of LocalNode to allow do_format

  def addEdge(self, source, sourceOutput, target, targetInput, type="text"):
    if sourceOutput not in source.egress.keys():
      raise Exception(f"Node {source.name} does not have an output named {sourceOutput}")
    if targetInput not in target.ingress.keys():
      raise Exception(f"Node {target.name} does not have an input named {targetInput}")
    if type not in ["binary", "text", "none"]:
      raise Exception(f"Unsupported edge type: {type}")

    self.graph.add_edge(source, target, info={
      "from": sourceOutput,
      "to": targetInput,
      "name": f"{sourceOutput}2{targetInput}",
      "type": type
    })
  
  def addSimpleEdge(self, source, target, type="text"):
    if len(source.egress.keys()) > 1:
      raise Exception(f"Node {source.name} has more than one output. Use addEdge() and specify the output.")
    if len(target.ingress.keys()) > 1:
      raise Exception(f"Node {target.name} has more than one input. Use addEdge() and specify the input.")
    
    sourceOutput = list(source.egress.keys())[0]
    targetInput = list(target.ingress.keys())[0]
    self.addEdge(source, sourceOutput, target, targetInput, type=type)
  
  def addComponent(self, name, sourceNode, sourceInput, targetNode, targetOutput, indexFile, type):
    if type not in ["asr", "mt", "smt"]:
      raise Exception(f"Component {name} has unsupported type: {type}")
    self._components.append(self.Component(name, sourceNode, sourceInput, targetNode, targetOutput, indexFile, type))


  def createEvaluations(self, hostDirectory, containerDirectory, testsetDirectory):
    for component in self._components:

      evaluationDicts = index_parser.parseIndexFile(component.indexFile, testsetDirectory)
      for evaluationDict in evaluationDicts:

        # Create the directory for the file to be evaluated
        sourceFileName = os.path.basename(evaluationDict["SRC"])
        hostEvaluationPath = f"{hostDirectory}/{component.name}/{sourceFileName}"
        os.makedirs(hostEvaluationPath, exist_ok=True)

        # Copy the files
        for name, path in evaluationDict.items():
          shutil.copy(path, f"{hostEvaluationPath}/{name}")
          shutil.copy(path, f"{hostEvaluationPath}/{name}")

      
        entryNode = self.addLocalNode(f"fileInputNode-{sourceFileName}", {}, {"fileOutput": "stdout"}, f"cat ./SRC")
        self.graph.add_edge(entryNode, component.sourceNode, info={
          "from": "fileOutput",
          "to": component.sourceInput,
          "name": f"SRC2{component.sourceInput}",
          "type": "text"
        })
        exitNode = self.addLocalNode(f"exitNode-{sourceFileName}", {"output": "stdin"}, {}, f"cat > ./RES")
        self.graph.add_edge(component.targetNode, exitNode, info={
          "from": component.targetOutput,
          "to": "output",
          "name": f"{component.targetOutput}2RES",
          "type": "text"
        })
        path = nx.algorithms.shortest_path(self.graph, entryNode, exitNode)

        # Location of the files in the container (bindmounted dir location)
        containerEvaluationPath = f"{containerDirectory}/{component.name}/{sourceFileName}"
        pipeline = Pipeline(copy.deepcopy(self.graph.subgraph(path)), containerEvaluationPath)
        commands = pipeline.createPipeline(mode=None)
        commands.append("""
while :; do
  lastModificationSeconds=$(date +%s -r RESULT)
  currentSeconds=$(date +%s)
  elapsedSeconds=$((currentSeconds - lastModificationSeconds))
  if (( elapsedSeconds > 30 )); then
    echo "30 seconds from last write to the result file, shutting down in 30 seconds..."
    sleep 30
    kill -SIGINT $$
  fi
done
        """)
        with open(f"{hostEvaluationPath}/pipeline.sh", "w+") as pipeline:
          pipeline.writelines([c + "\n" for c in commands])
      
  def createPipeline(self, mode):
    pipeline = Pipeline(copy.deepcopy(self.graph), self.logsDir)
    commands = pipeline.createPipeline()
    for command in commands:
      print(command)

  def draw(self):
    plt.subplot()
    pos = nx.spring_layout(self.graph)
    labels = {node: node.name for node in self.graph.nodes}
    nx.draw(self.graph, pos, labels=labels, with_labels=True, arrowsize=30, font_size=20)
    nx.draw_networkx_edge_labels(self.graph, pos)
    plt.show()
