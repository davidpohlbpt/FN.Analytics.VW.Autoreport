import pytest
import requests
from pycore import easy

from pptcreator.utils.get_session import get_session


@pytest.fixture
def credentials(monkeypatch):
    monkeypatch.setattr("pptcreator.utils.get_session.USERNAME", "test-user")
    monkeypatch.setattr("pptcreator.utils.get_session.PASSWORD", "test-pass")


def test_get_session(mocker, credentials):

    # -------------------------------- Arrange --------------------------------- #
    mock_response = mocker.Mock()
    mock_response.json.return_value = {"value": {"accessToken": "test-token"}}
    mock_response.raise_for_status.return_value = None
    mock_post = mocker.patch.object(
        requests.Session, "post", return_value=mock_response
    )

    # ---------------------------------- Act ----------------------------------- #
    session = get_session()

    # -------------------------------- Assert ---------------------------------- #
    assert session.headers["Authorization"] == "Bearer test-token"
    mock_response.raise_for_status.assert_called_once()
