from pipeliner import Pipeliner

# Assume the pwd directory contains the elitr-testset directory
# The pwd dir is the one bind-mounted to the container
TESTSET_LOCATION = "./pwd"

p = Pipeliner(logsDir="/pwd/logs")

# Define the pipeline, the "useless" component is not going to be evaluated
start = p.addLocalNode("start", {"start_input": "stdin"}, {"start_output": "stdout"}, 'tr "[:lower:]" "[:upper:]"')
finish = p.addLocalNode("finish", {"finish_input": "stdin"}, {"finish_output": "stdout"}, "cat")
useless = p.addLocalNode("useless", {"in": "stdin"}, {}, "NOT USED")
p.addSimpleEdge(start, finish)
p.addSimpleEdge(finish, useless)

# Specify the component to evaluate
p.addComponent("exampleComponent", start, "start_input", finish, "finish_output", "./example_index", "mt")
# Create the directory structure at hostDirectory
p.createEvaluations(hostDirectory="./pwd/evaluation", containerDirectory="/pwd/evaluation", testsetDirectory=TESTSET_LOCATION)

    



    

