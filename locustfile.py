import os

from locust import HttpUser, between, task


class IngestUser(HttpUser):
    wait_time = between(0.01, 0.05)

    def on_start(self):
        email = os.getenv("LOADTEST_EMAIL", "admin@local.dev")
        password = os.getenv("LOADTEST_PASSWORD", "adminadmin")
        response = self.client.post(
            "/api/v1/auth/login",
            data={"username": email, "password": password},
        )
        response.raise_for_status()
        token = response.json()["access_token"]
        self.client.headers.update({"Authorization": f"Bearer {token}"})

    @task(8)
    def ingest_one(self):
        with self.client.post(
            "/api/v1/events",
            json={"event_type": "load.ping", "payload": {"src": "locust"}},
            catch_response=True,
        ) as response:
            if response.status_code == 429:
                response.success()
            elif response.status_code >= 400:
                response.failure(f"ingest failed: {response.status_code}")

    @task(2)
    def ingest_batch(self):
        with self.client.post(
            "/api/v1/events/batch",
            json={
                "events": [
                    {"event_type": "load.batch", "payload": {"i": 0}},
                    {"event_type": "load.batch", "payload": {"i": 1}},
                ]
            },
            catch_response=True,
        ) as response:
            if response.status_code == 429:
                response.success()
            elif response.status_code >= 400:
                response.failure(f"batch failed: {response.status_code}")
