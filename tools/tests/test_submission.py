"""E27-4: генератор списка библиотек и конвертер документа сдачи."""

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SUB = ROOT / "tools" / "submission"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"sub_{name}", SUB / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


libs = _load("libs")
pdf = _load("build_pdf")

UV = """
[manifest]
members = ["app"]

[[package]]
name = "Some_Lib"
version = "1.2.3"
source = { registry = "https://pypi.org/simple" }

[[package]]
name = "transitive"
version = "0.5"
source = { registry = "https://pypi.org/simple" }

[[package]]
name = "app"
version = "0.1.0"
source = { editable = "services/app" }
dependencies = [
    { name = "some-lib" },
]

[package.metadata]
requires-dist = [
    { name = "some-lib", specifier = ">=1" },
]
"""

PNPM = """lockfileVersion: '9.0'

importers:

  .: {}

  apps/web:
    dependencies:
      '@scope/pkg':
        specifier: ^1.0.0
        version: 1.4.0(react@19.3.0)
      react:
        specifier: ^19.0.0
        version: 19.3.0
      '@fsp/ui':
        specifier: workspace:*
        version: link:../../packages/ui

packages:

  '@scope/pkg@1.4.0':
    resolution: {integrity: sha512-x}

  react@19.3.0:
    resolution: {integrity: sha512-y}

  inner@2.0.0:
    resolution: {integrity: sha512-z}

snapshots:

  react@19.3.0: {}
"""


def test_parse_uv_lock_direct_and_members():
    py, members = libs.parse_uv_lock(UV)
    assert members == ["app"]
    assert set(py) == {"some-lib", "transitive"}
    assert py["some-lib"].version == "1.2.3"
    assert py["some-lib"].direct_in == {"app"}
    assert py["transitive"].direct_in == set()


def test_parse_pnpm_lock():
    npm = libs.parse_pnpm_lock(PNPM)
    assert set(npm) == {"@scope/pkg@1.4.0", "react@19.3.0", "inner@2.0.0"}
    assert npm["@scope/pkg@1.4.0"].direct_in == {"apps/web"}
    assert npm["react@19.3.0"].direct_in == {"apps/web"}
    assert npm["inner@2.0.0"].direct_in == set()


def test_licenses_from_metadata_or_unknown(tmp_path):
    site = tmp_path / "site"
    dist = site / "Some_Lib-1.2.3.dist-info"
    dist.mkdir(parents=True)
    (dist / "METADATA").write_text(
        "Name: some-lib\nLicense-Expression: MIT\n\nbody", encoding="utf-8"
    )
    py, _ = libs.parse_uv_lock(UV)
    assert libs.python_license(site, py["some-lib"]) == "MIT"
    assert libs.python_license(site, py["transitive"]) == libs.UNKNOWN

    pnpm = tmp_path / ".pnpm"
    pj = pnpm / "@scope+pkg@1.4.0_react@19.3.0" / "node_modules" / "@scope" / "pkg"
    pj.mkdir(parents=True)
    (pj / "package.json").write_text(json.dumps({"license": "Apache-2.0"}), encoding="utf-8")
    npm = libs.parse_pnpm_lock(PNPM)
    assert libs.npm_license(pnpm, npm["@scope/pkg@1.4.0"]) == "Apache-2.0"
    assert libs.npm_license(pnpm, npm["react@19.3.0"]) == libs.UNKNOWN


def test_build_on_synthetic_root(tmp_path):
    (tmp_path / "uv.lock").write_text(UV, encoding="utf-8")
    (tmp_path / "pnpm-lock.yaml").write_text(PNPM, encoding="utf-8")
    text = libs.build(tmp_path)
    assert "| Some_Lib | 1.2.3 | проверить | app |" in text
    assert "| react | 19.3.0 | проверить | apps/web |" in text
    assert libs.build(tmp_path) == text  # детерминированно


def test_real_locks_parse():
    py, members = libs.parse_uv_lock((ROOT / "uv.lock").read_text(encoding="utf-8"))
    npm = libs.parse_pnpm_lock((ROOT / "pnpm-lock.yaml").read_text(encoding="utf-8"))
    assert "fastapi" in py and "fsp-core" in members
    assert any(k.startswith("react@") for k in npm)
    assert all(lib.version for lib in py.values())


def test_markdown_converter():
    html = pdf.convert(
        "# Заголовок\n\nТекст **жирный** и `a<b` [ссылка](x.md).\n\n"
        "- раз\n- два\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n```mermaid\nA-->B\n```\n"
    )
    assert "<h1>Заголовок</h1>" in html
    assert "<strong>жирный</strong>" in html
    assert "<code>a&lt;b</code>" in html
    assert '<a href="x.md">ссылка</a>' in html
    assert "<ul>" in html and html.count("<li>") == 2
    assert "<th>A</th>" in html and "<td>2</td>" in html
    assert "A--&gt;B" in html and "Mermaid" in html


def test_pdf_builds(tmp_path):
    import pytest

    try:
        import weasyprint  # noqa: F401
    except (ImportError, OSError) as exc:  # нет системных библиотек Pango/GTK (Windows)
        pytest.skip(f"WeasyPrint недоступен: {exc}")
    src = tmp_path / "a.md"
    src.write_text("# Тест\n\nРусский текст.\n", encoding="utf-8")
    out = tmp_path / "out" / "a.pdf"
    assert pdf.build(src, out) > 0
    assert out.read_bytes().startswith(b"%PDF")
