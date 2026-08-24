**Problem 8**
**
I’m keeping this focused on the safest near-term operational fix for the insecure defaults without changing the project’s design or introducing a large security rewrite.

Problem eight is a **production safety problem**, not just a configuration issue.

**Best immediate solution:** fail startup when running outside local development if any insecure default is still in use.

Recommended policy:

- Keep the current `.env` defaults for local development only.
- Add a startup guard:
  - if `APP_ENV` or `DEBUG` indicates production, reject startup if:
    - `SECRET_KEY` is still the default value
    - `SEED_ADMIN_PASSWORD` is still the default value
    - `SEED_ADMIN_EMAIL` is still the default
- Also disable seed-admin creation in production by default.

This is the best short-term fix because it:
- prevents accidental deployment with “known secret” values
- keeps local dev easy
- avoids forcing a full secret-management system immediately
- gives a clear fail-fast signal before the service starts

A practical rule:

```python
if settings.debug is False and settings.secret_key == "change-me-to-a-long-random-string":
    raise RuntimeError("Production secret key is not configured")
```

For the time being, a `.env` file with real secrets plus a startup validation check is the most sensible solution. Later, you can move to a secret manager such as Docker secrets, Kubernetes secrets, Vault, or Azure Key Vault.
**

** Try to fix the issue and after fixing give a step by step documentation how did you solve . Don't make the doc large just provide point to point info. 
**



**Solution:**
**
Viewed config.py:1-47
Viewed main.py:1-89
Edited main.py
Edited config.py

I have implemented the startup guard to fail-fast if insecure defaults are detected outside of local development. Here is the step-by-step documentation of the solution:

### How the Issue Was Solved (Production Safety Guard)

1. **Created a Startup Safety Check:**
   - Added a `_check_production_safety()` function in `app/main.py`.
   - The function immediately returns if `settings.debug` is `True` (allowing local development to proceed as normal).
   - If `settings.debug` is `False` (production mode), the function checks `settings.secret_key`, `settings.seed_admin_password`, and `settings.seed_admin_email`. If any of these still contain their `.env.example` insecure default values, it explicitly raises a `RuntimeError` to halt application startup.

2. **Wired Safety Check to Lifespan:**
   - Invoked `_check_production_safety()` at the very beginning of the FastAPI `@asynccontextmanager async def lifespan(app: FastAPI)` function. This guarantees the service refuses to start and immediately alerts operators if production secrets are missing.

3. **Disabled Seed Admin by Default in Production:**
   - Modified `app/core/config.py` to change `seed_admin` from a hardcoded `True` to `bool | None = None`. 
   - Updated `_seed_admin()` in `app/main.py` to evaluate `should_seed`. If `seed_admin` isn't explicitly defined in the environment, it falls back to matching the `debug` setting (meaning seed admin creation is enabled locally, but completely disabled in production by default).
   **