import logging
import os
import traceback

from dotenv import load_dotenv

load_dotenv()

from models import Domain
from services import select_system

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)


def deactivate_ips(
    domain: str,
    ip_list: list,
    host_system: str,
    user: str,
    token: str,
):
    logger.info(f'Deactivating IPs {ip_list} for domain {domain}')

    domain_item = Domain.get('SENDING_DOMAIN', domain)

    try:
        system = select_system(host_system)
        for ip in ip_list:
            system.deactivate_ip(domain_item, ip, user)

        system.update_universe_ip(token, ip_list, status='un-assign')

        logger.info(f'Successfully deactivated {ip_list} for {domain}')

    except Exception as e:
        logger.error(f"Failed deactivating {ip_list} for {domain}: {e}")
        logger.error(traceback.format_exc())
        raise


def main():
    deactivate_ips(
        domain="noticiasdirectas.com",
        ip_list=["45.81.231.158"],
        host_system="Charon",
        user="loan.nguyen@audienceserv.com",
        token=os.environ["UNIVERSE_TOKEN"],
    )


if __name__ == '__main__':
    main()
