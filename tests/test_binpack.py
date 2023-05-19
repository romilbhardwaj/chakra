import pytest
from kubernetes.client.models import V1Pod, V1PodSpec, V1Container, V1ResourceRequirements

from chakra.policies import BestfitBinpackPolicy


def create_pod(cpu_request):
    """Helper function to create a pod with a specific cpu request."""
    return V1Pod(
        spec=V1PodSpec(
            containers=[
                V1Container(
                    name="test-container",
                    resources=V1ResourceRequirements(
                        requests={
                            "cpu": cpu_request
                        }
                    )
                )
            ]
        )
    )

def test_best_fit_allocation():
    policy = BestfitBinpackPolicy('cpu')
    cluster_state = {
        'node1': {'cpu': 3.0, 'mem': 1024, 'nvidia.com/gpu': 0},
        'node2': {'cpu': 2.5, 'mem': 2048, 'nvidia.com/gpu': 0},
        'node3': {'cpu': 2.6, 'mem': 1024, 'nvidia.com/gpu': 0},
    }

    # The best fit for a 2.0 CPU request is node2, because it leaves the least amount of CPU remaining
    pod = create_pod(2.0)
    assert policy.get_allocation(cluster_state, pod) == 'node2'

def test_no_suitable_node():
    policy = BestfitBinpackPolicy('cpu')
    cluster_state = {
        'node1': {'cpu': 1.0, 'mem': 1024, 'nvidia.com/gpu': 0},
        'node2': {'cpu': 1.0, 'mem': 2048, 'nvidia.com/gpu': 0},
        'node3': {'cpu': 1.0, 'mem': 1024, 'nvidia.com/gpu': 0},
    }

    # If the pod requests more resources than any node can provide, the policy should raise an exception
    pod = create_pod(2.0)
    with pytest.raises(Exception) as e:
        policy.get_allocation(cluster_state, pod)
    assert str(e.value) == 'No node has enough resources to fit the pod'


def test_fallback_to_cpu_allocation():
    policy = BestfitBinpackPolicy('nvidia.com/gpu')
    cluster_state = {
        'node1': {'cpu': 3.0, 'mem': 1024, 'nvidia.com/gpu': 0},
        'node2': {'cpu': 2.5, 'mem': 2048, 'nvidia.com/gpu': 0},
        'node3': {'cpu': 2.6, 'mem': 1024, 'nvidia.com/gpu': 0},
    }

    # The pod does not request 'nvidia.com/gpu', so the policy should fallback to 'cpu'
    # The best fit for a 2.0 CPU request is node2, because it leaves the least amount of CPU remaining
    pod = create_pod(2.0)
    assert policy.get_allocation(cluster_state, pod) == 'node2'


def test_no_cpu_request():
    policy = BestfitBinpackPolicy('nvidia.com/gpu')
    cluster_state = {
        'node1': {'cpu': 1.0, 'mem': 1024, 'nvidia.com/gpu': 0},
        'node2': {'cpu': 1.0, 'mem': 2048, 'nvidia.com/gpu': 0},
        'node3': {'cpu': 1.0, 'mem': 1024, 'nvidia.com/gpu': 0},
    }

    # If the pod does not request either 'nvidia.com/gpu' or 'cpu', the policy should raise an exception
    pod = V1Pod(
        spec=V1PodSpec(
            containers=[
                V1Container(
                    name="test-container",
                    resources=V1ResourceRequirements(
                        requests={
                            "mem": 512
                        }
                    )
                )
            ]
        )
    )

    with pytest.raises(Exception) as e:
        policy.get_allocation(cluster_state, pod)
    assert str(e.value) == 'Pod does not have a resource request for cpu'
