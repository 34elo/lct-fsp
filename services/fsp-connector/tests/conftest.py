import httpx
import pytest
from fsp_connector.http_adapter import HttpFspAdapter
from fsp_mock.config import Settings as MockSettings
from fsp_mock.data import build_store
from fsp_mock.main import build_app

KEY = "k"


async def no_sleep(_: float) -> None:
    return None


@pytest.fixture
def mock_store():
    return build_store()


@pytest.fixture
def mock_app(mock_store):
    return build_app(MockSettings(fsp_mock_api_key=KEY, fsp_webhook_url=None), mock_store)


@pytest.fixture
async def adapter(mock_app):
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=mock_app), base_url="http://mock")
    a = HttpFspAdapter(
        "http://mock",
        KEY,
        client=client,
        public_url="https://mock.example",
        oauth_redirect_uri="https://api.example/cb",
        sleep=no_sleep,
    )
    yield a
    await a.aclose()
