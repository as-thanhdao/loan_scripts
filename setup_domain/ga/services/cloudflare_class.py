import os
import requests
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

TOKEN = os.environ['CLOUDFLARE_TOKEN']
ID = os.environ['CLOUDFLARE_ACCOUNT_ID']


class Cloudflare:
    def __init__(self):
        self.url = 'https://api.cloudflare.com/client/v4'
        self.headers = {'authorization': f'Bearer {TOKEN}'}
        self.id = ID

    def list_cloudflare_zones(self, params={}):
        return self.list_request('zones', params)

    def list_dns_records_by_zone(self, zone_id):
        return self.list_request(f'zones/{zone_id}/dns_records')

    def get_cloudflare_zone_by_name(self, domain):
        zone = self.list_request(end_point='zones', params={'name': domain})
        if len(zone):
            return zone[0]
        else:
            return None

    def check_domain_on_cloudflare(self, domain):
        zone = self.get_cloudflare_zone_by_name(domain)
        if zone is not None:
            return {'domain': domain, 'success': False, 'result': 'Existing domain'}
        else:
            return {'domain': domain, 'success': True, 'result': 'Available domain'}

    def create_cloudflare_zone(self, domain: str):
        data = {
            'account': {
                'id': self.id
            },
            'name': domain,
            'type': 'full'
        }
        res = requests.post(f'{self.url}/zones', headers=self.headers, json=data)
        result = self.check_response(res)
        return result

    def create_dns_record(self, zone_id, data):
        res = requests.post(f'{self.url}/zones/{zone_id}/dns_records', headers=self.headers, json=data)
        result = self.check_response(res)
        return result

    def delete_dns_record(self, zone_id, dns_id):
        res = requests.delete(f'{self.url}/zones/{zone_id}/dns_records/{dns_id}', headers=self.headers)
        result = self.check_response(res)
        return result

    def update_dns_record(self, zone_id, dns_id, record):
        data = {
            'content': record['value'],
            'type': record['type'],
            'name': record['name']
        }
        res = requests.put(f'{self.url}/zones/{zone_id}/dns_records/{dns_id}', headers=self.headers, data=data)
        result = self.check_response(res)
        return result

    def list_request(self, end_point, params={}):
        results = []
        page = 1
        while True:
            res = requests.get(f'{self.url}/{end_point}', headers=self.headers,
                               params={**params, 'page': page})
            json_dict = res.json()
            if not json_dict['success']:
                # Without this the loop used to retry the same failing page
                # forever, hanging the script and hammering Cloudflare.
                raise Exception(f'listing {end_point} failed:', json_dict['errors'])
            results += json_dict['result']
            info = json_dict['result_info']
            if info['total_pages'] == 0 or info['page'] >= info['total_pages']:
                return results
            page += 1

    def get_request(self, end_point, id):
        try:
            res = requests.get(f'{self.url}/{end_point}/{id}', headers=self.headers)
            json_dict = res.json()
            if json_dict['success']:
                return json_dict['result']
            else:
                logger.error(f'getting {end_point} failed:', json_dict['errors'])
                return None
        except Exception as e:
            raise e

    def check_response(self, res):
        json_dict = res.json()
        if json_dict['success']:
            return json_dict['result']
        else:
            raise Exception('Cloudflare request ERROR:', json_dict['errors'])
