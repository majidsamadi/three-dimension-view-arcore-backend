"""Service composition: ``build_live()`` from the Lambda environment, ``build_for_tests()``.

Live composition reads only environment variables set by Terraform
(``infra/application/compute.tf``).  The AWS SDK is imported lazily by the
adapters, so importing this module never touches AWS.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import os
import re
from typing import Mapping

from wisestay_home_backend.adapters.central_identity import CentralJwtIdentityVerifier
from wisestay_home_backend.adapters.dynamodb_repository import DynamoDbRepository
from wisestay_home_backend.adapters.jwks import HttpJwksSource
from wisestay_home_backend.adapters.resvanta_property_reference import (
    ResvantaHttpPropertyReference,
    SsmCredentialSource,
)
from wisestay_home_backend.adapters.s3_object_storage import S3ObjectStorage
from wisestay_home_backend.application.common import Clock, IdGenerator, SecretsIdGenerator, ServiceDeps
from wisestay_home_backend.domain import policy
from wisestay_home_backend.http.handlers import HomeScannerApi
from wisestay_home_backend.ports.commercial_gate import (
    CommercialGate,
    ConfigurationError,
    NotConfiguredCommercialGate,
)
from wisestay_home_backend.ports.identity import IdentityVerifier
from wisestay_home_backend.ports.object_storage import ObjectStorage
from wisestay_home_backend.ports.property_reference import (
    PropertyReferencePort,
    UnconfiguredPropertyReference,
)
from wisestay_home_backend.ports.repository import Repository

_ISSUER = re.compile(r"^https://cognito-idp\.ap-southeast-1\.amazonaws\.com/ap-southeast-1_[A-Za-z0-9]+$")
REQUIRED_ENV = ("WISESTAY_ENVIRONMENT", "TABLE_NAME", "ASSET_BUCKET", "CENTRAL_ISSUER",
                "CENTRAL_CLIENT_ID")


@dataclass(frozen=True, slots=True)
class Composition:
    api: HomeScannerApi
    repository: Repository
    storage: ObjectStorage
    identity: IdentityVerifier
    properties: PropertyReferencePort
    gate: CommercialGate
    clock: Clock
    ids: IdGenerator


def _compose(*, repository, storage, identity, properties, clock, ids, environment) -> Composition:
    gate = NotConfiguredCommercialGate(environment)
    deps = ServiceDeps(repository=repository, storage=storage, clock=clock, ids=ids)
    api = HomeScannerApi(deps=deps, identity=identity, properties=properties, gate=gate)
    return Composition(api, repository, storage, identity, properties, gate, clock, ids)


def build_for_tests(*, repository: Repository, storage: ObjectStorage, identity: IdentityVerifier,
                    properties: PropertyReferencePort, clock: Clock, ids: IdGenerator,
                    environment: str = "test") -> Composition:
    return _compose(repository=repository, storage=storage, identity=identity,
                    properties=properties, clock=clock, ids=ids, environment=environment)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def build_live(env: Mapping[str, str] | None = None) -> Composition:
    env = os.environ if env is None else env
    missing = [name for name in REQUIRED_ENV if not env.get(name)]
    if missing:
        raise ConfigurationError(f"missing environment: {', '.join(missing)}")
    if env["WISESTAY_ENVIRONMENT"] != "dev":
        raise ConfigurationError("this slice is composed for the dev environment only")
    issuer = env["CENTRAL_ISSUER"]
    if not _ISSUER.match(issuer):
        raise ConfigurationError("CENTRAL_ISSUER must be the central ap-southeast-1 Cognito pool")
    identity = CentralJwtIdentityVerifier(
        issuer=issuer, client_id=env["CENTRAL_CLIENT_ID"], application_id=policy.APPLICATION_ID,
        jwks=HttpJwksSource(issuer + "/.well-known/jwks.json", timeout_s=3, ttl_s=3600))
    api_root = env.get("RESVANTA_API_ROOT")
    parameter = env.get("RESVANTA_CREDENTIAL_PARAMETER")
    properties: PropertyReferencePort
    if api_root and parameter:
        properties = ResvantaHttpPropertyReference(api_root, SsmCredentialSource(parameter))
    else:
        properties = UnconfiguredPropertyReference()
    return _compose(repository=DynamoDbRepository(env["TABLE_NAME"]),
                    storage=S3ObjectStorage(env["ASSET_BUCKET"]), identity=identity,
                    properties=properties, clock=_utc_now, ids=SecretsIdGenerator(),
                    environment=env["WISESTAY_ENVIRONMENT"])
