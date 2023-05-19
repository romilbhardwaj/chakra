# Patches the Kubernetes API to add fake nvidia.com/gpus to nodes. Run kubectl proxy in another window.
import subprocess

import kubernetes

NUM_GPUs = 4

kubernetes.config.load_kube_config()
client = kubernetes.client.CoreV1Api()

node_names = [node.metadata.name for node in client.list_node().items]

print("Make sure kubectl proxy is running in another terminal window.")

for node in node_names:
    print(f'Patching node {node}')

    curl_cmd = f"""curl --header "Content-Type: application/json-patch+json" --request PATCH --data '[{{"op": "add", "path": "/status/capacity/nvidia.com~1gpu", "value": "{NUM_GPUs}"}}]' http://localhost:8001/api/v1/nodes/{node}/status"""

    print(curl_cmd)
    subprocess.run(curl_cmd, shell=True)

print("Done patching nodes. Check with kubectl describe nodes | grep gpu")
