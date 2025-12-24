import os
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import secrets

security = HTTPBasic()

def basic_auth(credentials: HTTPBasicCredentials = Depends(security)):
    correct_password = os.getenv("ADMIN_PASSWORD")
    if not correct_password:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server misconfigured: ADMIN_PASSWORD not set",
        )

    if not secrets.compare_digest(credentials.password, correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

