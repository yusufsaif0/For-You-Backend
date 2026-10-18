import json
from functools import lru_cache

import firebase_admin
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from firebase_admin import auth, credentials, exceptions as firebase_exceptions

from app.core.config import settings


bearer_scheme = HTTPBearer(auto_error=False)


@lru_cache(maxsize=1)
def _firebase_app() -> firebase_admin.App:
    if not settings.firebase_project_id:
        raise HTTPException(status_code=503, detail="Authentication is not configured on this server.")
    try:
        return firebase_admin.get_app()
    except ValueError:
        if settings.firebase_service_account_json:
            try:
                account = json.loads(settings.firebase_service_account_json)
                credential = credentials.Certificate(account)
            except (json.JSONDecodeError, ValueError, TypeError) as error:
                raise HTTPException(status_code=503, detail="Server authentication credentials are invalid.") from error
        else:
            credential = credentials.ApplicationDefault()
        try:
            return firebase_admin.initialize_app(
                credential,
                options={"projectId": settings.firebase_project_id},
            )
        except (ValueError, OSError) as error:
            raise HTTPException(status_code=503, detail="Server authentication is temporarily unavailable.") from error


def require_user(
    authorization: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict:
    if authorization is None or authorization.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Sign in to access your data.", headers={"WWW-Authenticate": "Bearer"})
    try:
        claims = auth.verify_id_token(
            authorization.credentials,
            check_revoked=True,
            app=_firebase_app(),
        )
    except HTTPException:
        raise
    except (
        auth.InvalidIdTokenError,
        auth.ExpiredIdTokenError,
        auth.RevokedIdTokenError,
        auth.UserDisabledError,
        firebase_exceptions.FirebaseError,
        ValueError,
        TypeError,
    ):
        raise HTTPException(status_code=401, detail="Your sign-in session is invalid or expired. Sign in again.", headers={"WWW-Authenticate": "Bearer"}) from None
    if not claims.get("uid") or not claims.get("email_verified", False):
        raise HTTPException(status_code=403, detail="Verify your email address before using the app.")
    return {"uid": claims["uid"], "email": claims.get("email")}


def reset_auth_cache_for_tests() -> None:
    _firebase_app.cache_clear()
