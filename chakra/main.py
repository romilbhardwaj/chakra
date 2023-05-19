# Script to launch Chakra scheduler
import argparse
import json
import logging
from chakra.scheduler import ChakraScheduler
from chakra import policies

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG, #CRITICAL or INFO
                    format='%(asctime)s | %(levelname)-6s | %(name)-40s || %(message)s',
                    datefmt='%m-%d %H:%M:%S'
                    )

SUPPORTED_POLICIES = {
    'random': policies.RandomPolicy,
    'binpack': policies.BestfitBinpackPolicy
}

if __name__ == '__main__':
    # Parse arguments
    parser = argparse.ArgumentParser(description='Chakra scheduler')
    parser.add_argument('--policy', type=str, default='random',
                        help=f'Policy to use. Currently supported - {str(list(SUPPORTED_POLICIES.keys()))}')
    parser.add_argument('--policy-args', type=str, default='',
                        help='JSON kwargs to pass to the policy. Example - \'{"arg1": "val1", "arg2": "val2"}\'')
    parser.add_argument('--kubeconfig', type=str, default='',
                        help='Path to kubeconfig file. If not specified, tries to use incluster config')
    args = parser.parse_args()

    # Create policy
    if args.policy not in SUPPORTED_POLICIES:
        raise ValueError(f'Policy {args.policy} not supported. Currently supported - {str(list(SUPPORTED_POLICIES.keys()))}')
    logger.info(f'Using policy {args.policy} with args {args.policy_args}')
    # Parse policy args
    policy_args = {}
    if args.policy_args:
        policy_args = json.loads(args.policy_args)
    policy = SUPPORTED_POLICIES[args.policy](**policy_args)
    kube_config_path = args.kubeconfig
    if kube_config_path:
        logger.info(f'Using kubeconfig at {kube_config_path}')
    else:
        logger.info('Using in-cluster auth.')
    c = ChakraScheduler(kube_config_path=kube_config_path, policy=policy)
    c.run()