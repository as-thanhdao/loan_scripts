import logging
import datetime as dt
from typing import List

from .aws_class import Route53
from .cloudflare_class import Cloudflare
from .custom_classes import AwsRecord
from .inwx_class import INWX
from .ga_class import GAEngineAPI
from models import Domain, IPBlock, IPAddress
from utils import (dmarc_generator, ip_hostname_converter, get_ip_address_id, update_universe_ip)
from exceptions import ExternalError

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class SetUpClass():
    def __init__(self, api_cred: tuple, system_host: str, inwx_username: str, inwx_password: str,
                 aws_access_key_id: str, aws_secret_access_key: str):
        self.system = GAEngineAPI(api_cred, system_host)
        self.inwx = INWX(inwx_username, inwx_password)
        self.aws = Route53(aws_access_key_id, aws_secret_access_key)
        self.cloudflare = Cloudflare()

    def change_ip_hostdomain(self, domain: Domain, ptr_record_list: List[AwsRecord]):
        logger.info(f'Changing ip host domain of IPs to {domain.sending_domain} in PTR record')
        for data in ptr_record_list:
            smtp = data['record_name'].split('-')[0]
            item = IPBlock.get('PTR_RECORD', smtp)
            record_dict = {'record_name': data['value'][0].split('.')[-1] + '.' + item.ip_zone_name,
                           'type': 'PTR',
                           'value': [data['record_name'] + '.' + domain.sending_domain]}
            self.aws.change_domain_dns_records(item.hostzone_id, record_dict, action='UPSERT')

    def pluto_ip_create(self, host_domain: str, ip_items: list, throttling_id: int):
        logger.info('Creating new IP in Pluto')
        new_pluto_ids = []
        for ip_item in ip_items:
            host_record = ip_item.smtp + '.' + host_domain
            pluto_id = self.system.create_ip(ip_item.smtp, ip_item.ip_address, host_record, throttling_id)
            new_pluto_ids.append({'ip_address': ip_item.ip_address, 'pluto_id': pluto_id})
        return new_pluto_ids

    def pluto_ip_update(self, host_domain: str, ip_items: list, throttling_id: int):
        logger.info('Updating IP in Pluto')
        new_pluto_ids = []
        for ip_item in ip_items:
            host_record = ip_item.smtp + '.' + host_domain
            pluto_id = self.system.update_ip(ip_item.pluto_id, host_record, throttling_id)
            new_pluto_ids.append({'ip_address': ip_item.ip_address, 'pluto_id': pluto_id})
        return new_pluto_ids

    def create_domain_throttling_rule(self, sending_domain: str, rules: list):
        logger.info(f'Creating throttling rule on Pluto for {sending_domain}')
        result = self.system.create_throttling_template(sending_domain, rules)
        return result

    def setup_a_record(self, domain_id: str, domain: str, records: List[AwsRecord]):
        logger.info(f'Adding IP type A record...')
        for record in records:
            cloudflare_record = {
                'name': record['record_name'] + '.' + domain,
                'type': record['type'],
                'content': record['value'][0]
            }
            self.cloudflare.create_dns_record(domain_id, cloudflare_record)

    def delete_a_record(self, domain_item, ip_item):
        logger.info(f'Deleting A record of {ip_item.ip_address} from {domain_item.sending_domain}')
        record_name = f'{ip_item.smtp}.{domain_item.sending_domain}'
        records = self.cloudflare.list_dns_records_by_zone(domain_item.sending_domain_id)
        for record in records:
            if record['type'] == 'A' and record['name'] == record_name:
                self.cloudflare.delete_dns_record(domain_item.sending_domain_id, record['id'])

    def add_domain(self, domain):
        logger.info(f'Adding {domain} as an Incoming domain in Pluto Engine')
        item = Domain.get('SENDING_DOMAIN', domain)
        if item.domain_pluto_id:
            pass
        else:
            domain_create_res = self.system.create_domain(domain)
            item.update(actions=[
                Domain.domain_pluto_id.set(str(domain_create_res['data']['domain']['id']))
            ])

    def add_unique_records(self, domain_id: str, domain: str):
        logger.info(f'Adding dkim record...')
        item = Domain.get('SENDING_DOMAIN', domain)
        if item.dkim_pluto_id:
            pass
        else:
            unique_records = self.system.create_dkim_key(domain)
            dkim_record = unique_records['data']['dkim_key']['dns']['public_key']
            dkim_pluto_id = unique_records['data']['dkim_key']['id']
            record = {
                'name': dkim_record['name'],
                'type': 'TXT',
                'content': '"' + 'v=DKIM1; ' + f"{dkim_record['value']}" + '"'
            }
            self.cloudflare.create_dns_record(domain_id, record)
            item.update(actions=[
                Domain.dkim_pluto_id.set(str(dkim_pluto_id))
            ])
        logger.info(f'Adding dkim record succeeded')

    def setup_click_record(self, domain_id: str, domain: str, click_ip: str):
        logger.info(f'Adding click record...')
        record = {
            'name': domain,
            'type': 'A',
            'content': click_ip
        }
        self.cloudflare.create_dns_record(domain_id, record)
        logger.info(f'Adding click record succeeded')

    def add_default_records(self, domain_id: str, domain: str, system: str):
        logger.info(f'Adding default records (spf, mail and mx)...')
        spf_temp_list = []
        mail_ip = '193.107.76.1' if system == 'Pluto' else '45.81.231.1'
        for item in IPBlock.query(hash_key='PTR_RECORD', filter_condition=IPBlock.spf_block.startswith('ip')):
            spf_temp_list.append(item.spf_block)
        spf = {
            'name': domain,
            'type': 'TXT',
            'content': f'"v=spf1 {" ".join(spf_temp_list)} ~all"'
        }
        mail = {
            'name': f'mail.{domain}',
            'type': 'A',
            'content': mail_ip
        }
        dmarc = {
            'name': f'_dmarc.{domain}',
            'type': 'TXT',
            'content': dmarc_generator(domain)
        }
        mx = {
            'name': domain,
            'type': 'MX',
            'content': f'mail.{domain}',
            'priority': 10
        }
        spf_result = self.cloudflare.create_dns_record(domain_id, spf)
        mail_a_result = self.cloudflare.create_dns_record(domain_id, mail)
        dmarc_result = self.cloudflare.create_dns_record(domain_id, dmarc)
        mx_result = self.cloudflare.create_dns_record(domain_id, mx)
        logger.info(f'Adding default records succeeded')
        return spf_result, mail_a_result, dmarc_result, mx_result

    def add_required_pluto_setup(self, domain: str, geo: str, click_sub_domain: str):
        logger.info(f'Finishing remaining setups of {domain} on Pluto')
        item = Domain.get('SENDING_DOMAIN', domain)
        if item.url_pluto_id:
            pass
        else:
            forward_mailboxes = [
                {'local': 'dmarc_reports', 'forward_address': 'dmarc_reports@audienceserv.com'},
                {'local': 'feedbackloop', 'forward_address': 'feedbackloop@audienceserv.com'},
                {'local': 'postmaster', 'forward_address': 'feedbackloop@audienceserv.com'},
                {'local': 'reply', 'forward_address': 'kontakt@buncha.org'}
            ]
            spam_mailboxes = [
                {"local": "abuse"},
                {"local": "feedback"}
            ]
            self.system.create_forward_mailboxes(item.domain_pluto_id, forward_mailboxes)
            self.system.create_bounce_mailboxes(item.domain_pluto_id)
            self.system.create_spam_mailboxes(item.domain_pluto_id, spam_mailboxes)
            click_address = self.system.create_click_url(click_sub_domain)
            item.update(actions=[
                Domain.url_pluto_id.set(str(click_address['data']['url_domain']['id']))
            ])

    def setup_sending_ip_addresses(self,
                                   sending_domain: str,
                                   sending_domain_id: str,
                                   ip_list: list,
                                   throttling_id: str,
                                   last_modified_by: str,
                                   model_throttling_id: str):
        logger.info(f'Starting setups for domains')
        host_record_dict = ip_hostname_converter(ip_list)
        domain_item = Domain.get('SENDING_DOMAIN', sending_domain)

        ip_items = [IPAddress.get('IPADDRESS', ip) for ip in ip_list]

        if throttling_id:
            logger.info(f'Old throttling id detected: {throttling_id}')
            new_pluto_ips = []
            for ip_item in ip_items:
                if ip_item.pluto_id:
                    new_pluto_ips += self.pluto_ip_update(sending_domain, [ip_item], throttling_id)
                else:
                    new_pluto_ips += self.pluto_ip_create(sending_domain, [ip_item], throttling_id)
        else:
            default_rules = self.system.get_throttling_template_data(model_throttling_id)['data']['throttling_template']['rules']
            for data in default_rules:
                del data['id']
            new_throttling_id = self.create_domain_throttling_rule(sending_domain, default_rules)
            logger.info(f"New throttling ID is {new_throttling_id}")
            new_pluto_ips = []
            for ip_item in ip_items:
                if ip_item.pluto_id:
                    new_pluto_ips += self.pluto_ip_update(sending_domain, [ip_item], new_throttling_id)
                else:
                    new_pluto_ips += self.pluto_ip_create(sending_domain, [ip_item], new_throttling_id)
            domain_item.update(actions=[
                Domain.throttling_id.set(str(new_throttling_id))
            ])

        self.change_ip_hostdomain(domain_item, host_record_dict)
        self.setup_a_record(sending_domain_id, sending_domain, host_record_dict)
        new_ip_id_list = [ip['pluto_id'] for ip in new_pluto_ips]
        routing_rule_id = self.system.create_routing_rule(sending_domain, new_ip_id_list)
        domain_item.update(actions=[
            Domain.routing_id.set(str(routing_rule_id))
        ])
        for ip in new_pluto_ips:
            ip_item = IPAddress.get('IPADDRESS', ip['ip_address'])
            ip_item.update(actions=[
                IPAddress.pluto_id.set(str(ip['pluto_id'])),
                IPAddress.routing_ids.set([str(routing_rule_id)]),
                IPAddress.host_domain.set(sending_domain),
                IPAddress.last_status_switch.set(dt.datetime.now()),
                IPAddress.status.set('ACTIVE'),
                IPAddress.last_modified_by.set(last_modified_by)
            ])

    def add_ip_to_domain(self, domain_item, ip_list, user):
        throttling_id = domain_item.throttling_id
        routing_id = domain_item.routing_id
        sending_domain = domain_item.sending_domain
        sending_domain_id = domain_item.sending_domain_id
        host_record_dict = ip_hostname_converter(ip_list)

        ip_items = [IPAddress.get('IPADDRESS', ip) for ip in ip_list]

        logger.info(f'Creating IPs on Pluto with throttling rule {throttling_id}')
        new_pluto_ips = []
        for ip_item in ip_items:
            if ip_item.pluto_id:
                new_pluto_ips += self.pluto_ip_update(sending_domain, [ip_item], throttling_id)
            else:
                new_pluto_ips += self.pluto_ip_create(sending_domain, [ip_item], throttling_id)
        self.change_ip_hostdomain(domain_item, host_record_dict)
        self.setup_a_record(sending_domain_id, sending_domain, host_record_dict)

        new_ip_id_list = [ip['pluto_id'] for ip in new_pluto_ips] + get_ip_address_id(domain_item.ip_list)
        self.system.update_routing_rule(routing_id, new_ip_id_list)

        domain_item.update(actions=[
            Domain.ip_list.set(domain_item.ip_list + ip_list),
            Domain.last_modified_by.set(user),
        ])

        for ip in new_pluto_ips:
            ip_item = IPAddress.get('IPADDRESS', ip['ip_address'])
            ip_item.update(actions=[
                IPAddress.pluto_id.set(str(ip['pluto_id'])),
                IPAddress.routing_ids.set(ip_item.routing_ids + [str(routing_id)]),
                IPAddress.host_domain.set(sending_domain),
                IPAddress.last_status_switch.set(dt.datetime.now()),
                IPAddress.status.set('ACTIVE'),
                IPAddress.last_modified_by.set(user)
            ])

    def update_universe_ip(self, token, ips, status='assigned'):
        for ip in ips:
            ip_item = IPAddress.get('IPADDRESS', ip)
            data = {
                'ip_address': ip_item.SK,
                'mta_id': ip_item.pluto_id,
                'mta_name': ip_item.smtp,
                'host_name': ip_item.host_domain,
                'mailing_system': ip_item.host_system,
                'status': status
            }
            update_universe_ip(token, data)

    def delete_domain_pluto(self, domain):
        logger.info(f'Deleting {domain} from Pluto Engine')
        domain_item = Domain.get('SENDING_DOMAIN', domain)
        if domain_item.domain_pluto_id:
            self.system.delete_domain(domain_item.domain_pluto_id)
            domain_item.update(actions=[
                Domain.domain_pluto_id.remove()
            ])

    def delete_throttling_rule_pluto(self, domain):
        logger.info(f'Deleting {domain} throttling rule from Pluto Engine')
        domain_item = Domain.get('SENDING_DOMAIN', domain)
        if domain_item.throttling_id:
            self.system.delete_throttling_rule(domain_item.throttling_id)
            domain_item.update(actions=[
                Domain.throttling_id.remove()
            ])

    def delete_unique_record(self, domain):
        logger.info(f'Deleting {domain} unique id from Pluto Engine')
        domain_item = Domain.get('SENDING_DOMAIN', domain)
        if domain_item.dkim_pluto_id:
            self.system.delete_dkim(domain_item.dkim_pluto_id)
            domain_item.update(actions=[
                Domain.dkim_pluto_id.remove()
            ])

    def delete_pluto_url(self, domain):
        logger.info(f'Deleting {domain} url id from Pluto Engine')
        domain_item = Domain.get('SENDING_DOMAIN', domain)
        if domain_item.url_pluto_id:
            self.system.delete_url(domain_item.url_pluto_id)
            domain_item.update(actions=[
                Domain.url_pluto_id.remove()
            ])

    def deactivate_ip(self, domain_item, ip_address, user):
        logger.info(f'Deactivating {ip_address} from {domain_item.sending_domain}')

        ip_item = IPAddress.get('IPADDRESS', ip_address)
        remaining_ip_list = [ip for ip in domain_item.ip_list if ip != ip_address]

        if domain_item.routing_id:
            self.system.update_routing_rule(domain_item.routing_id, get_ip_address_id(remaining_ip_list))

        # self.system.delete_ip(ip_item.pluto_id)

        self.delete_a_record(domain_item, ip_item)

        domain_item.update(actions=[
            Domain.ip_list.set(remaining_ip_list),
            Domain.last_modified_by.set(user),
        ])

        ip_item.update(actions=[
            IPAddress.status.set('INACTIVE'),
            IPAddress.host_domain.remove(),
            IPAddress.routing_ids.set([]),
            IPAddress.last_status_switch.set(dt.datetime.now()),
            IPAddress.last_modified_by.set(user),
        ])
