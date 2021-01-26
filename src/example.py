from pipeliner import Pipeliner

p = Pipeliner()

uppercaser = p.addLocalNode("uppercaser", {"rawText": "stdin"}, {"uppercased": "stdout"}, "tr [:lower:] [:upper:]")
logger = p.addLocalNode("logger", {"toBeLogged": "stdin"}, {}, "cat >/tmp/saved.txt")
p.addEdge(uppercaser, "uppercased", logger, "toBeLogged")
logger2 = p.addLocalNode("logger2", {"toBeLogged": "stdin"}, {}, "cat >/tmp/saved2.txt")
p.addEdge(uppercaser, "uppercased", logger2, "toBeLogged")

p.createPipeline()