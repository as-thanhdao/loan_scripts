import datetime as dt
import os

from pynamodb.attributes import (UnicodeAttribute, UTCDateTimeAttribute, JSONAttribute,
                                 BooleanAttribute, NumberAttribute)
from pynamodb.models import Model


class IPBlock(Model):
    class Meta:
        region = 'eu-west-1'
        table_name = 'mercury_EspServices'

    PK = UnicodeAttribute(hash_key=True)
    SK = UnicodeAttribute(range_key=True)

    type = UnicodeAttribute(null=False)

    ip_zone_name = UnicodeAttribute(null=False)
    hostzone_id = UnicodeAttribute(null=False)
    spf_block = UnicodeAttribute(null=False)
    smtp = UnicodeAttribute(null=False)

    service = UnicodeAttribute(null=False)

    created_at = UTCDateTimeAttribute(null=False)
    updated_at = UTCDateTimeAttribute(null=False)

    def save(self, conditional_operator=None, **expected_values):
        self.service = os.getenv('SERVICE')
        self.updated_at = dt.datetime.now()
        self.PK = 'PTR_RECORD'
        self.type = self.PK
        self.smtp = self.SK
        super(IPBlock, self).save()
