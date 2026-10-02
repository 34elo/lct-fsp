import fakeredis
import pytest
from fsp_connector.cache import CachedFspAdapter
from fsp_connector.config import Settings
from fsp_connector.factory import build_adapter
from fsp_connector.http_adapter import HttpFspAdapter


def test_mock_adapter_selected():
    s = Settings(fsp_adapter="mock")
    assert isinstance(build_adapter(s), HttpFspAdapter)
    assert isinstance(build_adapter(s, fakeredis.FakeAsyncRedis()), CachedFspAdapter)


def test_other_adapters_not_yet():
    with pytest.raises(NotImplementedError):
        build_adapter(Settings(fsp_adapter="organizers"))
