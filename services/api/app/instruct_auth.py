"""Instructional authorization has no anonymous/demo bypass."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import AwareDatetime, TypeAdapter, model_validator

from app.auth import AuthenticatedUser, _bearer, require_api_user
from app.config import Settings
from app.instruct_contracts import (
    ClassGrantV1, ClassSummaryV1, Contract, Id, PrincipalScopeV1,
)


class Membership(Contract):
    principal: PrincipalScopeV1
    classroom: ClassSummaryV1
    revision: Id
    validFrom: AwareDatetime
    validTo: AwareDatetime

    @model_validator(mode="after")
    def interval(self):
        if self.validTo <= self.validFrom:
            raise ValueError("invalid membership interval")
        return self


def require_instruct_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> AuthenticatedUser:
    # Direct reuse avoids inheriting the commercial dependency's global test override.
    if credentials is None:
        raise HTTPException(401, "Authentication required", headers={"WWW-Authenticate": "Bearer"})
    user = require_api_user(request, credentials)
    if user is None:
        raise HTTPException(401, "Authentication required", headers={"WWW-Authenticate": "Bearer"})
    return user


def principal(user: AuthenticatedUser) -> PrincipalScopeV1:
    # Entra object IDs are stable across our dedicated SPA/API registrations.
    return PrincipalScopeV1(
        tenantId=user.tenant_id, subject=str(user.claims.get("oid") or user.subject),
    )


def memberships(settings: Settings, user: AuthenticatedUser) -> list[Membership]:
    try:
        records = TypeAdapter(list[Membership]).validate_json(settings.INSTRUCT_CLASS_GRANTS_JSON)
        keys = [(m.principal.tenantId, m.principal.subject, m.classroom.classId) for m in records]
        if len(keys) != len(set(keys)):
            raise ValueError("ambiguous membership")
    except ValueError:
        raise HTTPException(503, "Authorization unavailable") from None
    now = datetime.now(timezone.utc)
    return [m for m in records if m.principal == principal(user) and m.validFrom <= now < m.validTo]


def authorize(
    settings: Settings, user: AuthenticatedUser, class_id: str, assessment_id: str | None = None,
) -> ClassGrantV1:
    match = next((m for m in memberships(settings, user) if m.classroom.classId == class_id
                  and (assessment_id is None or assessment_id in m.classroom.assessmentIds)), None)
    if match is None:
        raise HTTPException(404, "Resource not found")
    digest = hashlib.sha256(
        f"{user.tenant_id}\0{principal(user).subject}\0{class_id}\0{match.revision}".encode()
    ).hexdigest()
    return ClassGrantV1(
        grantId=digest, principal=principal(user), classId=class_id,
        checkedAt=datetime.now(timezone.utc), membershipRevision=match.revision,
    )
