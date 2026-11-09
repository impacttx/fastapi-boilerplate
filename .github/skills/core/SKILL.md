# FastAPI Boilerplate API Core Skills

## Purpose

Document shared settings, error handling, terms and conditions, URL preview, and core utilities.

## Entry Points

- app/core/config.py: settings, upload paths, MIME allowlist.
- app/core/odms.py: TermsAndConditions and TnCModule.
- app/core/routes.py: terms-and-conditions and url-preview endpoints.
- app/core/schemas.py: shared response models.
- app/core/errors.py: error models and exception handlers.
- app/core/utils/redis.py: OTP storage and token blocklist.

## Terms and Conditions

- GET /v1/core/terms-and-conditions returns latest active TnC for a module.
- TnC modules: chat, matrimonial.

## URL Preview

- GET /v1/core/url-preview uses linkpreview to fetch metadata.
- Returns title, description, image, favicon, site name.

## Uploads and Media

- Upload directories are created at startup under uploads/.
- MIME allowlist and disallowed document types in config.py.

## Error Handling

- Common errors are normalized via register_all_errors.
- AccessTokenRequired, RefreshTokenRequired, InvalidToken map to 401.

## Tests

- Add core route tests under tests/unit_tests or integration_tests.

## Gotchas

- Settings are case sensitive and required env vars must be present.
- URL preview errors return 204 with an error detail message.

## Change Tips

- When adding new modules, update TnCModule enum and any dependent logic.
- If you change upload paths, update static mount and any mobile URLs.
