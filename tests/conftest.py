import datetime as dt
import tempfile

import pytest
from pycore.resources.file import FileStorage
from pycore.testing.unit import *

from pptcreator.config import settings


@pytest.fixture
def load_date():
    return dt.date(2020, 1, 1)


@pytest.fixture
def load_id():
    return 1000


@pytest.fixture
def entity_id():
    return 1


@pytest.fixture
def test_dir():
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield tmp_dir


@pytest.fixture
def storage(test_dir):
    return FileStorage(root_dir=test_dir)


@pytest.fixture
def cont(storage):
    cont = settings.storage_container
    (storage.root_dir / cont).mkdir()
    return cont
