import os

from .set_up_class import SetUpClass

SYSTEM_HOSTS = {'Pluto': 'plutomailsystem', 'Charon': 'charonmail'}


def _require(name):
    try:
        return os.environ[name]
    except KeyError:
        raise SystemExit(f'{name} is missing from .env')


def select_system(sending_system):
    if sending_system not in SYSTEM_HOSTS:
        raise SystemExit(f'Unknown sending system: {sending_system}')

    system_cred = (_require(f'{sending_system.upper()}_USERNAME'),
                   _require(f'{sending_system.upper()}_PASSWORD'))

    # Route53 runs on the karma account, which is not the one PynamoDB picks up
    # from the boto3 chain for DynamoDB -- keep the two sets of keys apart.
    return SetUpClass(system_cred, SYSTEM_HOSTS[sending_system],
                      _require('INWX_USERNAME'), _require('INWX_PASSWORD'),
                      _require('KARMA_AWS_ACCESS_KEY_ID'),
                      _require('KARMA_AWS_SECRET_ACCESS_KEY'))
