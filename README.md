# Chakra
Chakra is a highly customizable Kubernetes scheduler that makes Kubernetes schedule jobs as _you_ want them to be scheduled.

The goal of Chakra is ease of use and flexibility. It is not designed for performance, and is not suitable for production use.

Currently supported policies:
* Random
* Best Fit Binpacking

## Usage
Chakra runs as a deployment inside your Kubernetes cluster. It watches all pod that have pod.spec.schedulerName set to `chakra`, and schedules them according to the chosen policy.

To use Chakra:
1. Launch the Chakra deployment
```console
# Setup permissions
kubectl apply -f chakra_admin.yaml
# You can configure the policy being deployed by editing chakra.yaml
kubectl apply -f chakra.yaml
```

2. Submit pods with `pod.spec.schedulerName` set to `chakra`
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nginx
spec:
  template:
    spec:
      schedulerName: chakra # <--- This is critical! This is how the pod is assigned to Chakra for scheduling.
      containers:
        ...
```

3. Check logs with `kubectl logs -f chakra-<pod-id>`


## Developer Notes
### Setting up your debug cluster
```console
cd tests

# Create a 3 node kind cluster
kind create cluster --config kind-cluster.yaml

# Add fake GPU resources to these nodes:
python add_gpus_kind.py

# Now you can experimeent with this cluster by submitting nginx pods with schedulerName set to chakra. This yaml also uses the fake GPUs.
kubectl apply -f nginx.yaml
```

### Running Chakra outside of Kubernetes
You can also run Chakra outside of Kubernetes using `--kubeconfig` flag to point to a kubeconfig file. This is useful for development and debugging.
```console
# Random policy
python3 -m chakra.main --policy random --kubeconfig ~/.kube/config

# Binpacking policy
python3 -m chakra.main --policy binpack --policy-args '{"binpacking_resource": "cpu"}' --kubeconfig ~/.kube/config
```

## Adding your own Policy
Take a look at chakra/policies.py. You'll need to inherit from `BaseClass` and implement the `get_allocation` method.

## Known issues
* When the cluster is full and a resource frees up, chakra does not reschedule pending pods onto the freed up resources. This is because the watch doesn't get triggered. This is to be fixed by making the loop not wait on watch and instead also look at pending pods. 