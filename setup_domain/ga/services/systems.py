import json
import os

from .set_up_class import SetUpClass

CREDS_FILE = os.path.join(os.path.dirname(__file__), '..', 'credentials.json')


def select_system(sending_system):
    with open(CREDS_FILE) as file:
        creds_dict = json.loads(file.read())
        pluto_cred = tuple(creds_dict['pluto_cred'])
        charon_cred = tuple(creds_dict['charon_cred'])
        inwx_username = creds_dict['inwx_cred']['username']
        inwx_password = creds_dict['inwx_cred']['password']
        aws_access_key_id = creds_dict['aws_cred_karma']['aws_access_key_id']
        aws_secret_access_key = creds_dict['aws_cred_karma']['aws_secret_access_key']

    if sending_system == 'Pluto':
        return SetUpClass(pluto_cred, 'plutomailsystem',
                          inwx_username, inwx_password,
                          aws_access_key_id, aws_secret_access_key)

    if sending_system == 'Charon':
        return SetUpClass(charon_cred, 'charonmail',
                          inwx_username, inwx_password,
                          aws_access_key_id, aws_secret_access_key)
