import pytest

from core.types import Caller


@pytest.fixture
def teller() -> Caller:
    return Caller(id="S001", role="teller", audience="staff", attributes={"branch": "ACC-01"})
