"""
UCKhabar — Firebase Authentication Service

Verifies Firebase ID tokens sent from the frontend after Google Sign-In.
Used as a FastAPI dependency on all protected endpoints.

How it works:
  1. User signs in with Google on the frontend (Firebase Auth handles OAuth)
  2. Frontend gets a Firebase ID token
  3. Frontend sends token in every API request: Authorization: Bearer <token>
  4. This service verifies the token and extracts the user's UID
  5. That UID is used as user_id throughout the entire system

Local dev:
  Set GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
  Download from: Firebase Console → Project Settings → Service Accounts → Generate key

Cloud Run:
  Uses the instance's default service account automatically (no key file needed).
  Make sure the service account has the "Firebase Authentication Admin" role.
"""

import logging
import firebase_admin
from firebase_admin import credentials, auth
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger("uckhabar.auth")

# ---------------------------------------------------------------------------
# Firebase Admin SDK initialisation
# ---------------------------------------------------------------------------

def _init_firebase() -> None:
    """
    Initialise Firebase Admin SDK once.
    - On Cloud Run: uses the VM's default service account (no config needed).
    - Locally: reads GOOGLE_APPLICATION_CREDENTIALS env var pointing to a
               service account JSON file.
    We explicitly pass the project ID so the SDK doesn't have to auto-discover
    it (auto-discovery can fail on some Cloud Run configurations).
    """
    if firebase_admin._apps:
        return   # already initialised

    import os
    project_id = os.environ.get("GCP_PROJECT_ID")

    try:
        cred = credentials.ApplicationDefault()
        options = {"projectId": project_id} if project_id else {}
        firebase_admin.initialize_app(cred, options)
        logger.info(
            f"Firebase Admin SDK initialised "
            f"(project={project_id or 'auto-detected'})"
        )
    except Exception as e:
        logger.error(f"Firebase Admin SDK init failed: {e}")
        raise RuntimeError(
            "Could not initialise Firebase. "
            "Set GOOGLE_APPLICATION_CREDENTIALS to your service account JSON path, "
            "or run on Cloud Run where credentials are automatic."
        ) from e


_init_firebase()

# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------

_bearer_scheme = HTTPBearer()


async def get_current_user(
    http_creds: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> dict:
    """
    FastAPI dependency — call this on any endpoint that requires authentication.

    Usage:
        @app.get("/feed/me")
        async def get_feed(user = Depends(get_current_user)):
            uid = user["uid"]
            ...

    Returns a dict with:
        uid     — Firebase UID (used as user_id everywhere in UCKhabar)
        email   — user's Google email
        name    — user's Google display name
        picture — profile picture URL
    """
    token = http_creds.credentials

    try:
        decoded = auth.verify_id_token(token)
        return {
            "uid":     decoded["uid"],
            "email":   decoded.get("email"),
            "name":    decoded.get("name"),
            "picture": decoded.get("picture"),
        }
    except auth.ExpiredIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired. Please sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except auth.RevokedIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token revoked. Please sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except auth.InvalidIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        logger.warning(f"Token verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed.",
            headers={"WWW-Authenticate": "Bearer"},
        )
