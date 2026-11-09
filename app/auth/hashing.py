# Modern password/content hashing via pwdlib (Argon2id).
# Parameters meet OWASP Argon2id minimum recommendations:
#   time_cost   >= 2 iterations
#   memory_cost >= 19 456 KiB (19 MB), preferably 64 MB
#   \parallelism >= 1
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError
from pwdlib.hashers.argon2 import Argon2Hasher

_password_hash = PasswordHash(
    (
        Argon2Hasher(
            time_cost=2,  # Iterations (OWASP min: 2)
            memory_cost=64 * 1024,  # 64 MiB (OWASP min: ~19 MiB)
            parallelism=2,  # Number of parallel threads
        ),
    )
)


def hash_content(password: str) -> str:
    """Hash a piece of content (e.g. a password or OTP) using Argon2id."""
    return _password_hash.hash(password)


def verify_content(plain_password: str, hashed_password: str) -> bool:
    """Verify a piece of content against its Argon2id hash.

    Returns ``False`` on mismatch or when the stored hash cannot be
    identified, rather than raising, so callers can treat any failure
    uniformly as an invalid credential.
    """
    try:
        return _password_hash.verify(plain_password, hashed_password)
    except UnknownHashError:
        return False
