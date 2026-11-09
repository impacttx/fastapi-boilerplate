# FastAPI Boilerplate API Agent Skills

## Purpose
Provide enough context for AI coding assistants to work on the backend safely, especially auth, chat websockets, and push/call flows.

## Quick Mental Model
- FastAPI app with Beanie ODM (MongoDB) and Redis for auth and ephemeral data.
- REST endpoints under /v1 for auth, users, devices, chat, etc.
- WebSocket channel for chat and call signaling.
- Push delivery is split by platform: Expo for Android, APNS VoIP for iOS.

## Code Map (Entry Points)
- app/main.py: Router wiring and health endpoints; mounts /v1.
- app/app.py: FastAPI app config, middleware, DB init, lifespan cleanup.
- app/core/config.py: Settings and env vars (case sensitive).
- app/auth/routes.py: OTP and login flows.
- app/chat/routes.py: WebSocket endpoint and chat REST endpoints.
- app/chat/messaging.py: WebSocket dispatch, presence, pending call signals.
- app/user/device_routes.py: Push token and device registration.
- app/core/utils/expo_push.py: Android call notifications via Expo.
- app/core/utils/voip_push.py: iOS VoIP push via APNS.
- app/core/utils/push_service.py: General message push via Expo.

## Auth Flow (OTP + JWT)
- /v1/auth/get_otp: Generates OTP, stores hash in Redis, sends OTP out of band.
- /v1/auth/register: Verifies OTP, creates new user, issues access/refresh tokens.
- /v1/auth/login: Verifies OTP, logs in existing user, issues access/refresh tokens.
- /v1/auth/refresh_token: Rotates tokens and blocklists old JTI in Redis.
- /v1/auth/logout: Blocklists access token JTI.

## Chat + WebSocket Flow
- WebSocket endpoint: /v1/chat/{user_id} (see app/chat/routes.py).
- Client sends heartbeat every 30s; server timeout is 45s.
- Key event types (see app/chat/messaging.py):
  - message, typing, read_receipt, delivery_receipt, delete_message
  - offer, answer, candidate, end_call, decline_call (call signaling)
  - presence_subscription, presence_update
- Pending call signals for offline users are stored server-side and delivered when they reconnect.
  - This avoids exceeding FCM 4 KB payload limits.

## Notifications + Device APIs
- Device registration endpoints in app/user/device_routes.py.
- Expo push is used for Android; APNS VoIP is used for iOS.
- Message notifications use Expo (app/core/utils/push_service.py).
- Call notifications use:
  - Expo for Android (app/core/utils/expo_push.py)
  - APNS VoIP for iOS (app/core/utils/voip_push.py)

## Push + Call Notifications
- Android: Expo push (app/core/utils/expo_push.py) with type=call and channelId=calls.
- iOS: APNS VoIP push (app/core/utils/voip_push.py) with apns-topic bundleId.voip.
- General message pushes: app/core/utils/push_service.py.
- Critical fields: payload type must be call for incoming call handling on mobile.

## Device Registration (Push Tokens)
- /v1/devices/register: register or update device + expo/voip tokens.
- /v1/devices/voip-token: update iOS VoIP token.
- /v1/devices/{device_id}: unregister on logout.

## Data Storage
- MongoDB (Beanie): users, chat rooms, messages, uploads, matrimonial data, world data.
- Redis: OTP, token blocklist, transient auth data.
- uploads/: media and documents; mounted at /user-contents.

## Matrimonial
- Routes: app/matrimonial/routes.py (CRUD for profiles, favorites, search).
- ODMs in app/matrimonial/odms.py.
- Uploaded profile images are stored under uploads/images/matrimonial.

## World (Countries / States / Cities)
- Routes: app/world/routes.py.
- Uses separate MongoDB database name "world" in app/app.py init_db.

## Uploads + Media
- MIME allowlist and upload directory mapping in app/core/config.py.
- File validation in app/chat/helper.py and file ODM in app/chat/odms.py.
- Public file access via /user-contents static mount.

## Migrations + Seed Data
- Beanie migrations under fastapi-boilerplate/migrations/.
- Seed and initial data helpers live in app/initial_data.py.

## Configuration (Env Var Names Only)
Defined in app/core/config.py (case sensitive):
- SECRET_KEY, PROJECT_NAME, ENVIRONMENT, LOG_LEVEL, DEBUG
- ALLOWED_CORS_ORIGINS, TRUSTED_HOSTS
- MONGO_DB, MONGO_URI, REDIS_URI
- JWT_PRIVATE_KEY, JWT_PUBLIC_KEY, JWT_ALGORITHM, JWT_EXPIRY_TIME, JWT_REFRESH_EXPIRY_TIME
- JWT_AUDIENCE, JWT_ISSUER, JWT_AUTH_URL, AUTH_TOKEN_URL, OTP_EXPIRY_MINUTES
- AWS_S3_BUCKET_NAME, AWS_REGION_NAME, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, CDN_ENDPOINT_URL
- APNS_KEY_ID, APNS_TEAM_ID, APNS_BUNDLE_ID, APNS_AUTH_KEY, APNS_USE_SANDBOX
- LOGFIRE_TOKEN, ROLLBAR_ACCESS_TOKEN

## Run / Debug / Tests
- Local dev: docker compose up --build (see fastapi-boilerplate/README.md).
- DB migrations: beanie migrate and beanie new-migration.
- Tests: pytest (see pyproject.toml for flags).

## Known Gotchas
- Python version mismatch: README references 3.12/3.14; pyproject requires 3.14.
- WebSocket timeout assumes 30s client heartbeat; do not change without updating client.
- Call payloads must avoid large SDP in push payloads due to FCM size limits.
- Settings are case sensitive; ensure env names match exactly.

## Agent Tips (Safe Changes)
- When changing auth: update both OTP flow and token creation/refresh; keep Redis blocklist.
- When changing chat event shapes: update app/chat/schemas.py and mobile WS handlers together.
- For calls: keep type=call and channelId=calls in push payloads.
- For uploads: ensure MIME checks in app/chat/helper and upload paths in config are aligned.
