# Step 3 — JWT authentication and RBAC

## Password hashing and tokens

`app/core/security.py`:

- **passlib + bcrypt** for password hashes (`hash_password` / `verify_password`)
- **python-jose** HMAC-SHA256 JWTs (`create_access_token` / `decode_token`)

Each access token carries `sub` (user UUID), `role`, `scopes`, `iat`, and `exp`.

## Roles and scopes

| Role | Scopes issued |
| --- | --- |
| `admin` | `admin`, `ingest_writer`, `viewer` |
| `ingest_writer` | `ingest_writer`, `viewer` |
| `viewer` | `viewer` |

`require_scopes("ingest_writer")` guards write routes. Admins skip the check. Viewers can list events and open the WebSocket stream but cannot ingest.

## How a request is authenticated

`get_current_principal` in `app/api/deps.py` accepts **either**:

1. `Authorization: Bearer <jwt>` (OAuth2 password flow via `POST /api/v1/auth/login`)
2. `X-API-Key: eik_...` (hashed with SHA-256 and looked up in `api_keys`)

Swagger UI uses the OAuth2 password flow against `/api/v1/auth/login`.

## Routes

| Method | Path | Notes |
| --- | --- | --- |
| `POST` | `/api/v1/auth/register` | First `admin` may self-register; later admins are rejected |
| `POST` | `/api/v1/auth/login` | Form body: `username` (email) + `password` |
| `GET` | `/api/v1/auth/me` | Current principal |
| `POST` | `/api/v1/auth/api-keys` | Returns the raw key **once** |
| `GET` | `/api/v1/auth/api-keys` | Metadata only (hash is never returned) |

On startup, if `SEED_ADMIN=true` and the seed email is missing, lifespan inserts a local admin so you can log in immediately after `alembic upgrade head`.
