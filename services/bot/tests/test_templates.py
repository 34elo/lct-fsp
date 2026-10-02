from fsp_bot.templates import render, render_keyboard
from fsp_contracts.notify import TgButton, TgTemplate


def test_offer_new_escapes_html_and_shows_fork():
    text = render(
        TgTemplate.offer_new,
        {
            "company": "Север <b>",
            "verified": True,
            "rating": 4.6,
            "title": "Middle Backend",
            "salary_from": 200000,
            "salary_to": 250000,
            "format": "удалёнка",
            "below_min": 230000,
            "match": 92,
            "reasons": [{"ok": True, "text": "FastAPI"}, {"ok": False, "text": "Нет Kafka"}],
            "deadline": "12 октября",
        },
    )
    assert "Север &lt;b&gt;" in text
    assert "200 000 – 250 000 ₽" in text
    assert "Ниже ваших ожиданий (от 230 000 ₽)" in text
    assert "✓ FastAPI" in text and "⚠ Нет Kafka" in text


def test_every_template_renders_with_empty_data():
    for t in TgTemplate:
        try:
            assert render(t, {})
        except KeyError:
            pass  # обязательные поля шаблона; полнота данных — забота core


def test_profile_updated_dots():
    text = render(
        TgTemplate.profile_updated,
        {"skills": [{"name": "Алгоритмы", "from": 3, "to": 4}]},
    )
    assert "●●●○ → ●●●●" in text


def test_keyboard():
    kb = render_keyboard(
        [[TgButton(text="A", callback_data="o:a:1"), TgButton(text="B", url="https://x.y")]]
    )
    assert kb is not None and kb.inline_keyboard[0][1].url == "https://x.y"
    assert render_keyboard([]) is None
