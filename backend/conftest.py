import pytest
from asgiref.sync import sync_to_async
from django.db import connections


@pytest.fixture(autouse=True)
async def close_worker_connections():
    """Close the database connection held by asgiref's worker thread after each test.

    The adapters run ORM queries through `sync_to_async`, which uses one long-lived worker
    thread. Its connection would otherwise stay open and stop the test database being dropped.
    """
    yield
    await sync_to_async(connections.close_all)()
