import logging
import requests

from models import IPAddress

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

UNIVERSE_HOST = 'https://universe.audienceserv.com/v1'


def ip_hostname_converter(ip_list):
    logger.info(f'Converting IP list: {ip_list} into workable dict')
    result = []
    for ip in ip_list:
        record_name = IPAddress.get('IPADDRESS', ip).smtp
        result.append({'record_name': record_name, 'value': [ip], 'type': 'A'})
    return result


def dmarc_generator(domain):
    dmarc = f'"v=DMARC1\; p=none\; pct=100\; rua=mailto:dmarc-reports@{domain}\;"'
    return dmarc


def update_universe_ip(token, data: dict):
    requests.post(url=f'{UNIVERSE_HOST}/ipaddress', headers={'x-access-token': token}, json=data)
