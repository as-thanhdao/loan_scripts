import logging
from models import IPAddress, Domain

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def get_ip_address_id(ip_list):
    logger.info(f'Getting pluto IDs of {ip_list} on DynamoDB')
    id_list = []
    for ip in ip_list:
        item = IPAddress.get('IPADDRESS', ip)
        id_list.append(item.pluto_id)
    return id_list


def db_update_ip_routing_list(ip_list: list, routing_id_list: list, action='ADD'):
    logger.info(f'{action} pluto routing IDs with {routing_id_list} on {ip_list} on DynamoDB')
    if action == 'REPLACE':
        for ip in ip_list:
            item = IPAddress.get('IPADDRESS', ip)
            item.update(actions=[
                IPAddress.routing_ids.set(routing_id_list)
            ])
    if action == 'ADD':
        for ip in ip_list:
            item = IPAddress.get('IPADDRESS', ip)
            new_routing_ids = item.routing_ids + routing_id_list
            item.update(actions=[
                IPAddress.routing_ids.set(new_routing_ids)
            ])


def db_update_ip_id(ip_list: list, pluto_id):
    logger.info(f'Updating pluto IDs of {ip_list} on DynamoDB')
    for ip in ip_list:
        item = IPAddress.get('IPADDRESS', ip)
        item.update(actions=[
            IPAddress.pluto_id.set(str(pluto_id))
        ])


def db_update_unused_domain(record: dict):
    item = Domain.get('SENDING_DOMAIN', record['name'])
    item.update(actions=[
        Domain.status.set('UNUSED'),
        Domain.sending_domain_id.set(record['id'])
    ])
    logger.info(f'Updated {record["name"]} with id {record["id"]} to UNUSED')
