import json
import firebase_admin
from firebase_admin import credentials, auth
from fastapi import Depends, HTTPException, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Annotated, Optional

# --- Settings ---
class AuthSettings(BaseSettings):
    FIREBASE_SERVICE_ACCOUNT_JSON: str
    ADMIN_SECRET_TOKEN: str = "secret-admin-token"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = AuthSettings()

# --- Firebase Initialization ---
try:
    service_account_value = settings.FIREBASE_SERVICE_ACCOUNT_JSON
    if service_account_value.strip().startswith("{"):
        cred_dict = json.loads(service_account_value)
        if "private_key" in cred_dict:
            cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
        cred = credentials.Certificate(cred_dict)
    else:
        cred = credentials.Certificate(service_account_value)

    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
        print("Firebase Admin SDK initialized successfully.")

except ValueError as e:
    print(f"CRITICAL ERROR: Invalid JSON in FIREBASE_SERVICE_ACCOUNT_JSON. {e}")
except Exception as e:
    print(f"CRITICAL ERROR: Failed to initialize Firebase: {e}")


# --- Authentication Dependencies ---
auth_scheme = HTTPBearer()
# Optional auth scheme to allow either Bearer token OR Admin Header without auto-erroring on missing Bearer
auth_scheme_optional = HTTPBearer(auto_error=False)

async def get_current_user(token: HTTPAuthorizationCredentials = Depends(auth_scheme)) -> dict:
    """Verifies Firebase ID token for Workshop Users."""
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authorization token not provided")
    try:
        decoded_token = auth.verify_id_token(token.credentials)
        return {"uid": decoded_token["uid"], "email": decoded_token.get("email", "")}
    except Exception as e:
        print(f"Authentication Error: {e}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {e}")

async def verify_admin(x_admin_token: Optional[str] = Header(None)) -> bool:
    """Verifies Admin Secret Token."""
    if x_admin_token != settings.ADMIN_SECRET_TOKEN:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Admin Token")
    return True

async def get_current_user_or_admin(
    token: Optional[HTTPAuthorizationCredentials] = Depends(auth_scheme_optional),
    x_admin_token: Optional[str] = Header(None)
) -> dict:
    """
    Authenticates either an Admin (via header) or a Workshop User (via Bearer token).
    Returns a dict with 'role' ('admin' or 'workshop') and 'uid'.
    """
    # 1. Check Admin Token
    if x_admin_token == settings.ADMIN_SECRET_TOKEN:
        return {"uid": "admin_static_user_001", "role": "admin", "email": "admin@drvyn.com"}
    
    # 2. Check Bearer Token
    if token:
        try:
            decoded_token = auth.verify_id_token(token.credentials)
            return {"uid": decoded_token["uid"], "role": "workshop", "email": decoded_token.get("email", "")}
        except Exception:
            pass # Invalid token, fall through to error
            
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized: Invalid credentials")

AuthUser = Annotated[dict, Depends(get_current_user)]
AdminUser = Annotated[bool, Depends(verify_admin)]
UserOrAdmin = Annotated[dict, Depends(get_current_user_or_admin)]