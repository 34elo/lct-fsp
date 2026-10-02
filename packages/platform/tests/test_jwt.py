from datetime import timedelta

import pytest
from fsp_platform.jwt import TokenError, decode_token, encode_token


def test_roundtrip():
    tok = encode_token("s" * 32, "u1", "candidate")
    assert decode_token("s" * 32, tok)["sub"] == "u1"


def test_wrong_secret_and_expired():
    with pytest.raises(TokenError):
        decode_token("o" * 32, encode_token("s" * 32, "u1", "candidate"))
    with pytest.raises(TokenError):
        decode_token("s" * 32, encode_token("s" * 32, "u1", "candidate", ttl=timedelta(seconds=-5)))
