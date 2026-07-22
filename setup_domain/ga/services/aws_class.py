import boto3
import datetime as dt
import logging

from exceptions import DomainRegistrationError
from .custom_classes import AwsRecord

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class Route53:
    def __init__(self, aws_access_key_id, aws_secret_access_key):
        session = boto3.Session(
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
        )
        self.client = session.client('route53')

    def get_all_aws_domain(self):
        temp_domain_check = self.client.list_hosted_zones()
        all_domain_list = temp_domain_check['HostedZones']
        while temp_domain_check['IsTruncated']:
            temp_domain_check = self.client.list_hosted_zones(Marker=temp_domain_check['NextMarker'])
            all_domain_list = all_domain_list + temp_domain_check['HostedZones']
        return all_domain_list

    def check_aws_domain(self, domain):
        all_domain_list = self.get_all_aws_domain()
        existing_domains = [x['Name'][:-1] for x in all_domain_list]
        if domain in existing_domains:
            return {'domain': domain, 'success': False, 'result': 'HostedZone already created'}
        else:
            return {'domain': domain, 'success': True, 'result': 'HostedZone available'}

    def create_aws_domain(self, domain: str):
        domain_dict = {}
        result = self.client.create_hosted_zone(Name=domain, CallerReference=str(dt.datetime.today()))
        if result['ResponseMetadata']['HTTPStatusCode'] in [200, 201, 202]:
            domain_dict['domain'] = domain
            domain_dict['domain_id'] = result['HostedZone']['Id'].split('/')[-1]
            domain_dict['ns_record'] = [x for x in result['DelegationSet']['NameServers']]
            domain_dict['success'] = True
            return domain_dict
        else:
            raise DomainRegistrationError(domain + ': HostedZone creation failed')

    def get_domain_record_list(self, domain, domain_id):
        domain_records = self.client.list_resource_record_sets(HostedZoneId=domain_id)['ResourceRecordSets']
        for record in domain_records:
            if record['Type'] == 'NS':
                if record['Name'] == domain + '.':
                    return [x['Value'][:-1] for x in record['ResourceRecords']]

    def get_aws_domain_id(self, domain):
        domain_id_list = self.get_all_aws_domain()
        domain_dict = {}
        for data in domain_id_list:
            if domain + '.' in data['Name']:
                domain_dict['domain'] = domain
                domain_dict['domain_id'] = data['Id'].split('/')[-1]
                ns_record = self.get_domain_record_list(domain, domain_dict['domain_id'])
                domain_dict['ns_record'] = ns_record
                domain_dict['success'] = True
                return domain_dict

    def change_domain_dns_records(self, domain_id: str, dns_dict: AwsRecord, action='CREATE', ttl=300):
        if dns_dict['record_name'][-1] != '.':
            dns_dict['record_name'] = dns_dict['record_name'] + '.'
        try:
            response = self.client.change_resource_record_sets(
                HostedZoneId=domain_id,
                ChangeBatch={
                    'Changes': [
                        {
                            'Action': action,
                            'ResourceRecordSet': {
                                'Name': dns_dict['record_name'],
                                'Type': dns_dict['type'],
                                'TTL': ttl,
                                'ResourceRecords': [{'Value': x} for x in dns_dict['value']]
                            }
                        }
                    ]
                }
            )
            return response
        except Exception as e:
            raise e

    def delete_host_zone(self, domain_id):
        try:
            temp_domain_records = self.client.list_resource_record_sets(HostedZoneId=domain_id)
            domain_records = temp_domain_records['ResourceRecordSets']
            while temp_domain_records['IsTruncated']:
                next_record_name = temp_domain_records['NextRecordName']
                temp_domain_records = self.client.list_resource_record_sets(HostedZoneId=domain_id,
                                                                            StartRecordName=next_record_name)
                domain_records.extend(temp_domain_records['ResourceRecordSets'])

            delete_rec = [x for x in domain_records if (x.get('Type', '') != 'NS' or x.get('TTL', '') != 172800) and x.get('Type', '') != 'SOA']
            if len(delete_rec) > 0:
                self.client.change_resource_record_sets(HostedZoneId=domain_id, ChangeBatch={
                    'Comment': 'Delete unused Hosted Zone',
                    'Changes': [{'Action': 'DELETE', 'ResourceRecordSet': x} for x in delete_rec]})

            delete = self.client.delete_hosted_zone(Id=domain_id)
            return delete
        except Exception as e:
            raise e
