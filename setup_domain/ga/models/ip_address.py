import datetime as dt
import os

from pynamodb.attributes import (UnicodeAttribute, UTCDateTimeAttribute, JSONAttribute,
                                 BooleanAttribute, NumberAttribute)
from pynamodb.models import Model


class IPAddress(Model):
    class Meta:
        region = 'eu-west-1'
        table_name = 'mercury_EspServices'

    PK = UnicodeAttribute(hash_key=True)
    SK = UnicodeAttribute(range_key=True)

    type = UnicodeAttribute(null=False)

    ip_address = UnicodeAttribute(null=False)

    pluto_id = UnicodeAttribute(null=True)
    routing_ids = JSONAttribute(null=False)
    smtp = UnicodeAttribute(null=False)
    host_domain = UnicodeAttribute(null=True)
    host_system = UnicodeAttribute(null=True)
    last_sent_event = JSONAttribute(null=True)

    status = UnicodeAttribute(null=False)
    service = UnicodeAttribute(null=False)
    deactivating_ips = JSONAttribute(null=True)

    cyren_score = NumberAttribute(null=True)
    sender_score = NumberAttribute(null=True)
    proofpoint_status = UnicodeAttribute(null=True)
    proofpoint_blocked = BooleanAttribute(null=True)
    free_fr_status = UnicodeAttribute(null=True)
    free_fr_blocked = BooleanAttribute(null=True)

    created_at = UTCDateTimeAttribute(null=False)
    updated_at = UTCDateTimeAttribute(null=False)
    last_modified_by = UnicodeAttribute(null=True)
    last_status_switch = UTCDateTimeAttribute(null=True)

    def to_dict(self):
        result_dict = self.attribute_values
        result_dict['created_at'] = str(result_dict['created_at'])
        result_dict['updated_at'] = str(result_dict['updated_at'])
        result_dict['last_status_switch'] = str(result_dict['last_status_switch'])
        return result_dict

    def save(self, conditional_operator=None, **expected_values):
        self.service = os.getenv('SERVICE')
        self.updated_at = dt.datetime.now()
        self.type = 'IPADDRESS'
        self.PK = 'IPADDRESS'
        self.ip_address = self.SK
        super(IPAddress, self).save()

    def update(self, **expected_values):
        actions = expected_values['actions']
        actions.append(IPAddress.updated_at.set(dt.datetime.now()))
        super(IPAddress, self).update(actions)
