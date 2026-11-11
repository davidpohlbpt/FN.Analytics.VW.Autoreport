import requests


def send_request(
    session: requests.Session,
    url: str,
    headers: dict,
    method: str = "GET",
    json: dict | None = None,
) -> dict:
    response = session.request(
        method=method,
        url=url,
        headers=headers,
        json=json,
    )
    response.raise_for_status()
    return response.json()
