class DomainRegistrationError(Exception):
    """Error for when domain registration run into a problem after checking for availability"""


class DomainUnavailableError(Exception):
    """Error for when domain chosen for registration is not available on INWX"""


class DnsRecordSetupError(Exception):
    """Error for when the domain setup progress run into a problem"""


class PlutoEngineSetupError(Exception):
    """Error for when the domain setup progress in Pluto run into a problem"""


class PlutoEngineGetError(Exception):
    """Error for when getting data from Pluto API is unsuccessful"""


class ExternalError(Exception):
    """Exception for 400 errors"""
