import sys
from pyvis.network import Network
import json

if len(sys.argv) < 2:
    sys.stdout.write("Usage: python3 visualize.py [networkSimulationFile.json]\n")
    exit()

net = Network(height="100vh", width="100%", bgcolor="#ffffff", font_color="white", notebook=False)

# parse configuration details
netJsonFile = open(sys.argv[1], 'r')
netJson = json.load(netJsonFile)

# parse and create hosts
X=0
for host in netJson["hosts"]:
	net.add_node(host, y=3000, x=X, shape='box', color='blue', fixed=True)
	X += 100

# parse and create switches
X_t = 100
X_a = 100
X_c = 400
for switch in netJson["switches"]:
	if switch[0] == 't':
		net.add_node(switch, y=2800, x=X_t, shape='box', color='red', fixed=True)
		X_t += 300
	elif switch[0] == 'a':
		net.add_node(switch, y=2600, x=X_a, shape='box', color='green', fixed=True)
		X_a += 300
	else:
		net.add_node(switch, y=0, x=X_c, shape='box', color='orange', fixed=True)
		X_c += 600

# parse and create links
for addr1, addr2, p1, p2 in netJson["links"]:
	if addr1[0] == 'h' and addr2[0] == 't':
		net.add_edge(addr1, addr2)
	elif addr1[0] == 't' and addr2[0] == 'h':
		net.add_edge(addr2, addr1)
	elif addr1[0] == 't' and addr2[0] == 'a':
		net.add_edge(addr1, addr2)
	elif addr1[0] == 'a' and addr2[0] == 't':
		net.add_edge(addr2, addr1)
	elif addr1[0] == 'a' and addr2[0] == 'c':
		net.add_edge(addr1, addr2)
	elif addr1[0] == 'c' and addr2[0] == 'a':
		net.add_edge(addr2, addr1)
	else:
		net.add_edge(addr1, addr2)

netJsonFile.close()

net.save_graph("topology.html")

