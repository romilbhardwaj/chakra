# Implements various Chakra policies for allocating jobs to nodes
import logging
from typing import Dict, Union

import random

from kubernetes.client import V1Pod

logger = logging.getLogger(__name__)

class BasePolicy:

    def __init__(self):
        pass

    def __repr__(self):
        return self.__class__.__name__

    def get_allocation(self,
                       cluster_state: Dict[str, Dict[str, Union[float, int]]],
                       pod: V1Pod) -> str:
        """
        Returns the name of the node to allocate the job to.

        Hint: Can access labels using event_obj.metadata.labels
        :param cluster_state: Dictionary containing the current state of the cluster. Structure is {node_name: {cpu: float, mem: float, nvidia.com/gpu: float}}
        :param pod: V1Pod object to be scheduled
        :return: Node name to allocate the pod to.
        """
        raise NotImplementedError


class RandomPolicy(BasePolicy):
    """Randomly allocates jobs to nodes. Does not check if the node has enough resources."""

    def __init__(self):
        pass

    def get_allocation(self,
                       cluster_state: Dict[str, Dict[str, Union[float, int]]],
                       pod: V1Pod) -> str:
        node_names = list(cluster_state.keys())
        return random.choice(node_names)

class BestfitBinpackPolicy(BasePolicy):
    """Allocates jobs to nodes based on best fit bin packing. Checks if the node has enough resources before allocating."""

    def __init__(self, binpacking_resource: str = 'cpu'):
        """

        :param binpacking_resource: Resource to binpack on. Can be 'cpu', 'memory', or 'nvidia.com/gpu'
        """
        if binpacking_resource not in ['cpu', 'memory', 'nvidia.com/gpu']:
            raise Exception(
                'Invalid binpacking resource. Must be one of cpu, memory, or nvidia.com/gpu'
            )
        self.binpacking_resource = binpacking_resource

    def get_allocation(self,
                       cluster_state: Dict[str, Dict[str, Union[float, int]]],
                       pod: V1Pod) -> str:
        """
        Returns the name of the node to allocate the job to.
        :param cluster_state: Dictionary containing the current state of the cluster. Structure is {node_name: {cpu: float, mem: float, nvidia.com/gpu: float}}
        :param pod: Kubernetes V1Pod object to be scheduled
        :return:
        """

        # Initially, use the binpacking_resource defined for the class
        binpacking_resource = self.binpacking_resource
        # Get the pod resource requirement
        if pod.spec.containers[0].resources and pod.spec.containers[0].resources.requests:
            pod_resource_req = pod.spec.containers[0].resources.requests.get(binpacking_resource)

        # Fall back to CPU if the specified binpacking resource is not requested by the pod
        if pod_resource_req is None:
            pod_resource_req = pod.spec.containers[0].resources.requests.get(
                'cpu')
            if pod_resource_req is None:
                raise Exception('Pod does not have a resource request for cpu')
            # Also fall back the binpacking resource to CPU for checking in the cluster_state
            logger.warning(f'Falling back to CPU since pod does not have a resource request for {binpacking_resource}')
            binpacking_resource = 'cpu'

        pod_resource_req = float(pod_resource_req)

        # Find the best fit node
        best_fit_node = None
        best_fit_node_remaining = None
        for node, resources in cluster_state.items():
            print(list(pod.spec.containers[0].resources.requests.keys()))
            if all(float(resources.get(resource, 0)) >= float(pod.spec.containers[0].resources.requests.get(resource, 0))
                   for resource in pod.spec.containers[0].resources.requests.keys()):
                remaining_resource = resources.get(binpacking_resource) - pod_resource_req
                if remaining_resource >= 0 and (best_fit_node is None or remaining_resource < best_fit_node_remaining):
                    best_fit_node = node
                    best_fit_node_remaining = remaining_resource

        if best_fit_node is None:
            raise Exception('No node has enough resources to fit the pod')

        return best_fit_node


