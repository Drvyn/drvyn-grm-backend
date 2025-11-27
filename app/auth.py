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

    # LOGIC: Check if it's a JSON string or a file path
    if service_account_value.strip().startswith("{"):
        # It looks like JSON content, parse it into a dictionary
        cred_dict = json.loads(service_account_value)
        cred = credentials.Certificate(cred_dict)
    else:
        # It doesn't look like JSON, assume it is a file path
        cred = credentials.Certificate(service_account_value)

    firebase_admin.initialize_app(cred)
    print("Firebase Admin SDK initialized successfully.")

except ValueError as e:
    print(f"Error initializing Firebase Admin SDK: {e}. Is `FIREBASE_SERVICE_ACCOUNT_JSON` correct?")
except Exception as e:
    print(f"An unexpected error occurred during Firebase init: {e}")


# --- Authentication Dependency ---
auth_scheme = HTTPBearer()

async def get_current_user(token: HTTPAuthorizationCredentials = Depends(auth_scheme)) -> dict:
    """
    A FastAPI dependency that verifies the Firebase ID token in the
    Authorization header and returns the user's data (including UID).
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization token not provided",
        )
    
    try:
        # Verify the token
        decoded_token = auth.verify_id_token(token.credentials)
        
        # Return the user's UID and email
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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred during authentication: {e}",
        )

# --- Annotated User Type ---
# This is a shorthand you can use in your endpoint functions
# e.g., async def my_endpoint(user: AuthUser):
AuthUser = Annotated[dict, Depends(get_current_user)]
