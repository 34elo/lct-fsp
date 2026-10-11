from fsp_bot.templates import render, render_keyboard
from fsp_contracts.notify import TgButton, TgTemplate


def test_offer_new_renders_core_fields():
    """Поля — ровно те, что кладёт `offer_card_data` в core."""
    text = render(
        TgTemplate.offer_new,
        {
            "offer_id": "o1",
            "company_name": "Север <b>",
            "company_responsibility": 4.6,
            "vacancy_title": "Middle Backend",
            "formats": ["remote"],
            "employment_type": "full",
            "salary_from": 200000,
            "salary_to": 250000,
            "message": "Привет <i>!",
            "match_score": 0.92,
            "explanation": [
                {"kind": "plus", "text": "FastAPI"},
                {"kind": "warn", "text": "Нет Kafka"},
            ],
            "below_candidate_min": True,
            "expires_at": "2026-10-12T09:00:00+00:00",
        },
    )
    assert "Север &lt;b&gt;" in text and "(ответственность 4.6/5)" in text
    assert "200 000 – 250 000 ₽" in text and "удалёнка · полная занятость" in text
    assert "⚠ Ниже ваших ожиданий" in text
    assert "Совпадение <b>92%</b>" in text
    assert "✓ FastAPI" in text and "⚠ Нет Kafka" in text
    assert "«Привет &lt;i&gt;!»" in text
    assert "⏳ Ответить до 12 октября" in text


def test_offer_new_minimal_and_status_templates():
    text = render(
        TgTemplate.offer_new,
        {"salary_from": 1, "salary_to": 2, "below_candidate_min": False, "expires_at": "bad"},
    )
    assert "Ниже" not in text and "Совпадение" not in text and "до bad" in text
    assert "принят" in render(
        TgTemplate.offer_updated, {"status": "accepted", "vacancy_title": "X"}
    )
    assert "Вы приняли оффер" in render(TgTemplate.offer_accepted, {"offer_id": "o1"})
    assert "Новое сообщение" in render(TgTemplate.offer_message, {"message_id": "m1"})


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


def test_offer_new_salary_basis_label():
    """Вилка подписана «до НДФЛ» (по умолчанию) или «на руки»."""
    base = {"vacancy_title": "Dev", "salary_from": 100000, "salary_to": 150000}
    assert "150 000 ₽</b> до НДФЛ" in render(TgTemplate.offer_new, base)
    assert "150 000 ₽</b> на руки" in render(TgTemplate.offer_new, base | {"salary_basis": "net"})


def test_regular_task_published_shows_profession_title():
    """Название профессии вместо slug; старые команды без названия — slug."""
    text = render(
        TgTemplate.regular_task_published,
        {"profession": "backend", "profession_title": "Backend-разработчик"},
    )
    assert "Backend-разработчик" in text and "backend" not in text
    assert "backend" in render(TgTemplate.regular_task_published, {"profession": "backend"})
