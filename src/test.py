import pickle

with open("/Users/sakthi.n/Documents/OpenSource/codetraverse/src/hypatia_graph.pkl", "rb") as f:
    g = pickle.load(f)

print(len(g.nodes()))

for node in g.nodes():
    if g.nodes[node].get("node_type") == "type":
        print(f"{g.nodes[node].get("name")} =>  {g.nodes[node].get('node_type')}")