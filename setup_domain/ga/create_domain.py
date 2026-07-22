import argparse
import logging
import datetime as dt

from dotenv import load_dotenv

load_dotenv()

from models import Domain

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

CONTACT_ID = '567605'


def create_domain():
    sending_domain = 'marchionews.com'
    sending_domain_id = 'e40a688e60db6a659433e87f84863016'
    sending_system = 'Charon'
    geo = 'IT'
    user = 'loan.nguyen@audienceserv.com'
    click_ip = '45.81.231.2'
    model_throttling_id = '4'
    now = dt.datetime.utcnow()

    logger.info(f'Creating domain {sending_domain}...')

    domain = Domain()
    domain.SK = sending_domain
    domain.sending_domain_id = sending_domain_id
    domain.sending_system = sending_system
    domain.geo = geo
    domain.click_ip = click_ip
    domain.ip_list = []
    domain.model_throttling_id = model_throttling_id
    domain.status = 'UNUSED'
    domain.registrant = CONTACT_ID
    domain.admin = CONTACT_ID
    domain.tech = CONTACT_ID
    domain.billing = CONTACT_ID
    domain.last_modified_by = user
    domain.created_at = now

    domain.save()

    logger.info(f'Domain {sending_domain} created with status UNUSED')


if __name__ == '__main__':
    create_domain()
