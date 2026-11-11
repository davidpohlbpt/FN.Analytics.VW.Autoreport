import os

import requests

BASE_URL = os.getenv("base_request_url")
USERNAME = os.getenv("username")
PASSWORD = os.getenv("password")


def get_session() -> requests.Session:
    """Log in and return an authenticated session that carries the auth cookie."""
    session = requests.Session()

    payload = {"username": USERNAME, "password": PASSWORD}

    response = session.post(
        f"https://{BASE_URL}/api/login",
        json=payload,
        headers={"Accept": "application/json"},
    )
    response.raise_for_status()

    token = response.json()["value"]["accessToken"]
    session.headers.update({"Authorization": f"Bearer {token}"})

    return session
