import logging
import os
import traceback

from dotenv import load_dotenv

load_dotenv()

from models import Domain, IPAddress
from services import select_system
from exceptions import ExternalError
from utils import build_parser, parse_args

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)


def set_up_domain(
    sending_domain: str,
    sending_system: str,
    ip_list: list,
    geo: str,
    user: str,
    model_throttling_id: str,
    token: str,
):
    logger.info('Setting up domain...')

    click_ip = '193.107.76.2' if sending_system == 'Pluto' else '45.81.231.2'

    for ip in ip_list:
        ip_item = IPAddress.get('IPADDRESS', ip)
        if ip_item.host_system != sending_system:
            raise ExternalError(
                f"{ip} belongs to {ip_item.host_system}, not {sending_system}"
            )

    domain = Domain.get('SENDING_DOMAIN', sending_domain)

    actions = [
        Domain.sending_system.set(sending_system),
        Domain.ip_list.set(ip_list),
        Domain.geo.set(geo),
        Domain.status.set('SETUP_PENDING'),
        Domain.click_ip.set(click_ip),
        Domain.last_modified_by.set(user),
        Domain.model_throttling_id.set(str(model_throttling_id)),
        Domain.failed_reason.remove(),
    ]

    domain.update(actions=actions)

    try:
        system = select_system(sending_system)

        if sending_system in ['Pluto', 'Charon'] and ip_list:
            system.setup_sending_ip_addresses(
                domain.sending_domain,
                domain.sending_domain_id,
                ip_list,
                domain.throttling_id,
                user,
                str(model_throttling_id),
            )

        system.add_domain(domain.sending_domain)
        system.add_required_pluto_setup(domain.sending_domain, geo, f'click.{domain.sending_domain}')
        system.add_unique_records(domain.sending_domain_id, domain.sending_domain)
        system.setup_click_record(domain.sending_domain_id, f'click.{domain.sending_domain}', click_ip)
        system.add_default_records(domain.sending_domain_id, domain.sending_domain, sending_system)
        system.update_universe_ip(token, ip_list)

        domain.update(actions=[Domain.status.set('USED')])

        logger.info(f"Successfully set up {domain.sending_domain}")

    except Exception as e:
        domain.update(actions=[
            Domain.failed_reason.set(str(e)),
            Domain.status.set('SETUP_FAILED'),
        ])
        logger.error(f"{domain.sending_domain} setup failed: {e}")
        logger.error(traceback.format_exc())
        raise


def main():
    parser = build_parser('Set up an existing UNUSED domain: DNS records, click host and sending IPs')
    parser.add_argument('--geo', required=True, help='geo code, e.g. ES')
    parser.add_argument('--throttling-id', default='4', help='model throttling id (default: 4)')
    args = parse_args(parser)

    set_up_domain(
        sending_domain=args.domain,
        sending_system=args.system,
        ip_list=args.ips,
        geo=args.geo,
        user=args.user,
        model_throttling_id=args.throttling_id,
        token=os.environ["UNIVERSE_TOKEN"],
    )


if __name__ == '__main__':
    main()
