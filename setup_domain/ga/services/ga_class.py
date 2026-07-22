import requests
import json
import logging

from exceptions import PlutoEngineSetupError, PlutoEngineGetError

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class GAEngineAPI:
    def __init__(self, ga_api_cred: tuple, ga_system_domain: str):
        self.engine_cred = ga_api_cred
        self.system_domain = ga_system_domain
        self.base_url = f'https://{ga_system_domain}.com/ga/api/v3/eng'

    def create_dkim_key(self, domain: str):
        input_data = {
            "dkim_key": {
                "domain": domain,
                "selector": "default",
                "default_for_domain": True,
                "key": {
                    "bits": 1024
                }
            }
        }
        dkim_create_res = requests.post(f'{self.base_url}/dkim_keys',
                                        auth=self.engine_cred,
                                        data=json.dumps(input_data))
        if dkim_create_res.json()['success']:
            return dkim_create_res.json()
        else:
            raise PlutoEngineSetupError(domain + ': ' + dkim_create_res.json()['error_messages'][0])

    def create_domain(self, domain: str):
        input_data = {
            "domain": {
                "domain": domain,
                "email_status": "normal"
            }
        }
        create_domain_res = requests.post(f'{self.base_url}/incoming_email_domains',
                                          auth=self.engine_cred,
                                          data=json.dumps(input_data))
        if create_domain_res.json()['success']:
            return create_domain_res.json()
        else:
            raise PlutoEngineSetupError(domain + ': ' + create_domain_res.json()['error_messages'][0])

    def create_bounce_mailboxes(self, domain_id):
        input_data = {
            "mailbox": {
                "localpart": "return"
            }
        }
        create_mailbox_res = requests.post(
            f'{self.base_url}/incoming_email_domains/{domain_id}/bounce_mailboxes',
            auth=self.engine_cred,
            data=json.dumps(input_data))
        if create_mailbox_res.json()['success']:
            logger.info('Bounce mailbox created')
        else:
            raise PlutoEngineSetupError('Bounce mailbox creation failed: ' + create_mailbox_res.json()['error_messages'][0])

    def create_spam_mailboxes(self, domain_id, mailboxes: list):
        for box in mailboxes:
            input_data = {
                "mailbox": {
                    "localpart": box["local"],
                }
            }
            create_mailbox_res = requests.post(
                f'{self.base_url}/incoming_email_domains/{domain_id}/spam_complaint_mailboxes',
                auth=self.engine_cred,
                data=json.dumps(input_data)
            )
            if create_mailbox_res.json()['success']:
                logger.info('Spam mailbox created')
            else:
                raise PlutoEngineSetupError('Spam mailbox creation failed: ' + create_mailbox_res.json()['error_messages'][0])

    def create_forward_mailboxes(self, domain_id, mailboxes: list):
        for box in mailboxes:
            input_data = {
                "mailbox": {
                    "localpart": box["local"],
                    "forward_to": [
                        box["forward_address"]
                    ],
                    "is_wildcard": False
                }
            }
            create_mailbox_res = requests.post(
                f'{self.base_url}/incoming_email_domains/{domain_id}/forwarding_mailboxes',
                auth=self.engine_cred,
                data=json.dumps(input_data)
            )
            if create_mailbox_res.json()['success']:
                logger.info('Forward mailbox created')
            else:
                raise PlutoEngineSetupError('Forward mailbox creation failed: ' + create_mailbox_res.json()['error_messages'][0])

    def create_click_url(self, click_sub_domain: str):
        input_data = {
            "url_domain": {
                "domain": click_sub_domain,
                "ssl": True
            }
        }
        create_url_res = requests.post(
            f'{self.base_url}/url_domains',
            auth=self.engine_cred,
            data=json.dumps(input_data))
        if create_url_res.json()['success']:
            logger.info('Click URL created')
            return create_url_res.json()
        else:
            raise PlutoEngineSetupError('Click URL creation failed: ' + create_url_res.json()['error_messages'][0])

    def get_routing_rule(self, routing_id: str):
        response = requests.get(f'{self.base_url}/routing_rules/{routing_id}',
                                    auth=self.engine_cred)
        json_data = response.json()
        if json_data['success']:
            return json_data['data']['routing_rule']
        else:
            raise PlutoEngineGetError(f"Getting routing rule with the ID: {routing_id} failed: " +
                                      json_data['error_messages'][0])

    def create_routing_rule(self, domain: str, ip_id_list: list):
        routing_rule = [{"virtual_mta": {"id": x}, "portion_of_mail": 1} for x in ip_id_list]
        input_data = {
            "routing_rule": {
                "name": domain,
                "default": {
                    "randomization_type": "random",
                    "deliver_through": routing_rule
                }
            }
        }
        create_rule_res = requests.post(f'{self.base_url}/routing_rules',
                                        auth=self.engine_cred,
                                        data=json.dumps(input_data))
        if create_rule_res.json()['success']:
            logger.info(f'Routing rule for {domain} created')
            return create_rule_res.json()['data']['routing_rule']['id']
        else:
            raise PlutoEngineSetupError('Routing rule creation failed: ' + create_rule_res.json()['error_messages'][0])

    def update_routing_rule(self, routing_id, ip_id_list: list):
        routing_rule = [{"virtual_mta": {"id": x}, "portion_of_mail": 1} for x in ip_id_list]
        input_data = {
            "routing_rule": {
                "default": {
                    "randomization_type": "random",
                    "deliver_through": routing_rule
                }
            }
        }
        update_rule_res = requests.put(f'{self.base_url}/routing_rules/{routing_id}',
                                       auth=self.engine_cred,
                                       data=json.dumps(input_data))
        if update_rule_res.json()['success']:
            logger.info(f'Routing rule updated')
        else:
            raise PlutoEngineSetupError('Routing rule update failed: ' + update_rule_res.json()['error_messages'][0])

    def delete_routing_rule(self, routing_id):
        delete_rule_res = requests.delete(f'{self.base_url}/routing_rules/{routing_id}',
                                          auth=self.engine_cred)
        if delete_rule_res.json()['success']:
            logger.info(f'Routing rule deleted')
        else:
            logger.info(f'Routing rule already deleted')

    def create_ip(self, name: str, ip_address: str, hostname: str, throttling_id):
        ip_info = {
            "ip_address": {
                "name": name,
                "ip": ip_address,
                "hostname": hostname,
                "throttling_template": {
                    'id': throttling_id
                },
                'default': {'max_concurrent_connections': 1,
                            'max_messages_per_hour': 300}
            }
        }
        ip_create_res = requests.post(f'{self.base_url}/ip_addresses',
                                      auth=self.engine_cred,
                                      data=json.dumps(ip_info))
        if ip_create_res.json()['success']:
            logger.info(f'{hostname} updated')
            return ip_create_res.json()['data']['ip_address']['id']
        else:
            raise PlutoEngineSetupError('Adding IP to Pluto failed: ' + ip_create_res.json()['error_messages'][0])
    
    def update_ip(self, ip_id: str, hostname: str, throttling_id):
        ip_info = {
            "ip_address": {
                "hostname": hostname,
                "throttling_template": {
                    'id': throttling_id
                },
                'default': {'max_concurrent_connections': 1,
                            'max_messages_per_hour': 300}
            }
        }
        ip_create_res = requests.put(f'{self.base_url}/ip_addresses/{ip_id}',
                                      auth=self.engine_cred,
                                      data=json.dumps(ip_info))
        if ip_create_res.json()['success']:
            logger.info(f'{hostname} updated')
            return ip_create_res.json()['data']['ip_address']['id']
        else:
            raise PlutoEngineSetupError('Adding IP to Pluto failed: ' + ip_create_res.json()['error_messages'][0])

    def create_throttling_template(self, name: str, rules: list):
        create_throttle_rule = {
            "throttling_template": {
                "name": name,
                "rules": rules,
                "default": {
                    "max_concurrent_connections": 1,
                    "max_messages_per_hour": 100
                }
            }
        }
        throttle_rule_res = requests.post(f'{self.base_url}/throttling_templates',
                                          auth=self.engine_cred,
                                          data=json.dumps(create_throttle_rule))
        if throttle_rule_res.json()['success']:
            return throttle_rule_res.json()['data']['throttling_template']['id']
        else:
            raise PlutoEngineSetupError('Throttling rule creation failed: ' + throttle_rule_res.json()['error_messages'][0])

    def get_throttling_template_data(self, rule_id):
        throttle_rule_res = requests.get(f'{self.base_url}/throttling_templates/{rule_id}',
                                         auth=self.engine_cred)
        return throttle_rule_res.json()

    def create_smtp_relay(self, relay_name: str, destination: dict):
        input = {
            "relay_server": {
                "name": relay_name,
                "source_ip": {
                  "ip": "193.107.76.1",
                  "hostname": "smtp1-0.pluto-relay.de"
                },
                "destination": destination,
                "throttle_limits": {
                  "max_concurrent_connections": 10,
                  "max_messages_per_hour": 500000
                }
              }
            }
        smtp_relay_res = requests.post(f'{self.base_url}/relay_servers',
                                       data=json.dumps(input),
                                       auth=self.engine_cred)
        if smtp_relay_res.json()['success']:
            return smtp_relay_res.json()
        else:
            raise PlutoEngineSetupError(relay_name + ': ' + smtp_relay_res.json()['error_messages'][0])

    def delete_ip(self, ip_id_list):
        delete_res = requests.delete(f'{self.base_url}/ip_addresses/{ip_id_list}',
                                     auth=self.engine_cred)
        if delete_res.json()['success']:
            logger.info(f'{ip_id_list} ip deleted')
        else:
            raise PlutoEngineSetupError(f'IP {ip_id_list} delete failed: ' + delete_res.json()['error_messages'][0])

    def delete_domain(self, domain_id):
        if domain_id:
            delete_domain_res = requests.delete(f'{self.base_url}/incoming_email_domains/{domain_id}',
                                                auth=self.engine_cred)
            if delete_domain_res.json()['success']:
                logger.info(f'Domain {domain_id} deleted from Pluto')
            else:
                raise PlutoEngineSetupError(f"Domain {domain_id} failed to delete: " +
                                            f"{delete_domain_res.json()['error_messages'][0]}")

    def delete_throttling_rule(self, throttling_id):
        if throttling_id:
            delete_throttling_res = requests.delete(f'{self.base_url}/throttling_templates/{throttling_id}',
                                                    auth=self.engine_cred)
            if delete_throttling_res.json()['success']:
                logger.info(f'Domain {throttling_id} deleted from Pluto')
            else:
                raise PlutoEngineSetupError(f"Domain {throttling_id} failed to delete: " +
                                            f"{delete_throttling_res.json()['error_messages'][0]}")

    def delete_dkim(self, dkim_id):
        if dkim_id:
            delete_dkim_res = requests.delete(f'{self.base_url}/dkim_keys/{dkim_id}',
                                              auth=self.engine_cred)
            if delete_dkim_res.json()['success']:
                logger.info(f'DKIM key {dkim_id} deleted from Pluto')
            else:
                raise PlutoEngineSetupError(f"DKIM key {dkim_id} failed to delete: " +
                                            f"{delete_dkim_res.json()['error_messages'][0]}")

    def delete_url(self, url_id):
        if url_id:
            delete_url_res = requests.delete(f'{self.base_url}/url_domains/{url_id}',
                                             auth=self.engine_cred)
            if delete_url_res.json()['success']:
                logger.info(f'DKIM key {url_id} deleted from Pluto')
            else:
                raise PlutoEngineSetupError(f"DKIM key {url_id} failed to delete: " +
                                            f"{delete_url_res.json()['error_messages'][0]}")

    def delete_smtp_relay(self, smtp_relay_id):
        if smtp_relay_id:
            delete_smtp_res = requests.delete(f'{self.base_url}/relay_servers/{smtp_relay_id}',
                                              auth=self.engine_cred)
            if delete_smtp_res.json()['success']:
                logger.info(f'SMTP Relay {smtp_relay_id} deleted from Pluto')
            else:
                raise PlutoEngineSetupError(f"SMTP Relay {smtp_relay_id} failed to delete: " +
                                            f"{delete_smtp_res.json()['error_messages'][0]}")
