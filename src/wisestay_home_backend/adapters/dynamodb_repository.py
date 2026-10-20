"""Live DynamoDB repository adapter (plan X.9.2).

``boto3`` is imported lazily, only when no client is injected (it ships with
the Lambda Python runtime).  Tests inject a stub client and never import it.
Items expired by TTL are treated as absent before DynamoDB deletes them.
"""
from __future__ import annotations

import base64
import json
import math
import time
from typing import Any, Callable

from wisestay_home_backend.ports.repository import (
    MAX_TRANSACT_OPS,
    Check,
    ConditionFailed,
    Item,
    Put,
    RepositoryUnavailable,
)

_ABSENT = "attribute_not_exists(pk) OR (attribute_exists(ttl_epoch) AND ttl_epoch <= :now)"
_VERSION = "#v = :expected"


def to_attr(value: Any) -> dict:
    if value is None:
        return {"NULL": True}
    if isinstance(value, bool):
        return {"BOOL": value}
    if isinstance(value, int):
        return {"N": str(value)}
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite numbers cannot be stored")
        return {"N": repr(value)}
    if isinstance(value, str):
        return {"S": value}
    if isinstance(value, (list, tuple)):
        return {"L": [to_attr(v) for v in value]}
    if isinstance(value, dict):
        return {"M": {str(k): to_attr(v) for k, v in value.items()}}
    raise TypeError(f"cannot store {type(value).__name__}")


def from_attr(attr: dict) -> Any:
    (kind, value), = attr.items()
    if kind == "NULL":
        return None
    if kind == "BOOL":
        return bool(value)
    if kind == "N":
        return int(value) if value.lstrip("-").isdigit() else float(value)
    if kind == "S":
        return value
    if kind == "L":
        return [from_attr(v) for v in value]
    if kind == "M":
        return {k: from_attr(v) for k, v in value.items()}
    raise ValueError(f"unsupported attribute type {kind}")


def _item_to_av(item: Item, version: int) -> dict:
    av = {"pk": {"S": item.pk}, "sk": {"S": item.sk}, "version": {"N": str(version)},
          "data": to_attr(item.data)}
    if item.gsi1pk is not None:
        av["gsi1pk"] = {"S": item.gsi1pk}
        av["gsi1sk"] = {"S": item.gsi1sk or ""}
    if item.ttl_epoch is not None:
        av["ttl_epoch"] = {"N": str(item.ttl_epoch)}
    return av


def _av_to_item(av: dict) -> Item:
    return Item(av["pk"]["S"], av["sk"]["S"], int(av["version"]["N"]), from_attr(av["data"]),
                av.get("gsi1pk", {}).get("S"), av.get("gsi1sk", {}).get("S"),
                int(av["ttl_epoch"]["N"]) if "ttl_epoch" in av else None)


def _error_code(exc: Exception) -> str | None:
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        return response.get("Error", {}).get("Code")
    return None


def _encode_cursor(key: dict | None) -> str | None:
    if not key:
        return None
    return base64.urlsafe_b64encode(json.dumps(key, sort_keys=True).encode("utf-8")).decode("ascii")


def _decode_cursor(cursor: str | None) -> dict | None:
    if cursor is None:
        return None
    try:
        value = json.loads(base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise ValueError("invalid cursor") from exc
    if not isinstance(value, dict):
        raise ValueError("invalid cursor")
    return value


class DynamoDbRepository:
    def __init__(self, table: str, client=None, *, clock: Callable[[], float] = time.time) -> None:
        if client is None:
            import boto3  # noqa: PLC0415 - lazy: never imported by tests

            client = boto3.client("dynamodb")
        self._table = table
        self._client = client
        self._clock = clock

    def _live(self, item: Item | None) -> Item | None:
        if item is not None and item.ttl_epoch is not None and self._clock() >= item.ttl_epoch:
            return None
        return item

    def get(self, pk: str, sk: str) -> Item | None:
        try:
            response = self._client.get_item(TableName=self._table, ConsistentRead=True,
                                              Key={"pk": {"S": pk}, "sk": {"S": sk}})
        except Exception as exc:
            raise RepositoryUnavailable("get_item failed") from exc
        raw = response.get("Item")
        return self._live(_av_to_item(raw)) if raw else None

    def transact(self, writes: list[Put | Check]) -> None:
        if not 1 <= len(writes) <= MAX_TRANSACT_OPS:
            raise ValueError("transact takes 1-25 operations")
        now = str(int(self._clock()))
        items = []
        for write in writes:
            if isinstance(write, Put) and write.expect == "absent":
                items.append({"Put": {
                    "TableName": self._table, "Item": _item_to_av(write.item, write.item.version),
                    "ConditionExpression": _ABSENT,
                    "ExpressionAttributeValues": {":now": {"N": now}}}})
            elif isinstance(write, Put):
                items.append({"Put": {
                    "TableName": self._table,
                    "Item": _item_to_av(write.item, write.expected_version + 1),
                    "ConditionExpression": _VERSION,
                    "ExpressionAttributeNames": {"#v": "version"},
                    "ExpressionAttributeValues": {":expected": {"N": str(write.expected_version)}}}})
            else:
                items.append({"ConditionCheck": {
                    "TableName": self._table,
                    "Key": {"pk": {"S": write.pk}, "sk": {"S": write.sk}},
                    "ConditionExpression": _VERSION,
                    "ExpressionAttributeNames": {"#v": "version"},
                    "ExpressionAttributeValues": {":expected": {"N": str(write.expected_version)}}}})
        try:
            self._client.transact_write_items(TransactItems=items)
        except Exception as exc:
            code = _error_code(exc)
            if code in ("TransactionCanceledException", "ConditionalCheckFailedException"):
                reasons = getattr(exc, "response", {}).get("CancellationReasons") or []
                if not reasons or any(r.get("Code") == "ConditionalCheckFailed" for r in reasons):
                    raise ConditionFailed("conditional write failed") from exc
            raise RepositoryUnavailable("transact_write_items failed") from exc

    def _query(self, *, index: str | None, hash_name: str, range_name: str, hash_value: str,
               sk_prefix: str, limit: int, cursor: str | None) -> tuple[list[Item], str | None]:
        kwargs = {
            "TableName": self._table,
            "KeyConditionExpression": "#h = :h AND begins_with(#r, :p)",
            "ExpressionAttributeNames": {"#h": hash_name, "#r": range_name},
            "ExpressionAttributeValues": {":h": {"S": hash_value}, ":p": {"S": sk_prefix}},
            "Limit": limit,
        }
        if index:
            kwargs["IndexName"] = index
        else:
            kwargs["ConsistentRead"] = True
        start = _decode_cursor(cursor)
        if start:
            kwargs["ExclusiveStartKey"] = start
        try:
            response = self._client.query(**kwargs)
        except Exception as exc:
            raise RepositoryUnavailable("query failed") from exc
        items = [i for i in (self._live(_av_to_item(raw)) for raw in response.get("Items", [])) if i]
        return items, _encode_cursor(response.get("LastEvaluatedKey"))

    def query(self, pk: str, sk_prefix: str, *, limit: int,
              cursor: str | None) -> tuple[list[Item], str | None]:
        return self._query(index=None, hash_name="pk", range_name="sk", hash_value=pk,
                           sk_prefix=sk_prefix, limit=limit, cursor=cursor)

    def query_gsi1(self, gsi1pk: str, sk_prefix: str, *, limit: int,
                   cursor: str | None) -> tuple[list[Item], str | None]:
        return self._query(index="gsi1", hash_name="gsi1pk", range_name="gsi1sk",
                           hash_value=gsi1pk, sk_prefix=sk_prefix, limit=limit, cursor=cursor)
