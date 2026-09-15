import argparse
import ipaddress
import os

SYSTEMS = ['Pluto', 'Charon']

CLICK_IPS = {'Pluto': '193.107.76.2', 'Charon': '45.81.231.2'}


def ip_address(value):
    try:
        ipaddress.ip_address(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f'{value} is not a valid IP address')
    return value


def click_ip_for(sending_system):
    return CLICK_IPS[sending_system]


def build_parser(description, ips='optional'):
    """Build a parser carrying the arguments every setup script shares.

    ips: 'required' for at least one, 'optional' to default to [], 'none' to omit.
    """
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('--domain', required=True,
                        help='sending domain, e.g. example.com')
    parser.add_argument('--system', required=True, choices=SYSTEMS,
                        help='mail system hosting the domain')
    parser.add_argument('--user', default=os.getenv('OPERATOR_EMAIL'),
                        help='operator email recorded as last_modified_by (default: $OPERATOR_EMAIL)')

    if ips != 'none':
        parser.add_argument('--ips', metavar='IP', type=ip_address, default=[],
                            nargs='+' if ips == 'required' else '*',
                            required=ips == 'required',
                            help='space-separated IP addresses')

    return parser


def parse_args(parser):
    args = parser.parse_args()
    if not args.user:
        parser.error('--user is required, or set OPERATOR_EMAIL in .env')
    return args
