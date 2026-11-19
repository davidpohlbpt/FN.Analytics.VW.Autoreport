import json
import urllib.parse
import urllib.request


def get_token(tenant_id, client_id, client_secret):
    token_url = f"https://login.microsoftonline.com/{urllib.parse.quote(tenant_id, safe='')}/oauth2/v2.0/token"

    token_data = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "https://graph.microsoft.com/.default",
    }).encode("utf-8")

    request = urllib.request.Request(token_url, data=token_data, method="POST")
    with urllib.request.urlopen(request, timeout=60) as response:
        access_token = json.loads(response.read())["access_token"]

    return access_token
