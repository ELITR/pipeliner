from pipeliner import Pipeliner

p = Pipeliner()

uppercaser = p.addLocalNode("uppercaser", {"rawText": "stdin"}, {"uppercased": "stdout"}, "tr [:lower:] [:upper:]")
logger = p.addLocalNode("logger", {"toBeLogged": "stdin"}, {}, "cat >/tmp/saved.txt")
p.addEdge(uppercaser, "uppercased", logger, "toBeLogged")

p.createPipeline()