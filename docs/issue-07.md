**Problem 7**
**
I’m focusing on the smallest operational fix that improves reliability without changing the project’s overall design.

Problem seven is a classic operational gap: the app reports itself as healthy even when Postgres or Redis is down.

**Best immediate solution:** add a separate readiness endpoint that checks both dependencies, while keeping `/health` as a simple liveness check.

Recommended pattern:

- `/health` → returns `200` if the process is running
- `/health/ready` → checks:
  - PostgreSQL connectivity
  - Redis connectivity
  - optionally the Lua script is loaded
- Return:
  - `200 OK` when ready
  - `503 Service Unavailable` when either dependency is failing

This is the best short-term fix because it:
- requires minimal code
- gives Kubernetes/Docker/LoadBalancer better lifecycle control
- prevents false positives during outages
- preserves the current API without major redesign

A practical implementation is:
- open a short async DB connection
- run `SELECT 1`
- ping Redis
- if either fails, return `503`

This should be the first operational improvement added before production deployment, because it gives a much clearer signal than a generic `200 OK` on `/health`.
**

** Try to fix the issue and after fixing give a step by step documentation how did you solve . Don't make the doc large just provide point to point info. 
**


**Solution:**
**
Viewed main.py:1-74
Viewed redis.py:1-30
Viewed database.py:1-53
Edited main.py
Ran command: `.venv\Scripts\ruff.exe check app/main.py`

I've added the `/health/ready` endpoint as requested. Here is the step-by-step documentation of the solution:

### How the Issue Was Solved (Readiness Probe)

1. **Imported Required Dependencies:** 
   - Updated `app/main.py` imports to include `Response` and `status` from `fastapi`.
   - Imported `text` from `sqlalchemy` to allow raw SQL execution.
   - Imported `get_db_context` and `get_redis` to access our datastores.

2. **Added the `/health/ready` Endpoint:**
   - Created a new `GET` route at `/health/ready` next to the existing liveness `/health` check.

3. **Implemented PostgreSQL Connectivity Check:**
   - Wrapped the check in a `try...except` block.
   - Opened a short async database session using `async with get_db_context() as session:`.
   - Executed a simple `SELECT 1` query (`await session.execute(text("SELECT 1"))`) to verify the database is reachable and responsive.

4. **Implemented Redis Connectivity Check:**
   - Retrieved the global Redis client via `get_redis()`.
   - Executed a lightweight `await redis.ping()` command to verify Redis is up.

5. **Configured Status Codes:**
   - If both checks pass, the endpoint returns a `200 OK` with `{"status": "ready"}`.
   - If an `Exception` is caught from either the DB or Redis, the `response.status_code` is explicitly set to `503 Service Unavailable`, and it returns the error details.
   **