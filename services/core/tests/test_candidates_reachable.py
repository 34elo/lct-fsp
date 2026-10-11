"""Профиль без ФИО и контактов скрыт от работодателей, демо-аккаунты видны."""

from app.candidates import service


def test_publishable_requires_contacts_only_when_enabled(monkeypatch):
    monkeypatch.setattr(service, "_require_contacts", lambda: False)
    assert "full_name_enc" not in str(service._publishable())
    monkeypatch.setattr(service, "_require_contacts", lambda: True)
    sql = str(service._publishable())
    assert "full_name_enc" in sql and "contacts_enc" in sql and "is_demo" in sql
