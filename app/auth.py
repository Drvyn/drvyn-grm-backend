import json
import firebase_admin
from firebase_admin import credentials, auth
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Annotated

# --- Settings ---
class AuthSettings(BaseSettings):
    FIREBASE_SERVICE_ACCOUNT_JSON: str
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = AuthSettings()

# --- Firebase Initialization ---
try:
    # Get the value from the environment variable
    service_account_value = settings.FIREBASE_SERVICE_ACCOUNT_JSON

    # LOGIC: Check if it's a JSON string (for Render/Vercel) or a file path (local)
    if service_account_value.strip().startswith("{"):
        # It is a JSON string. Parse it.
        cred_dict = json.loads(service_account_value)
        
        # --- CRITICAL FIX FOR RENDER/VERCEL ---
        # The private_key often has escaped newlines (\\n) instead of real newlines (\n).
        # We must replace them for the Firebase SDK to accept the key.
        if "private_key" in cred_dict:
            cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")
            
        cred = credentials.Certificate(cred_dict)
    else:
        # It is a file path (e.g., "serviceAccountKey.json" for local dev)
        cred = credentials.Certificate(service_account_value)

    # Initialize Firebase if it hasn't been initialized yet
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
        print("Firebase Admin SDK initialized successfully.")

except ValueError as e:
    print(f"CRITICAL ERROR: Invalid JSON in FIREBASE_SERVICE_ACCOUNT_JSON. {e}")
except Exception as e:
    # This catches other init errors preventing the 500 crash loop
    print(f"CRITICAL ERROR: Failed to initialize Firebase: {e}")


# --- Authentication Dependency ---
auth_scheme = HTTPBearer()

async def get_current_user(token: HTTPAuthorizationCredentials = Depends(auth_scheme)) -> dict:
    """
    Verifies the Firebase ID token and returns the user's UID and email.
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization token not provided",
        )
    
    try:
        # Verify the token
        decoded_token = auth.verify_id_token(token.credentials)
        
        return {
            "uid": decoded_token["uid"],
            "email": decoded_token.get("email", "")
        }
        
    except auth.ExpiredIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )
    except auth.InvalidIdTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {e}",
        )
    except Exception as e:
        # This catches errors if Firebase wasn't initialized
        print(f"Authentication Error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error: Authentication service failed.",
        )

AuthUser = Annotated[dict, Depends(get_current_user)]