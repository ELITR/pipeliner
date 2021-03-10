#!/usr/bin/python3
import networkx as nx
import psutil
import socket
import os
import time
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

class Pipeliner:
  def __init__(self, logsDir="/dev/null", availablePorts=AVAILABLE_PORTS):
    self.graph = nx.MultiDiGraph()
    self.resources = {}
    self.logsDir = logsDir if logsDir == "/dev/null" else logsDir + "/$DATE"
    self.metrics = False
    # List of ports that are guaranteed to be available on the machine
    self.availablePorts = availablePorts
    self._unbuffered = "stdbuf -oL "
    self._timestampFormat = "[%Y-%m-%d %H:%M:%S]"
    self._label = ""
    self._monitoringPorts = {}

  class Node:
    def __init__(self, name, ingress, egress):
      if len(ingress.items()) == 0 and len(egress.items()) == 0:
        raise Exception(f"Node {name} does not have any input or output.")
      self.name = name
      self.ingress = {key: [val] for key,val in ingress.items()}
      self.stdinName = next((k for k,v in ingress.items() if v == "stdin"), None)
      self.egress = {key: [val] for key, val in egress.items()}
      self.stdoutName = next((k for k,v in egress.items() if v == "stdout"), None)

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

  # Wait for the port to open, before actually connecting to it.
  def _netcat(self, port):
    return f"(while ! nc -z localhost {port}; do sleep 1; done; nc localhost {port})"

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
          proxyOutputPorts = [self.availablePorts.pop() for x in range(count)]
          proxyInputPort = self.availablePorts.pop()
          node.egress[outputName] = proxyOutputPorts
          inputName = next((x for x in node.ingress.keys() if outputType in node.ingress[x]))
          node.ingress[inputName] = [proxyInputPort]
          proxies.append(f"{self._netcatListen(proxyInputPort)} | {self._netcat(outputType)} | {self._splitOutputs(proxyOutputPorts)}")
        # Split the output; stdout is handled in _executeLocalResources
        elif count > 1 and outputType != "stdout":
          proxyOutputPorts = [self.availablePorts.pop() for x in range(count)]
          node.egress[outputName] = proxyOutputPorts
          proxies.append(f"{self._netcatListen(outputType)} | {self._splitOutputs(proxyOutputPorts)}")

    return proxies

  # Prepare commands for starting LocalResources. Two things need to be handled:
  # 1. Input, if the LocalResource is listening on stdin. Create a port that will forward data to stdin
  # 2. Output, if the LocalResource is outputting to stdout. Capture stdout with a pipe and create sockets for output.
  def _executeLocalResources(self):
    commands = []
    for node in [n for n in nx.topological_sort(self.graph) if isinstance(n, self.LocalNode)]:
      command = ""

      # Set up a proxy port and feed it to stdin
      if node.stdinName:
        stdinPort = self.availablePorts.pop()
        node.ingress[node.stdinName] = [stdinPort]
        command += f"{self._netcatListen(stdinPort)} | "
      # Don't buffer the component's output
      command += self._unbuffered + node.code

      # Redirect stderr to a subshell to add timestamps
      command += f" 2> >(ts '{self._timestampFormat}' > {self.logsDir}/{node.label}-{node.name}.err)"

      edgesFromStdout = [edge for edge in self.graph.out_edges(node, data=True) if edge[2]["info"]["from"] == node.stdoutName]
      if len(edgesFromStdout) > 0:
        stdoutPorts = [self.availablePorts.pop() for e in edgesFromStdout]
        node.egress[node.stdoutName] = stdoutPorts
        command += f" | {self._splitOutputs(stdoutPorts)}"
      
      commands.append(command)
    return commands

  # Print out entrypoints (nodes that have stdin inputs, but no incoming edges)
  def _reportEntrypoints(self):
    for node in self.graph.nodes:
      if self.graph.in_degree(node) == 0 and self.graph.out_degree(node) > 0 and node.stdinName:
        print(f"# {node.name} entrypoint: {node.ingress[node.stdinName]}")

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

  # TODO: Not working properly!
  def _bashmonitor(self):
    print("""
declare -A ports
red=`tput setaf 1`
green=`tput setaf 2`
reset=`tput sgr0`
    """)
    nodeNames = [f'"{node}"' for node in self._monitoringPorts.keys()]
    print(f"nodeNames=({' '.join(nodeNames)})")
    for node, usedPorts in self._monitoringPorts.items():
      usedPorts = [str(port) for port in usedPorts]
      print(f"ports[{node}]=\"{' '.join(usedPorts)}\"")

    print("""
while true; do
  clear
  for name in "${nodeNames[@]}"; do
    echo $name
    p="${ports[$name]}"
    for port in $p; do
      if nc -z -w 1 localhost $port; then
        echo "  $port ${green}RUNNING${reset}"
      else 
        echo "  $port ${red}FREE${reset}"
      fi 
    done
  done
  sleep 1
done
""")


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
      if len(teeArgs) > 0:
        pipes.append(f"{self._netcatListen(edge[0].egress[edgeFrom].pop())} | tee {' '.join(teeArgs)} | {self._netcat(edge[1].ingress[edgeTo].pop())}")
      else:
        pipes.append(f"{self._netcatListen(edge[0].egress[edgeFrom].pop())} | {self._netcat(edge[1].ingress[edgeTo].pop())}")
    return pipes

  # Catch SIGINT and properly terminate all children.
  def _prologue(self):
    print(f"""DATE=$(date '+%Y%m%d-%H%M%S')
mkdir -p {self.logsDir}
      """)

  # Generate a bash pipeline for connecting all of the components
  def createPipeline(self, test=False):

    self._sanityCheck()
    self._labelNodes()
    commands = []
    commands += self._createProxies()
    commands += self._executeLocalResources()
    self._getMonitoringPorts()
    commands += self._createPipes()

    componentCount = len(self.graph.nodes)
    self._prologue()
    self._reportEntrypoints()

    print(" &\n".join(commands)  + " &")
    print(f"cp $0 {self.logsDir}") # make a copy of the script
    print(f"( echo Last started pipeline was: > INFO ; echo Container: $(hostname) >> INFO; echo Logdir: {self.logsDir} >> INFO )")
    print(f"echo Container $(hostname) is starting, follow logs: {self.logsDir} >&2")
    if test:
      self._bashmonitor()
    else:
      print(f"if [ \"$1\" == '--silent' ]; then tail -f /dev/null; else tail -F -n {componentCount} {self.logsDir}/*.err; fi")
   
  def draw(self):
    plt.subplot()
    pos = nx.spring_layout(self.graph)
    labels = {node: node.name for node in self.graph.nodes}
    nx.draw(self.graph, pos, labels=labels, with_labels=True, arrowsize=30, font_size=20)
    nx.draw_networkx_edge_labels(self.graph, pos)
    plt.show()
