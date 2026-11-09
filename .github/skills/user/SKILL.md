# FastAPI Boilerplate API User Skills

## Purpose

Document user profile management, terms acceptance, device registration, and profile images.

## Entry Points

- app/user/routes.py: profile CRUD, TnC acceptance, profile picture upload, lookup.
- app/user/device_routes.py: device registration and push token updates.
- app/user/schemas.py: payloads and response models.
- app/auth/odms.py: User and UserDevice documents.

## Profile Flow

- /v1/user/tnc: accept terms for module and revision.
- /v1/user/profile: get, update (PUT), patch (PATCH), and delete.
- /v1/user/profile-picture: upload profile image to S3 or local storage.
- /v1/user/profiles/lookup: lookup by mobile numbers or user IDs.

## Device Registration

- /v1/devices/register: register or update device with push tokens.
- /v1/devices/voip-token: update iOS VoIP token.
- /v1/devices/{device_id}: unregister device on logout.

## Data Models

- User: profile fields and accepted terms.
- UserDevice: device_id, platform, expo/voip/fcm tokens.

## Tests

- Add user endpoint tests under tests/unit_tests or integration_tests.
- Use factories for User and UserDevice where possible.

## Gotchas

- TnC must be accepted before profile endpoints will succeed.
- Deprecated push-token endpoints still exist, but devices/register is preferred.
- Profile picture URL uses settings.CDN_ENDPOINT_URL prefix.

## Change Tips

- Keep user schemas in sync with mobile user profile expectations.
- When changing device registration, update mobile deviceService and voipPushService.
