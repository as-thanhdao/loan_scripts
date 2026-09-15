import logging
import datetime as dt
import os

from dotenv import load_dotenv

load_dotenv()

from pynamodb.exceptions import PutError

from models import Domain
from utils import build_parser, click_ip_for, parse_args

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

CONTACT_ID = os.getenv('CONTACT_ID', '567605')


def create_domain(
    sending_domain: str,
    sending_domain_id: str,
    sending_system: str,
    geo: str,
    user: str,
    model_throttling_id: str,
    ip_list: list = None,
    force: bool = False,
):
    logger.info(f'Creating domain {sending_domain}...')

    domain = Domain()
    domain.SK = sending_domain
    domain.sending_domain_id = sending_domain_id
    domain.sending_system = sending_system
    domain.geo = geo
    domain.click_ip = click_ip_for(sending_system)
    domain.ip_list = ip_list or []
    domain.model_throttling_id = str(model_throttling_id)
    domain.status = 'UNUSED'
    domain.registrant = CONTACT_ID
    domain.admin = CONTACT_ID
    domain.tech = CONTACT_ID
    domain.billing = CONTACT_ID
    domain.last_modified_by = user
    domain.created_at = dt.datetime.utcnow()

    # save() replaces the whole item, so refuse to clobber a domain that is
    # already set up unless the caller explicitly asked for it.
    try:
        domain.save(condition=None if force else Domain.SK.does_not_exist())
    except PutError as e:
        if 'ConditionalCheckFailed' in str(e):
            raise SystemExit(
                f'{sending_domain} already exists. Check its status first, '
                f'then pass --force to overwrite the record.'
            )
        raise

    logger.info(f'Domain {sending_domain} created with status UNUSED')


def main():
    parser = build_parser('Create a new sending domain record in DynamoDB')
    parser.add_argument('--domain-id', required=True,
                        help='sending_domain_id from the registrar')
    parser.add_argument('--geo', required=True, help='geo code, e.g. ES')
    parser.add_argument('--throttling-id', default='4', help='model throttling id (default: 4)')
    parser.add_argument('--force', action='store_true',
                        help='overwrite the record if the domain already exists')
    args = parse_args(parser)

    create_domain(
        sending_domain=args.domain,
        sending_domain_id=args.domain_id,
        sending_system=args.system,
        geo=args.geo,
        user=args.user,
        model_throttling_id=args.throttling_id,
        ip_list=args.ips,
        force=args.force,
    )


if __name__ == '__main__':
    main()
