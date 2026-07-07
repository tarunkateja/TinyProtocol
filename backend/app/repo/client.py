"""boto3 table access + conversion between JSON-ish dicts and DynamoDB items."""

import json
from decimal import Decimal
from typing import Any

import boto3

from app.config import settings

_resource = None


def _get_resource():
    global _resource
    if _resource is None:
        kwargs: dict[str, Any] = {}
        if settings.dynamo_endpoint_url:
            kwargs["endpoint_url"] = settings.dynamo_endpoint_url
        _resource = boto3.resource("dynamodb", **kwargs)
    return _resource


def reset() -> None:
    """Drop the cached boto3 resource (used by tests to pick up moto)."""
    global _resource
    _resource = None


def get_table():
    return _get_resource().Table(settings.table_name)


def get_client():
    return _get_resource().meta.client


def to_item(data: dict) -> dict:
    """Pydantic-dumped dict -> DynamoDB item (floats become Decimal, Nones dropped)."""
    cleaned = _strip_none(data)
    return json.loads(json.dumps(cleaned), parse_float=Decimal)


def from_item(item: Any) -> Any:
    """DynamoDB item -> plain dict (Decimal becomes int/float)."""
    if isinstance(item, Decimal):
        return int(item) if item % 1 == 0 else float(item)
    if isinstance(item, dict):
        return {k: from_item(v) for k, v in item.items()}
    if isinstance(item, list):
        return [from_item(v) for v in item]
    return item


def _strip_none(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _strip_none(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_strip_none(v) for v in value]
    return value
