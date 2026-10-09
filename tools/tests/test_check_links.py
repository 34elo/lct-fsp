"""Проверка ссылок в docs (E39-37): слаги заголовков, файлы, якоря, код не проверяется."""

from pathlib import Path

from tools import check_links as cl


def test_slug_like_github():
    assert cl.slug("7.5. Вайбкодинг по плану (`/vibe`)") == "75-вайбкодинг-по-плану-vibe"
    assert cl.slug("2. Разбор резюме (`ml.parse_resume`)") == "2-разбор-резюме-mlparse_resume"
    assert cl.slug("4.2. Очередь v2: два блока") == "42-очередь-v2-два-блока"


def test_broken_and_ok_links(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(cl, "ROOT", tmp_path)
    (tmp_path / "b.md").write_text("# Заголовок\n\n## Раздел (`x`)\n", encoding="utf-8")
    a = tmp_path / "a.md"
    a.write_text(
        "[ok](b.md#раздел-x) [нет якоря](b.md#нет) [нет файла](c.md)\n"
        "[наружу](https://example.com) [свой](#шапка)\n"
        "# Шапка\n"
        "```\n[в коде](missing.md)\n```\n"
        "`[инлайн](missing.md)`\n",
        encoding="utf-8",
    )
    errors = cl.check_file(a)
    assert len(errors) == 2
    assert "нет якоря #нет" in errors[0]
    assert "нет файла c.md" in errors[1]
