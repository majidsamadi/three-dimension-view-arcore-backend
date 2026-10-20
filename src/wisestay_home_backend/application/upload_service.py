"""H02-H06 resumable upload state machine (HSB-02.2-02.4, HSB-03.1, HSB-03.3).

States: ``open`` -> ``finalized`` | ``cancelled``; an ``open`` upload older
than 7 days answers 410 ``upload_expired``.  Component state is reconciled
from storage HEAD, so a lost browser acknowledgement still shows
``confirmed``.  The first successful finalize writes exactly one immutable
SceneVersion in a single repository transaction; a repeat with the same
Idempotency-Key is replayed by the HTTP layer, and a new key gets 409
``already_finalized``.  A digest or size mismatch creates no version.
"""
from __future__ import annotations

import base64
from dataclasses import replace
from datetime import timedelta
import hashlib

from wisestay_home_backend.application.common import (
    ServiceDeps,
    capture_key,
    check_expected_version,
    epoch,
    iso,
    load_capture,
    load_scene,
    load_upload,
    not_found,
    parse_iso,
    require_fields,
    scene_key,
    upload_key,
    version_sk,
)
from wisestay_home_backend.domain import policy
from wisestay_home_backend.domain.asset_reference import ActorContext
from wisestay_home_backend.domain.envelope import (
    canonical_json,
    capabilities,
    validate_envelope,
    validate_glb_structure,
)
from wisestay_home_backend.domain.scene import (
    ApiError,
    ComponentSlot,
    ComponentState,
    Scene,
    SceneVersion,
    UploadSession,
    UploadState,
    VersionState,
)
from wisestay_home_backend.ports.object_storage import (
    rejected_key,
    staging_key,
    version_key,
)
from wisestay_home_backend.ports.repository import ConditionFailed, Item, Put

READ_CHUNK_BYTES = 8 * 1024 * 1024
_COMPONENT_FIELDS = ("component_id", "role", "media_type", "sha256", "bytes")


def sha256_b64(hex_digest: str) -> str:
    return base64.b64encode(bytes.fromhex(hex_digest)).decode("ascii")


class UploadService:
    def __init__(self, deps: ServiceDeps) -> None:
        self._deps = deps

    # --- helpers -----------------------------------------------------------------------

    def _owned(self, actor: ActorContext, upload_id: str) -> tuple[UploadSession, Item]:
        loaded = load_upload(self._deps.repository, upload_id)
        if loaded is None or loaded[0].owner_user_id != actor.user_id:
            raise not_found()  # never disclose another account's upload
        return loaded

    def _expired(self, upload: UploadSession) -> bool:
        return (upload.state is UploadState.OPEN
                and self._deps.clock() >= parse_iso(upload.expires_at))

    def _reconcile(self, upload: UploadSession) -> tuple[ComponentSlot, ...]:
        """Component states from storage HEAD (ChecksumMode=ENABLED); no writes."""
        slots = []
        for slot in upload.components:
            if slot.state is not ComponentState.PENDING:
                slots.append(slot)  # confirmed at finalize, or failed by full-read verification
                continue
            stored = self._deps.storage.head(staging_key(upload.upload_id, slot.component_id))
            if stored is None:
                slots.append(slot)
            elif stored.bytes != slot.bytes:
                slots.append(replace(slot, state=ComponentState.FAILED, reason="size_mismatch"))
            elif (stored.checksum_sha256_b64 is not None
                  and stored.checksum_sha256_b64 != sha256_b64(slot.sha256)):
                slots.append(replace(slot, state=ComponentState.FAILED, reason="digest_mismatch"))
            else:
                slots.append(replace(slot, state=ComponentState.CONFIRMED, reason=None))
        return tuple(slots)

    def _presign(self, upload_id: str, slot: ComponentSlot) -> dict:
        signed = self._deps.storage.presign_put(
            staging_key(upload_id, slot.component_id), sha256_b64=sha256_b64(slot.sha256),
            content_length=slot.bytes, expires_s=policy.PRESIGNED_PUT_LIFETIME_S)
        return {"component_id": slot.component_id, "put_url": signed.url,
                "put_headers": dict(signed.headers), "url_expires_at": signed.expires_at}

    def _write_upload(self, upload: UploadSession, item: Item) -> int:
        pk, sk = upload_key(upload.upload_id)
        try:
            self._deps.repository.transact([Put(
                Item(pk, sk, item.version + 1, upload.to_data(), ttl_epoch=item.ttl_epoch),
                "version", item.version)])
        except ConditionFailed as exc:
            current = self._deps.repository.get(pk, sk)
            raise ApiError("version_conflict",
                           current_version=current.version if current else item.version) from exc
        return item.version + 1

    @staticmethod
    def _view(upload: UploadSession, slots: tuple[ComponentSlot, ...], record_version: int) -> dict:
        return {"upload_id": upload.upload_id, "capture_id": upload.capture_id,
                "state": upload.state.value, "expires_at": upload.expires_at,
                "record_version": record_version,
                "components": [{"component_id": s.component_id, "state": s.state.value,
                                "reason": s.reason} for s in slots]}

    # --- H02 ---------------------------------------------------------------------------

    def create(self, actor: ActorContext, capture_id: str, body) -> dict:
        loaded = load_capture(self._deps.repository, capture_id)
        if loaded is None or loaded[0].owner_user_id != actor.user_id:
            raise not_found()
        capture = loaded[0]
        body = require_fields(body, required={"envelope", "components"})
        components = body["components"]
        if not isinstance(components, list) or not components:
            raise ApiError("invalid_request", "components must be a non-empty list")
        if len(components) > policy.COMPONENTS_PER_UPLOAD or any(
                isinstance(c, dict) and isinstance(c.get("bytes"), int)
                and c["bytes"] > policy.BYTES_PER_COMPONENT for c in components):
            raise ApiError("limit_exceeded")
        envelope = body["envelope"]
        reasons = validate_envelope(envelope, draft=True, expected_kind=capture.kind,
                                    expected_asset_id=capture.scene_id)
        if not reasons:
            declared = [{k: c.get(k) for k in _COMPONENT_FIELDS} if isinstance(c, dict) else c
                        for c in components]
            if declared != envelope["components"] or any(
                    not isinstance(c, dict) or set(c) != set(_COMPONENT_FIELDS) for c in components):
                reasons.append("envelope_component_invalid")
            provenance = envelope["provenance"]
            if (provenance["content_class"] != capture.content_class
                    or provenance["permission_record_id"] != capture.permission_record_id):
                reasons.append("envelope_field_invalid")
        if reasons:
            raise ApiError("validation_failed", reasons=reasons)

        now = self._deps.clock()
        upload_id = self._deps.ids.new("upl")
        expires = now + timedelta(seconds=policy.UPLOAD_SESSION_EXPIRY_S)
        slots = tuple(ComponentSlot(c["component_id"], c["role"], c["media_type"], c["sha256"],
                                    c["bytes"]) for c in components)
        upload = UploadSession(upload_id, capture.capture_id, actor.user_id, UploadState.OPEN,
                               iso(now), iso(expires), envelope, slots)
        signed = [self._presign(upload_id, s) for s in slots]
        pk, sk = upload_key(upload_id)
        ttl = epoch(expires) + policy.UPLOAD_RECORD_RETENTION_AFTER_EXPIRY_S
        self._deps.repository.transact([Put(Item(pk, sk, 1, upload.to_data(), ttl_epoch=ttl),
                                            "absent")])
        return {"upload_id": upload_id, "capture_id": capture.capture_id, "state": "open",
                "expires_at": upload.expires_at, "record_version": 1,
                "components": [{**s, "state": "pending"} for s in signed]}

    # --- H03 ---------------------------------------------------------------------------

    def get(self, actor: ActorContext, upload_id: str) -> dict:
        upload, item = self._owned(actor, upload_id)
        if self._expired(upload):
            raise ApiError("upload_expired")
        slots = self._reconcile(upload) if upload.state is UploadState.OPEN else upload.components
        return self._view(upload, slots, item.version)

    # --- H04 ---------------------------------------------------------------------------

    def component_urls(self, actor: ActorContext, upload_id: str, body) -> dict:
        upload, item = self._owned(actor, upload_id)
        body = require_fields(body or {}, required=set(), optional={"component_ids"})
        if upload.state is not UploadState.OPEN:
            raise ApiError("invalid_state")
        if self._expired(upload):
            raise ApiError("upload_expired")
        slots = self._reconcile(upload)
        known = {s.component_id for s in slots}
        requested = body.get("component_ids")
        if requested is not None:
            if (not isinstance(requested, list) or not requested
                    or any(not isinstance(c, str) or c not in known for c in requested)
                    or len(set(requested)) != len(requested)):
                raise ApiError("invalid_request", "component_ids must name components of this upload")
            wanted = set(requested)
        else:
            wanted = known
        reissue = [s for s in slots if s.component_id in wanted and s.state is not ComponentState.CONFIRMED]
        if any(s.state is ComponentState.FAILED for s in upload.components
               if s.component_id in {r.component_id for r in reissue}):
            reset = tuple(replace(s, state=ComponentState.PENDING, reason=None)
                          if s.component_id in wanted and s.state is ComponentState.FAILED else s
                          for s in upload.components)
            self._write_upload(upload.with_components(reset), item)
        return {"components": [self._presign(upload.upload_id, s) for s in reissue]}

    # --- H05 ---------------------------------------------------------------------------

    def cancel(self, actor: ActorContext, upload_id: str, body) -> dict:
        upload, item = self._owned(actor, upload_id)
        body = require_fields(body, required={"expected_version"})
        if upload.state is UploadState.CANCELLED:
            return {"state": "cancelled"}  # repeat is a no-op
        if upload.state is not UploadState.OPEN:
            raise ApiError("invalid_state")
        check_expected_version(body, item.version)
        self._write_upload(replace(upload, state=UploadState.CANCELLED), item)
        for slot in upload.components:
            try:
                self._deps.storage.delete(staging_key(upload.upload_id, slot.component_id))
            except Exception:  # best effort; staging/ expires after 7 days anyway
                pass
        return {"state": "cancelled"}

    # --- H06 ---------------------------------------------------------------------------

    def _digest(self, key: str, size: int) -> str:
        digest = hashlib.sha256()
        position = 0
        while position < size:
            end = min(position + READ_CHUNK_BYTES, size) - 1
            chunk = self._deps.storage.read_range(key, position, end)
            if not chunk:
                break
            digest.update(chunk)
            position += len(chunk)
        return digest.hexdigest() if position == size else ""

    def finalize(self, actor: ActorContext, upload_id: str, body) -> dict:
        repo, storage = self._deps.repository, self._deps.storage
        upload, item = self._owned(actor, upload_id)
        body = require_fields(body, required={"expected_version"})
        if upload.state is UploadState.FINALIZED:
            raise ApiError("already_finalized", scene_id=upload.scene_id, version=upload.version)
        if upload.state is not UploadState.OPEN:
            raise ApiError("invalid_state")
        if self._expired(upload):
            raise ApiError("upload_expired")
        check_expected_version(body, item.version)

        slots = self._reconcile(upload)
        problems = [{"component_id": s.component_id, "state": s.state.value, "reason": s.reason}
                    for s in slots if s.state is not ComponentState.CONFIRMED]
        if any(s.state is ComponentState.PENDING for s in slots):
            raise ApiError("upload_incomplete", components=problems)
        for reason, code in (("size_mismatch", "component_size_mismatch"),
                             ("digest_mismatch", "component_digest_mismatch")):
            if any(s.reason == reason for s in slots):
                raise ApiError(code, components=problems)

        # Full-read digest verification: the stored bytes, not the claimed checksum.
        failed = []
        for slot in slots:
            key = staging_key(upload.upload_id, slot.component_id)
            if self._digest(key, slot.bytes) != slot.sha256:
                failed.append(slot.component_id)
        if failed:
            marked = tuple(replace(s, state=ComponentState.FAILED, reason="digest_mismatch")
                           if s.component_id in failed else s for s in upload.components)
            self._write_upload(upload.with_components(marked), item)
            raise ApiError("component_digest_mismatch", components=[
                {"component_id": c, "state": "failed", "reason": "digest_mismatch"} for c in failed])

        loaded_capture = load_capture(repo, upload.capture_id)
        if loaded_capture is None:
            raise not_found()
        capture, capture_item = loaded_capture
        now = iso(self._deps.clock())
        scene_loaded = load_scene(repo, capture.scene_id) if capture.scene_id else None
        if capture.scene_id and scene_loaded is None:
            raise ApiError("dependency_unavailable", "scene record missing for capture")
        scene_id = capture.scene_id or self._deps.ids.new("scn")
        version = str(scene_loaded[0].latest_version + 1 if scene_loaded else 1)

        envelope = {**upload.envelope, "asset_id": scene_id, "version": version,
                    "audience_projection_id": None}
        reasons = validate_envelope(envelope, expected_kind=capture.kind, expected_asset_id=scene_id)
        for slot in slots:
            key = staging_key(upload.upload_id, slot.component_id)
            for code in validate_glb_structure(
                    lambda a, b, _k=key: storage.read_range(_k, a, b), slot.bytes,
                    envelope_bounds=envelope.get("bounds_m"), kind=capture.kind):
                if code not in reasons:
                    reasons.append(code)
        state = VersionState.QUARANTINED if reasons else VersionState.VALIDATED

        stored_components = []
        for slot in slots:
            source = staging_key(upload.upload_id, slot.component_id)
            if state is VersionState.VALIDATED:
                dest = version_key(slot.sha256)
                if storage.head(dest) is None:
                    storage.copy(source, dest)
            else:
                dest = rejected_key(upload.upload_id, slot.component_id)
                storage.copy(source, dest)
            stored_components.append({"component_id": slot.component_id, "role": slot.role,
                                      "media_type": slot.media_type, "sha256": slot.sha256,
                                      "bytes": slot.bytes, "key": dest})

        envelope_sha256 = hashlib.sha256(canonical_json(envelope)).hexdigest()
        scene_version = SceneVersion(scene_id, version, upload.upload_id, state, tuple(reasons),
                                     envelope, envelope_sha256, tuple(stored_components), now)
        summary = {"state": state.value, "scale_claim": envelope.get("scale_claim"),
                   "bounds_m": envelope.get("bounds_m"),
                   "capabilities": capabilities(envelope, validated=state is VersionState.VALIDATED),
                   "missing_regions": list(envelope.get("unobserved_regions") or [])}
        result = {"scene_id": scene_id, "version": version, "state": state.value,
                  "validation": {"reasons": list(reasons)}, "envelope_sha256": envelope_sha256}
        finalized = replace(upload, state=UploadState.FINALIZED, scene_id=scene_id, version=version,
                            components=tuple(replace(s, state=ComponentState.CONFIRMED) for s in slots),
                            finalize_result=result)

        upk, usk = upload_key(upload.upload_id)
        spk, ssk = scene_key(scene_id)
        writes = [
            Put(Item(upk, usk, item.version + 1, finalized.to_data(), ttl_epoch=item.ttl_epoch),
                "version", item.version),
            Put(Item(spk, version_sk(version), 1, scene_version.to_data()), "absent"),
        ]
        if scene_loaded is None:
            scene = Scene(scene_id, capture.owner_user_id, capture.capture_id, capture.property_id,
                          capture.property_type, capture.kind, capture.content_class, now, 1,
                          {version: summary})
            writes.append(Put(Item(spk, ssk, 1, scene.to_data(), gsi1pk=f"OWNER#{capture.owner_user_id}",
                                   gsi1sk=f"SCENE#{now}#{scene_id}"), "absent"))
            cpk, csk = capture_key(capture.capture_id)
            writes.append(Put(Item(cpk, csk, capture_item.version + 1,
                                   replace(capture, scene_id=scene_id).to_data()),
                              "version", capture_item.version))
        else:
            scene, scene_item = scene_loaded
            updated = replace(scene, latest_version=int(version),
                              version_summaries={**scene.version_summaries, version: summary})
            writes.append(Put(Item(spk, ssk, scene_item.version + 1, updated.to_data(),
                                   gsi1pk=scene_item.gsi1pk, gsi1sk=scene_item.gsi1sk),
                              "version", scene_item.version))
        try:
            repo.transact(writes)
        except ConditionFailed as exc:
            current = load_upload(repo, upload.upload_id)
            if current and current[0].state is UploadState.FINALIZED:
                raise ApiError("already_finalized", scene_id=current[0].scene_id,
                               version=current[0].version) from exc
            raise ApiError("version_conflict",
                           current_version=current[1].version if current else item.version) from exc
        for slot in slots:
            try:
                storage.delete(staging_key(upload.upload_id, slot.component_id))
            except Exception:  # best effort; staging/ expires after 7 days anyway
                pass
        return result
