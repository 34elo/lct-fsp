from fsp_bot.config import Settings
from fsp_bot.main import make_bot

TOKEN = "123456:TEST"


def test_default_api_server() -> None:
    bot = make_bot(Settings(tg_bot_token=TOKEN))
    assert bot.session.api.base.startswith("https://api.telegram.org/")


def test_relay_api_server() -> None:
    bot = make_bot(Settings(tg_bot_token=TOKEN, tg_api_base="http://100.66.64.126:28443/"))
    assert bot.session.api.api_url(TOKEN, "getMe") == f"http://100.66.64.126:28443/bot{TOKEN}/getMe"
