# FastAPI Boilerplate API Auth Skills

## Purpose

Document the OTP login and JWT token flows, plus device registration schemas used by auth endpoints.

## Entry Points

- app/auth/routes.py: /v1/auth/get_otp, /v1/auth/register, /v1/auth/login, /v1/auth/refresh_token, /v1/auth/logout.
- app/auth/security.py: JWT creation/validation and auth guards.
- app/auth/schemas.py: request/response models for OTP and login.
- app/auth/hashing.py: Argon2-based hashing/verification.
- app/auth/utils.py: OTP generator and token helpers (URL-safe serializer).
- app/auth/odms.py: User and UserDevice documents.
- app/core/utils/redis.py: OTP storage and token blocklist.

## Key Flows

- OTP send: /v1/auth/get_otp generates OTP, hashes it, stores it in Redis.
- Register: /v1/auth/register verifies OTP, creates new user, updates last_login, returns access/refresh tokens.
- Login: /v1/auth/login verifies OTP, logs in existing user, updates last_login, returns access/refresh tokens.
- Refresh: /v1/auth/refresh_token blocklists the old JTI and issues new tokens.
- Logout: /v1/auth/logout blocklists current access token JTI.

## JWT Details

- Tokens are created with settings.JWT_PRIVATE_KEY and validated with settings.JWT_PUBLIC_KEY.
- Access vs refresh enforced in AccessTokenBearer and RefreshTokenBearer.
- Token blocklist is stored in Redis by JTI.

## Data Models

- User: mobile number, profile fields, accepted terms, activity timestamps.
- UserDevice: device_id, platform, expo/voip/fcm tokens, active status.

## Tests

- Add or update tests in tests/unit_tests and tests/integration_tests.
- Auth-related fixtures live in tests/fixtures and factories.

## Gotchas

- OTP is returned in response only in development environment.
- Token blocklist is mandatory for refresh/logout safety.
- Device platform is validated against ios/android enum.

## Change Tips

- When changing token claims or expiry, update both creation and validation logic.
- Keep Redis OTP expiry aligned with settings.OTP_EXPIRY_MINUTES.
- If you add new auth endpoints, also add schemas and tests.
