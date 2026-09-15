import datetime as dt
import os

from pynamodb.attributes import (UnicodeAttribute, UTCDateTimeAttribute, JSONAttribute, BooleanAttribute)
from pynamodb.models import Model


class Domain(Model):
    class Meta:
        region = 'eu-west-1'
        table_name = 'mercury_EspServices'

    PK = UnicodeAttribute(hash_key=True)
    SK = UnicodeAttribute(range_key=True)

    type = UnicodeAttribute(null=False)

    sending_domain = UnicodeAttribute(null=True)
    sending_domain_id = UnicodeAttribute(null=True)
    host_domain = UnicodeAttribute(null=True)
    host_domain_id = UnicodeAttribute(null=True)
    click_main_domain = UnicodeAttribute(null=True)
    click_main_domain_id = UnicodeAttribute(null=True)
    click_sub_domain = UnicodeAttribute(null=True)

    sending_system = UnicodeAttribute(null=True)
    ip_list = JSONAttribute(null=True)
    click_ip = UnicodeAttribute(null=True)
    geo = UnicodeAttribute(null=True)
    domain_pluto_id = UnicodeAttribute(null=True)
    bounce_domain_pluto_id = UnicodeAttribute(null=True)
    url_pluto_id = UnicodeAttribute(null=True)
    dkim_pluto_id = UnicodeAttribute(null=True)
    smtp_relay_id = UnicodeAttribute(null=True)

    model_throttling_id = UnicodeAttribute(null=True)
    throttling_id = UnicodeAttribute(null=True)
    routing_id = UnicodeAttribute(null=True)

    registrant = UnicodeAttribute(null=False)
    admin = UnicodeAttribute(null=False)
    tech = UnicodeAttribute(null=False)
    billing = UnicodeAttribute(null=False)

    status = UnicodeAttribute(null=False)
    failed_reason = UnicodeAttribute(null=True)
    service = UnicodeAttribute(null=False)

    cyren_status = UnicodeAttribute(null=True)
    cyren_marked_spam = BooleanAttribute(null=True)
    google_status = UnicodeAttribute(null=True)
    google_bad_reputation = BooleanAttribute(null=True)
    hetrix_blacklist_list = JSONAttribute(null=True)
    hetrix_blacklisted = BooleanAttribute(null=True)

    dkim = BooleanAttribute(null=True)
    dmarc = BooleanAttribute(null=True)
    spf = BooleanAttribute(null=True)
    spamfence_status = UnicodeAttribute(null=True)

    created_at = UTCDateTimeAttribute(null=False)
    updated_at = UTCDateTimeAttribute(null=False)
    last_modified_by = UnicodeAttribute(null=True)

    def save(self, condition=None, conditional_operator=None, **expected_values):
        self.service = os.getenv('SERVICE')
        self.updated_at = dt.datetime.now()
        self.PK = 'SENDING_DOMAIN'
        self.type = self.PK
        self.sending_domain = self.SK
        super(Domain, self).save(condition=condition)

    def update(self, **expected_values):
        actions = expected_values['actions']
        actions.append(Domain.updated_at.set(dt.datetime.now()))
        super(Domain, self).update(actions)

    def to_dict(self):
        dict = self.attribute_values
        dict['created_at'] = str(dict['created_at'])
        dict['updated_at'] = str(dict['updated_at'])
        return dict
