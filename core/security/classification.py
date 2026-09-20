"""Data classification helpers for local persistence decisions."""

from __future__ import annotations

from enum import Enum


class DataClass(str, Enum):
    SECRET = "secret"
    PII_HIGH = "pii_high"
    PII_LOW = "pii_low"
    CONFIG = "config"
    PUBLIC = "public"


# Field / artifact → class (inventory mirror of docs/security/local-data-threat-model.md)
FIELD_CLASS: dict[str, DataClass] = {
    "token": DataClass.SECRET,
    "access_token": DataClass.SECRET,
    "refresh_token": DataClass.SECRET,
    "client_secret": DataClass.SECRET,
    "id_token": DataClass.SECRET,
    "authorization_code": DataClass.SECRET,
    "body_text": DataClass.PII_HIGH,
    "plain_text": DataClass.PII_HIGH,
    "html_text": DataClass.PII_HIGH,
    "snippet": DataClass.PII_HIGH,
    "email": DataClass.PII_HIGH,
    "cv_path": DataClass.PII_HIGH,
    "phone": DataClass.PII_HIGH,
    "first_name": DataClass.PII_HIGH,
    "last_name": DataClass.PII_HIGH,
    "company": DataClass.PII_LOW,
    "title": DataClass.PII_LOW,
    "job_id": DataClass.PII_LOW,
}


def classify_field(name: str) -> DataClass:
    return FIELD_CLASS.get(name, DataClass.CONFIG)


def may_log(name: str) -> bool:
    return classify_field(name) in {DataClass.PII_LOW, DataClass.CONFIG, DataClass.PUBLIC}


def may_export(name: str) -> bool:
    return classify_field(name) != DataClass.SECRET
