from typing import TypedDict, List


class AwsRecord(TypedDict):
    name: str
    type: str
    value: List[str]


class CloudflareRecord(TypedDict):
    name: str
    type: str
    content: str
