import logging
import os
import traceback

from dotenv import load_dotenv

load_dotenv()

from models import IPAddress, Domain
from services import select_system
from exceptions import ExternalError

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)


def add_ips(
    domain: str,
    ip_list: list,
    host_system: str,
    user: str,
    token: str,
):
    logger.info(f'Adding IPs for domain {domain}')

    domain_item = Domain.get('SENDING_DOMAIN', domain)

    for ip in ip_list:
        item = IPAddress.get('IPADDRESS', ip)
        if item.host_system != host_system:
            raise ExternalError(f'{ip} belongs to {item.host_system}, not {host_system}')

    try:
        system = select_system(host_system)
        system.add_ip_to_domain(domain_item, ip_list, user)
        system.update_universe_ip(token, ip_list)

        logger.info(f'Successfully added {ip_list} for {domain}')

    except Exception as e:
        logger.error(f"Failed adding {ip_list} for {domain}: {e}")
        logger.error(traceback.format_exc())
        raise


def main():
    add_ips(
        domain="navegamail.es",
        ip_list=["45.81.231.158"],
        host_system="Charon",
        user="loan.nguyen@audienceserv.com",
        token=os.environ["UNIVERSE_TOKEN"],
    )


if __name__ == '__main__':
    main()
