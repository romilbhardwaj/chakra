# The main Chakra scheduler class. This class is responsible for scheduling pods to nodes.

import json
import logging
import re
import threading
import time
from collections import deque
from typing import Optional, Dict

from kubernetes.client import V1Pod

from chakra.policies import BasePolicy

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG, #CRITICAL or INFO
                    format='%(asctime)s | %(levelname)-6s | %(name)-40s || %(message)s',
                    datefmt='%m-%d %H:%M:%S'
                    )

from kubernetes import client, config, watch
from chakra import constants, policies

client.rest.logger.setLevel(logging.WARNING)

class ClusterStateUpdater(threading.Thread):
    """
    Thread to update the cluster state periodically.
    """

    PRINT_FREQUENCY = 5 # Seconds between printing cluster state
    def __init__(self, chakra_obj, kubecoreapi, namespace):
        super().__init__()
        self.chakra_obj = chakra_obj
        self.kubecoreapi = kubecoreapi
        self.namespace = namespace
        self.daemon = True
        self.last_print_time = 0


    def run(self):
        while True:
            cluster_state = self.get_cluster_state()
            self.chakra_obj.set_cluster_state(cluster_state)
            # If more time has passed than the print frequency, print the cluster state
            if time.time() - self.last_print_time > self.PRINT_FREQUENCY:
                logger.info(f'Cluster state: {str(cluster_state)}')
                self.last_print_time = time.time()

    @staticmethod
    def parse_resource_cpu(resource_str):
        """ Parse CPU string to cpu count. """
        unit_map = {'m': 1e-3, 'K': 1e3}
        value = re.search(r'\d+', resource_str).group()
        unit = resource_str[len(value):]
        return float(value) * unit_map.get(unit, 1)

    @staticmethod
    def parse_resource_memory(resource_str):
        """ Parse resource string to megabytes. """
        unit_map = {'Ki': 2 ** 10, 'Mi': 2 ** 20, 'Gi': 2 ** 30, 'Ti': 2 ** 40}
        value = re.search(r'\d+', resource_str).group()
        unit = resource_str[len(value):]
        return float(value) * unit_map.get(unit, 1) / (
                    2 ** 20)  # Convert to megabytes

    def get_cluster_state(self) -> Dict[str, Dict[str, int]]:
        """ Get allocatable resources per node. """
        # Get the nodes and running pods

        limit = None
        continue_token = ""
        nodes, _, _ = self.kubecoreapi.list_node_with_http_info(limit=limit,
                                                            _continue=continue_token)
        pods, _, _ = self.kubecoreapi.list_pod_for_all_namespaces_with_http_info(
            limit=limit, _continue=continue_token)

        nodes = nodes.items
        pods = pods.items

        available_resources = {}
        running_pods = set()

        for node in nodes:
            name = node.metadata.name
            total_cpu = self.parse_resource_cpu(node.status.allocatable['cpu'])
            total_memory = self.parse_resource_memory(
                node.status.allocatable['memory'])
            total_gpu = int(node.status.allocatable.get('nvidia.com/gpu', 0))

            used_cpu = 0
            used_memory = 0
            used_gpu = 0

            for pod in pods:
                if pod.spec.node_name == name and pod.status.phase in ['Running', 'Pending'] and pod.metadata.namespace == 'default':
                    running_pods.add(pod.metadata.name)
                    for container in pod.spec.containers:
                        if container.resources.requests:
                            used_cpu += self.parse_resource_cpu(
                                container.resources.requests.get('cpu', '0m'))
                            used_memory += self.parse_resource_memory(
                                container.resources.requests.get('memory',
                                                                 '0Mi'))
                            used_gpu += int(container.resources.requests.get(
                                'nvidia.com/gpu', 0))

            available_cpu = total_cpu - used_cpu
            available_memory = total_memory - used_memory
            available_gpu = total_gpu - used_gpu

            available_resources[name] = {
                'cpu': available_cpu,
                'memory': available_memory,
                'gpu': available_gpu
            }
        return available_resources


class ChakraScheduler:
    """
    The main Chakra scheduler class. This class watches cluster state and schedules pods to nodes.
    """
    def __init__(self,
                 kube_config_path: str = '',
                 policy: Optional[BasePolicy] = None,
                 namespace: str = 'default'):
        self.kube_config_path = kube_config_path
        logger.info('Using policy %s' % str(policy))
        self.policy = policy
        self.namespace = namespace

        if self.kube_config_path:
            logger.info(f'Initializing Scheduler with kube config path {str(self.kube_config_path)}')
            config.load_kube_config(config_file=self.kube_config_path)
        else:
            logger.info('Using in-cluster auth.')
            try:
                config.load_incluster_config()
            except config.config_exception.ConfigException:
                logger.error('Failed to load in-cluster config.')
                raise
        self.kubecoreapi = client.CoreV1Api()
        self.scheduler_name = constants.SCHEDULER_NAME
        logger.info('Scheduler Pre-init done.')
        self.cluster_state = None # Dictionary containing the current state of the cluster. Structure is {node_name: {cpu: float, mem: float, gpu: float}}

        # Run a thread to periodically fetch current state of the cluster and update the cluster state.
        self.cluster_state_updater = ClusterStateUpdater(self, self.kubecoreapi, self.namespace)
        self.cluster_state_updater.start()

    def set_cluster_state(self, cluster_state: Dict):
        # Called by the ClusterStateUpdater thread.
        self.cluster_state = cluster_state

    def scheduler(self, name, node):
        logger.info('Scheduling object %s on node %s.' % (str(name), str(node)))

        target = client.V1ObjectReference()
        target.kind = 'Node'
        target.apiVersion = 'v1'
        target.name = node

        meta = client.V1ObjectMeta()
        meta.name = name

        body = client.V1Binding(metadata=meta, target=target)

        result = False
        try:
            result = self.kubecoreapi.create_namespaced_binding(self.namespace, body)
        except ValueError as e: #TODO(romilb): Hack till kub-python fixes their api.
            if str(e) != 'Invalid value for `target`, must not be `None`':
                raise
            else:
                logger.info('Recieved response from API, but no target value... ignoring exception.')
        return result

    def process_event(self, event: Dict):
        """
        Processes the event and schedules the job.
        :param event: Dict containing 'object', 'raw_object'. 'object' is the V1Pod object and 'raw_object' is the raw json object.
        :return: None if the event was scheduled, else the event object.
        """
        pod: V1Pod = event['object']
        try:
            logger.info('Trying to schedule pod %s' % pod.metadata.name)
            try:
                allotted_node_name = self.policy.get_allocation(self.cluster_state, pod)
                logger.info(
                    'Got allocation node - %s' % str(allotted_node_name))
            except Exception as e:
                logger.exception(
                    'Unable to allocate %s: %s, adding it back to the wait queue.' % (pod.metadata.name, str(e)))
                return event
            res = self.scheduler(pod.metadata.name,
                                 allotted_node_name)
        except client.rest.ApiException as e:
            logger.warning('API Exception - %s' % str(json.loads(e.body)['message']))


    def run(self):

        # Wait for cluster state to be populated once before starting the scheduler.
        while self.cluster_state is None:
            logger.info('Waiting for cluster state to be populated.')
            time.sleep(1)
        logger.info('Cluster state populated, starting scheduler.')
        w = watch.Watch()
        logger.info('Watch initialized')
        waiting_objects = deque()   # This queue maintains list of jobs that were not scheduled due to unavailable machines. This list maintains priority order and tries to schedule waiting jobs every time kubernetes state updates.
        for new_event in w.stream(self.kubecoreapi.list_namespaced_pod, self.namespace):
            logger.info('Recieved object %s and event type %s, adding to wait queue.' % (new_event['object'].metadata.name, new_event['type']))
            waiting_objects.append(new_event)
            num_waiting = len(waiting_objects)
            logger.info('Current k8s scheduler wait queue length = %d' % num_waiting)
            for i in range(0, num_waiting):
                event = waiting_objects.popleft()
                if event['object'].status.phase == 'Pending' and event['object'].spec.node_name == None and event['object'].spec.scheduler_name == self.scheduler_name:
                    ret = self.process_event(event)
                    if ret:
                        # Event was returned, so it was not scheduled. Add it back to the queue.
                        waiting_objects.append(ret)
                else:
                    # limit output size to 100 chars
                    logger.info(f'Ignoring event {event["type"]} for pod {event["object"].metadata.name}')
                    pass
