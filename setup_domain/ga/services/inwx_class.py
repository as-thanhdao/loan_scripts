import logging

from exceptions import DomainUnavailableError, DomainRegistrationError, DnsRecordSetupError
from INWX.Domrobot import ApiClient

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class INWX:
    def __init__(self, username, password):
        api_client = ApiClient(api_url=ApiClient.API_LIVE_URL, api_type='/jsonrpc/')
        api_client.login(username, password)
        self.client = api_client

    def check_domain_availability(self, domain):
        domain_check_result = self.client.call_api(api_method='domain.check', method_params={'domain': domain})
        if domain_check_result['code'] == 1000:
            result_availability = domain_check_result['resData']['domain'][0]
            if result_availability['avail'] == 1 and result_availability['status'] == 'free':
                return {'domain': domain, 'success': True, 'result': 'Domain available'}
            elif result_availability['avail'] == 0 and result_availability['status'] == 'yours':
                return {'domain': domain, 'success': False, 'result': 'Domain already owned'}
            elif result_availability['avail'] == 0 and result_availability['status'] == 'used':
                raise DomainUnavailableError(domain + ' is unavailable')
        else:
            raise DomainUnavailableError(domain + ' is unavailable. ' + domain_check_result.get('reason', str(domain_check_result)))

    def buy_domain(self, domain: str, ns_records: list, registrant: int, admin: int, tech: int, billing: int):
        logger.info(f'Buying {domain}...')
        if domain[-3:] == '.us':
            domain_create_result = self.client.call_api(api_method='domain.create',
                                                        method_params={'domain': domain,
                                                                       'registrant': registrant, 'admin': admin,
                                                                       'tech': tech, 'billing': billing,
                                                                       'renewalMode': 'AUTORENEW',
                                                                       'ns': ns_records,
                                                                       'extData': {'US-NEXUS-APPPURPOSE': 'P1',
                                                                                   'US-NEXUS-CATEGORY': 'C31'}})
        else:
            domain_create_result = self.client.call_api(api_method='domain.create',
                                                        method_params={'domain': domain,
                                                                       'registrant': registrant, 'admin': admin,
                                                                       'tech': tech, 'billing': billing,
                                                                       'renewalMode': 'AUTORENEW',
                                                                       'ns': ns_records})
        if domain_create_result['code'] in [1000, 1001, 1300]:
            return {'domain': domain, 'success': True, 'result': 'Domain bought'}
        else:
            error_mess = domain_create_result.get('reason', domain_create_result)
            logger.error(error_mess)
            raise DomainRegistrationError(domain + ' buying failed: ' + error_mess)

    def ns_record_setup(self, domain: str, ns_records):
        ns_create_result = self.client.call_api(api_method='nameserver.create',
                                                method_params={'domain': domain, 'type': 'MASTER',
                                                               'ns': ns_records})
        if ns_create_result['code'] in [1000, 1001, 1300]:
            return {'domain': domain, 'success': True, 'result': 'NS created'}
        else:
            error_mess = ns_create_result.get('reason', ns_create_result)
            raise DnsRecordSetupError(domain + ' NS record setup failed: ' + error_mess)

    def change_renew_method(self, domain, new_method):
        update_domain_res = self.client.call_api(api_method='domain.update',
                                                 method_params={'domain': domain, 'renewalMode': new_method})
        if update_domain_res['code'] in [1000, 1001, 1300]:
            return {'domain': domain, 'success': True, 'result': 'Domain renewal rule updated'}
        else:
            error_mess = update_domain_res.get('reason', update_domain_res)
            raise DnsRecordSetupError(domain + ' domain renewal update failed: ' + error_mess)
