#!/usr/bin/python3
import networkx as nx
from functools import reduce
import matplotlib.pyplot as plt
from collections import Counter
from datetime import datetime

# Used for transferring data between stdout and stdins
AVAILABLE_PORTS = list(range(9100, 9200))

# Enable TICK-stack based metrics of all pipes
METRICS = False

# Because Python does not have a default function for list flattening
flatten = lambda t: [item for sublist in t for item in sublist]

class Pipeliner:
  def __init__(self, logsDir="/dev/null", availablePorts=list(range(9100,9200))):
    self.graph = nx.MultiDiGraph()
    self.resources = {}
    self.logsDir = logsDir if logsDir == "/dev/null" else logsDir + "/$DATE"
    self.metrics = False
    # List of ports that are guaranteed to be available on the machine
    self.availablePorts = availablePorts
    self._unbuffered = "stdbuf -oL "

  class Node:
    def __init__(self, name, ingress, egress):
      self.name = name
      self.ingress = {key: [val] for key,val in ingress.items()}
      self.stdinName = next((k for k,v in ingress.items() if v == "stdin"), None)
      self.egress = {key: [val] for key, val in egress.items()}
      self.stdoutName = next((k for k,v in egress.items() if v == "stdout"), None)

  class DockerNode(Node):
    def __init__(self, name, ingress, egress, composeDefinition=None):
      super().__init__(name, ingress, egress)
      self.composeDefinition = composeDefinition

  class LocalNode(Node):
    def __init__(self, name, ingress, egress, code=None):
      super().__init__(name, ingress, egress)
      self.code = code

  def addDockerNode(self, name, ingress, egress, composeDefinition=None):
    return self.DockerNode(name, ingress, egress, composeDefinition)

  def addLocalNode(self, name, ingress, egress, code):
    return self.LocalNode(name, ingress, egress, code)

  def addEdge(self, source, sourceOutput, target, targetInput, isLogged=False):
    if sourceOutput not in source.egress.keys():
      raise Exception(f"Node {source.name} does not have an output named {sourceOutput}")
    if targetInput not in target.ingress.keys():
      raise Exception(f"Node {target.name} does not have an input named {targetInput}")

    self.graph.add_edge(source, target, info={
      "from": sourceOutput,
      "to": targetInput,
      "name": f"{sourceOutput}2{targetInput}"
    })

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

    return proxies

  # Prepare commands for starting LocalResources. Two things need to be handled:
  # 1. Input, if the LocalResource is listening on stdin. Create a port that will forward data to stdin
  # 2. Output, if the LocalResource is outputting to stdout. Capture stdout with a pipe and create sockets for output.
  def _executeLocalResources(self):
    commands = []
    for node in [n for n in nx.topological_sort(self.graph) if isinstance(n, self.LocalNode)]:
      command = ""
      
      if node.stdinName:
        stdinPort = self.availablePorts.pop()
        node.ingress[node.stdinName] = [stdinPort]
        command += f"{self._netcatListen(stdinPort)} | "

      # Don't buffer the componen'ts output.
      command += self._unbuffered + node.code

      command += f" 2>{self.logsDir}/{node.name}.err"

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

  # Create pipes between the components, as specified by the edges of the graph.
  def _createPipes(self):
    pipes = []
    for edge in self.graph.edges(data=True):
      edgeInfo = edge[2]["info"]
      edgeFrom = edgeInfo["from"]
      edgeTo = edgeInfo["to"]
      edgeName = edgeInfo["name"]

      teeArgs = []
      teeArgs.append(f"{self.logsDir}/{edgeInfo['name']}.log ") 
      if METRICS:
        teeArgs.append(f">(python3 ./metrics.py {edgeName})")
      if len(teeArgs) > 0:
        pipes.append(f"{self._netcatListen(edge[0].egress[edgeFrom].pop())} | tee {' '.join(teeArgs)} | {self._netcat(edge[1].ingress[edgeTo].pop())}")
      else:
        pipes.append(f"{self._netcatListen(edge[0].egress[edgeFrom].pop())} | {self._netcat(edge[1].ingress[edgeTo].pop())}")
    return pipes

  # Catch SIGINT and properly terminate all children.
  def _prologue(self):
    print("""handler()
  {
      pkill -TERM -P $$
  }
trap handler SIGINT
    """)
    print(f"""DATE=$(date '+%Y-%m-%d-%H:%M:%S')
mkdir -p {self.logsDir}/$DATE
      """)

  # Generate a bash pipeline for connecting all of the components
  def createPipeline(self):

    commands = []
    commands += self._createProxies()
    commands += self._executeLocalResources()
    commands += self._createPipes()

    componentCount = len(self.graph.nodes)
    commands += [f"tail -F -n {componentCount} {self.logsDir}/*.err"]
    self._prologue()
    self._reportEntrypoints()
    print(" &\n".join(commands))
    
  def draw(self):
    plt.subplot()
    pos = nx.spring_layout(self.graph)
    labels = {node: node.name for node in self.graph.nodes}
    nx.draw(self.graph, pos, labels=labels, with_labels=True, arrowsize=30, font_size=20)
    nx.draw_networkx_edge_labels(self.graph, pos)
    plt.show()

  def generateDockerCompose(self):
    compose = """
version: "3.8"
services:
    """
    for resource in filter(lambda r: isinstance(r, self.DockerNode), self.resources.values()):
      compose += resource.composeDefinition
    return compose
