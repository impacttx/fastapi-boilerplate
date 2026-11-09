import secrets
from typing import Any

from itsdangerous import URLSafeTimedSerializer
from loguru import logger

from app.settings import settings


def generate_otp() -> str:
    """
    Generate a cryptographically secure 6-digit one-time password (OTP).
    """
    return "".join([str(secrets.randbelow(10)) for _ in range(6)])


async def send_otp(mobile_number: str, otp: str) -> None:
    """
    Send an OTP to the user's mobile number.
    """
    # TODO: Integrate SMS gateway (e.g. Twilio, AWS SNS) to deliver OTP
    logger.info(f"[OTP] Sending OTP to {mobile_number}")


# Use SECRET_KEY (not a public key) as the HMAC secret for URL-safe tokens
serializer = URLSafeTimedSerializer(
    secret_key=settings.SECRET_KEY.get_secret_value(),
    salt="email-configuration",
)


def create_url_safe_token(data: dict[str, Any]) -> str:
    return serializer.dumps(data)


def decode_url_safe_token(token: str):
    try:
        return serializer.loads(token)
    except Exception as e:  # noqa: BLE001
        logger.error(str(e))
