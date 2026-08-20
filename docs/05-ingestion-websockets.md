# Step 5 — High-throughput ingestion and WebSockets

## HTTP ingest

| Method | Path | Auth | Behavior |
| --- | --- | --- | --- |
| `POST` | `/api/v1/events` | `ingest_writer` | Single row insert + Pub/Sub publish |
| `POST` | `/api/v1/events/batch` | `ingest_writer` | `insert(EventLog)` with 1–1000 mappings |
| `GET` | `/api/v1/events` | `viewer` | Recent events (admins see all users) |

Batch insert path (`app/services/events.py`) avoids ORM unit-of-work overhead. After commit, events are published on Redis channel `events:stream` (override with `REDIS_EVENTS_CHANNEL`) using a non-transactional pipeline.

Example:

```powershell
$login = Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/v1/auth/login -ContentType "application/x-www-form-urlencoded" -Body "username=admin@local.dev&password=adminadmin"
$headers = @{ Authorization = "Bearer $($login.access_token)" }
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/v1/events/batch -Headers $headers -ContentType "application/json" -Body '{"events":[{"event_type":"signup","payload":{"plan":"free"}}]}'
```

## WebSocket stream

`WS /api/v1/events/stream?token=<jwt>`

1. Token is checked for `viewer` (or `admin`) **before** `accept()`. Invalid tokens close with policy-violation `1008`.
2. A dedicated Redis Pub/Sub subscription is opened (Pub/Sub cannot share a connection that also runs `GET`/`SET`).
3. Each published JSON message is forwarded to the socket.
4. A parallel task waits on client frames so a disconnect unsubscribes promptly.

Subscribe with any WebSocket client, for example:

```javascript
const ws = new WebSocket("ws://localhost:8000/api/v1/events/stream?token=" + accessToken);
ws.onmessage = (ev) => console.log(JSON.parse(ev.data));
```
