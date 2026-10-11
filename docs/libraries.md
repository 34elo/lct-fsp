# Библиотеки и версии

> Сгенерировано `make libraries` (`tools/libraries.py`) из `uv.lock` и `pnpm-lock.yaml`. Руками не правим.
> Лицензии взяты из метаданных установленных пакетов; «проверить» — метаданных нет (окружение не установлено или лицензия не указана).

Python 3.12: 142 пакетов, из них объявлены напрямую 35 (члены воркспейса: fsp-bot, fsp-contracts, fsp-core, fsp-fsp-connector, fsp-fsp-mock, fsp-ml, fsp-platform, lct-fsp).
JavaScript (pnpm): 751 пакетов, из них напрямую 33.

## Python: прямые зависимости

| Библиотека | Версия | Лицензия | Где объявлена |
|---|---|---|---|
| aiogram | 3.31.0 | MIT | fsp-bot |
| aiosqlite | 0.22.1 | MIT License | lct-fsp |
| alembic | 1.20.0 | MIT | fsp-core, fsp-fsp-connector |
| apscheduler | 3.11.3 | MIT | fsp-core |
| argon2-cffi | 25.1.0 | MIT | fsp-core |
| asyncpg | 0.31.0 | Apache-2.0 | fsp-platform |
| boto3 | 1.43.107 | Apache-2.0 | fsp-platform |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause | fsp-core, fsp-fsp-mock |
| fakeredis | 2.39.0 | BSD-3-Clause | lct-fsp |
| fastapi | 0.142.2 | MIT | fsp-platform |
| faststream | 0.7.7 | Apache-2.0 | fsp-platform |
| httpx | 0.28.1 | BSD-3-Clause | fsp-bot, fsp-fsp-connector, fsp-ml, fsp-platform |
| import-linter | 2.15 | BSD 2-Clause License | lct-fsp |
| jinja2 | 3.1.6 | BSD License | fsp-ml |
| locust | 2.46.7 | проверить | lct-fsp |
| moto | 5.2.3 | Apache-2.0 | lct-fsp |
| mypy | 2.4.0 | MIT | lct-fsp |
| natasha | 1.6.0 | MIT | fsp-ml |
| pydantic | 2.13.5 | MIT | fsp-contracts, fsp-platform |
| pydantic-settings | 2.15.0 | MIT | fsp-platform |
| pyjwt | 2.15.1 | MIT | fsp-platform |
| pymupdf | 1.28.2 | проверить | fsp-ml |
| pytest | 9.1.1 | MIT | lct-fsp |
| pytest-asyncio | 1.4.0 | Apache-2.0 | lct-fsp |
| pytest-xdist | 3.8.0 | MIT | lct-fsp |
| python-docx | 1.2.0 | MIT | fsp-ml |
| python-multipart | 0.0.32 | Apache-2.0 | fsp-core, fsp-fsp-mock |
| pyyaml | 6.0.3 | MIT | fsp-core |
| rapidfuzz | 3.14.6 | MIT | fsp-ml |
| redis | 8.1.0 | MIT | fsp-bot, fsp-fsp-connector, fsp-platform |
| ruff | 0.16.10 | MIT | lct-fsp |
| sqlalchemy | 2.1.2 | MIT | fsp-platform |
| structlog | 26.1.0 | MIT OR Apache-2.0 | fsp-platform |
| uvicorn | 0.54.0 | BSD-3-Clause | fsp-core, fsp-fsp-connector, fsp-fsp-mock, fsp-ml |
| weasyprint | 70.0 | BSD License | fsp-core |

## JavaScript: прямые зависимости

| Библиотека | Версия | Лицензия | Где объявлена |
|---|---|---|---|
| @eslint/js | 9.39.5 | MIT | apps/web, packages/ui |
| @fontsource-variable/jetbrains-mono | 5.3.0 | OFL-1.1 | apps/web, packages/ui |
| @fontsource-variable/onest | 5.3.1 | OFL-1.1 | apps/web, packages/ui |
| @playwright/test | 1.63.0 | Apache-2.0 | apps/web |
| @tailwindcss/vite | 4.3.3 | MIT | apps/web, packages/ui |
| @tanstack/react-query | 5.104.0 | MIT | apps/web |
| @testing-library/jest-dom | 6.10.0 | MIT | apps/web, packages/ui |
| @testing-library/react | 16.3.3 | проверить | apps/web, packages/ui |
| @types/node | 22.20.4 | MIT | apps/web, packages/ui |
| @types/react | 19.3.0 | MIT | apps/web, packages/ui |
| @types/react-dom | 19.3.0 | MIT | apps/web, packages/ui |
| @vitejs/plugin-react | 4.7.0 | MIT | apps/web, packages/ui |
| class-variance-authority | 0.7.1 | Apache-2.0 | packages/ui |
| clsx | 2.1.1 | MIT | packages/ui |
| eslint | 9.39.5 | MIT | apps/web, packages/ui |
| eslint-plugin-react-hooks | 5.2.0 | MIT | apps/web, packages/ui |
| jsdom | 25.0.1 | MIT | apps/web, packages/ui |
| lucide-react | 1.52.0 | ISC | packages/ui |
| mermaid | 11.17.2 | MIT | packages/ui |
| orval | 8.39.0 | MIT | apps/web |
| radix-ui | 1.6.7 | MIT | packages/ui |
| react | 19.3.0 | MIT | apps/web, packages/ui |
| react-dom | 19.3.0 | MIT | apps/web, packages/ui |
| react-markdown | 10.1.0 | MIT | packages/ui |
| react-router-dom | 7.18.4 | MIT | apps/web |
| remark-gfm | 4.0.1 | MIT | packages/ui |
| sonner | 2.0.8 | MIT | packages/ui |
| tailwind-merge | 3.7.0 | MIT | packages/ui |
| tailwindcss | 4.3.3 | MIT | apps/web, packages/ui |
| typescript | 5.9.3 | Apache-2.0 | apps/web, packages/ui |
| typescript-eslint | 8.71.0 | MIT | apps/web, packages/ui |
| vite | 6.4.3 | MIT | apps/web, packages/ui |
| vitest | 3.2.7 | MIT | apps/web, packages/ui |

## Python: все пакеты (включая транзитивные)

| Библиотека | Версия | Лицензия |
|---|---|---|
| aio-pika | 10.1.0 | Apache-2.0 |
| aiofiles | 25.1.0 | Apache-2.0 |
| aiogram | 3.31.0 | MIT |
| aiohappyeyeballs | 2.7.1 | PSF-2.0 |
| aiohttp | 3.14.3 | Apache-2.0 AND MIT |
| aiormq | 7.2.1 | Apache-2.0 |
| aiosignal | 1.4.0 | Apache 2.0 |
| aiosqlite | 0.22.1 | MIT License |
| alembic | 1.20.0 | MIT |
| annotated-doc | 0.0.5 | MIT |
| annotated-types | 0.8.0 | MIT |
| anyio | 4.15.1 | MIT |
| apscheduler | 3.11.3 | MIT |
| argon2-cffi | 25.1.0 | MIT |
| argon2-cffi-bindings | 26.1.0 | MIT |
| ast-serialize | 0.12.0 | MIT |
| asyncpg | 0.31.0 | Apache-2.0 |
| attrs | 26.1.0 | MIT |
| bidict | 0.24.1 | проверить |
| blinker | 1.9.0 | проверить |
| boto3 | 1.43.107 | Apache-2.0 |
| botocore | 1.43.107 | Apache-2.0 |
| brotli | 1.2.0 | MIT |
| brotlicffi | 1.2.0.2 | проверить |
| certifi | 2026.7.22 | MPL-2.0 |
| cffi | 2.1.1 | MIT-0 |
| charset-normalizer | 3.5.2 | MIT |
| click | 8.5.0 | BSD-3-Clause |
| colorama | 0.4.6 | BSD License |
| configargparse | 1.8.0 | проверить |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause |
| cssselect2 | 0.10.1 | BSD License |
| dawg-python | 0.7.2 | UNKNOWN |
| docopt | 0.6.2 | MIT |
| execnet | 2.1.2 | MIT |
| fakeredis | 2.39.0 | BSD-3-Clause |
| fast-depends | 3.0.9 | MIT |
| fastapi | 0.142.2 | MIT |
| faststream | 0.7.7 | Apache-2.0 |
| flask | 3.1.3 | проверить |
| flask-cors | 6.0.5 | проверить |
| flask-login | 0.6.3 | проверить |
| fonttools | 4.66.1 | MIT |
| frozenlist | 1.8.0 | Apache-2.0 |
| gevent | 26.9.0 | проверить |
| geventhttpclient | 2.6.0 | проверить |
| greenlet | 3.5.6 | MIT AND PSF-2.0 |
| grimp | 3.17 | BSD 2-Clause License |
| h11 | 0.16.0 | MIT |
| httpcore | 1.0.9 | BSD-3-Clause |
| httpx | 0.28.1 | BSD-3-Clause |
| idna | 3.20 | BSD-3-Clause |
| import-linter | 2.15 | BSD 2-Clause License |
| iniconfig | 2.3.0 | MIT |
| intervaltree | 3.2.1 | Apache-2.0 |
| ipymarkup | 0.9.0 | MIT |
| itsdangerous | 2.2.0 | проверить |
| jinja2 | 3.1.6 | BSD License |
| jmespath | 1.1.0 | MIT |
| librt | 0.16.0 | MIT |
| locust | 2.46.7 | проверить |
| lupa | 2.8 | MIT style |
| lxml | 6.1.3 | BSD-3-Clause |
| magic-filter | 1.0.12 | MIT |
| mako | 1.4.3 | MIT |
| markdown-it-py | 4.2.0 | MIT License |
| markupsafe | 3.0.3 | BSD-3-Clause |
| mdurl | 0.1.2 | MIT License |
| moto | 5.2.3 | Apache-2.0 |
| msgpack | 1.2.3 | проверить |
| multidict | 6.9.1 | Apache License 2.0 |
| mypy | 2.4.0 | MIT |
| mypy-extensions | 1.1.0 | MIT |
| natasha | 1.6.0 | MIT |
| navec | 0.10.0 | MIT |
| numpy | 2.5.3 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |
| opentelemetry-api | 1.45.0 | Apache-2.0 |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause |
| pamqp | 4.0.1 | BSD-3-Clause |
| pathspec | 1.1.1 | Mozilla Public License 2.0 (MPL 2.0) |
| pillow | 12.3.0 | MIT-CMU |
| pluggy | 1.6.0 | MIT |
| propcache | 0.5.4 | Apache-2.0 |
| psutil | 7.2.2 | проверить |
| py-partiql-parser | 0.6.3 | MIT |
| pycparser | 3.0 | BSD-3-Clause |
| pydantic | 2.13.5 | MIT |
| pydantic-core | 2.46.5 | MIT |
| pydantic-settings | 2.15.0 | MIT |
| pydyf | 0.12.1 | BSD License |
| pygments | 2.21.0 | BSD-2-Clause |
| pyjwt | 2.15.1 | MIT |
| pymorphy2 | 0.9.1 | MIT license |
| pymorphy2-dicts-ru | 2.4.417127.4579844 | MIT license |
| pymupdf | 1.28.2 | проверить |
| pyphen | 0.18.1 | GNU General Public License v2 or later (GPLv2+), GNU Lesser General Public License v2 or later (LGPLv2+), Mozilla Public License 1.1 (MPL 1.1) |
| pytest | 9.1.1 | MIT |
| pytest-asyncio | 1.4.0 | Apache-2.0 |
| pytest-xdist | 3.8.0 | MIT |
| python-dateutil | 2.9.0.post0 | Dual License |
| python-docx | 1.2.0 | MIT |
| python-dotenv | 1.2.4 | BSD-3-Clause |
| python-engineio | 4.14.0 | проверить |
| python-multipart | 0.0.32 | Apache-2.0 |
| python-socketio | 5.17.0 | проверить |
| pywin32 | 312 | проверить |
| pyyaml | 6.0.3 | MIT |
| pyzmq | 27.2.0 | проверить |
| rapidfuzz | 3.14.6 | MIT |
| razdel | 0.5.0 | MIT |
| redis | 8.1.0 | MIT |
| requests | 2.34.2 | Apache-2.0 |
| responses | 0.26.3 | Apache-2.0 |
| rich | 15.0.0 | MIT |
| ruff | 0.16.10 | MIT |
| s3transfer | 0.19.2 | Apache License 2.0 |
| simple-websocket | 1.1.0 | проверить |
| six | 1.17.0 | MIT |
| slovnet | 0.6.0 | MIT |
| sortedcontainers | 2.4.0 | Apache 2.0 |
| sqlalchemy | 2.1.2 | MIT |
| starlette | 1.7.0 | BSD-3-Clause |
| structlog | 26.1.0 | MIT OR Apache-2.0 |
| tinycss2 | 1.5.1 | BSD License |
| tinyhtml5 | 2.1.0 | MIT License |
| typing-extensions | 4.16.0 | PSF-2.0 |
| typing-inspection | 0.4.4 | MIT |
| tzdata | 2026.4 | Apache-2.0 |
| tzlocal | 5.4.4 | MIT |
| urllib3 | 2.8.0 | MIT |
| uvicorn | 0.54.0 | BSD-3-Clause |
| weasyprint | 70.0 | BSD License |
| webencodings | 0.6.1 | BSD License |
| websocket-client | 1.9.2 | проверить |
| werkzeug | 3.1.9 | BSD-3-Clause |
| wsproto | 1.3.2 | проверить |
| xmltodict | 1.0.4 | MIT |
| yargy | 0.16.0 | MIT |
| yarl | 1.25.1 | Apache-2.0 |
| zope-event | 6.2 | проверить |
| zope-interface | 8.6 | проверить |
| zopfli | 0.4.3 | Apache-2.0 |

## JavaScript: все пакеты (включая транзитивные)

| Библиотека | Версия | Лицензия |
|---|---|---|
| @adobe/css-tools | 4.5.0 | MIT |
| @antfu/install-pkg | 2.1.0 | MIT |
| @asamuzakjp/css-color | 3.2.0 | MIT |
| @babel/code-frame | 7.29.7 | MIT |
| @babel/compat-data | 7.29.7 | MIT |
| @babel/core | 7.29.7 | MIT |
| @babel/generator | 7.29.8 | MIT |
| @babel/helper-compilation-targets | 7.29.7 | MIT |
| @babel/helper-globals | 7.29.7 | MIT |
| @babel/helper-module-imports | 7.29.7 | MIT |
| @babel/helper-module-transforms | 7.29.7 | MIT |
| @babel/helper-plugin-utils | 7.29.7 | MIT |
| @babel/helper-string-parser | 7.29.7 | MIT |
| @babel/helper-validator-identifier | 7.29.7 | MIT |
| @babel/helper-validator-option | 7.29.7 | MIT |
| @babel/helpers | 7.29.7 | MIT |
| @babel/parser | 7.29.9 | MIT |
| @babel/plugin-transform-react-jsx-self | 7.29.7 | проверить |
| @babel/plugin-transform-react-jsx-source | 7.29.7 | проверить |
| @babel/runtime | 7.29.7 | MIT |
| @babel/template | 7.29.7 | MIT |
| @babel/traverse | 7.29.8 | MIT |
| @babel/types | 7.29.8 | MIT |
| @braintree/sanitize-url | 7.1.2 | MIT |
| @chevrotain/types | 11.1.2 | Apache-2.0 |
| @commander-js/extra-typings | 15.0.0 | MIT |
| @csstools/color-helpers | 5.1.0 | MIT-0 |
| @csstools/css-calc | 2.1.4 | MIT |
| @csstools/css-color-parser | 3.1.0 | проверить |
| @csstools/css-parser-algorithms | 3.0.5 | проверить |
| @csstools/css-tokenizer | 3.0.4 | MIT |
| @esbuild/aix-ppc64 | 0.25.12 | проверить |
| @esbuild/aix-ppc64 | 0.28.2 | проверить |
| @esbuild/android-arm | 0.25.12 | проверить |
| @esbuild/android-arm | 0.28.2 | проверить |
| @esbuild/android-arm64 | 0.25.12 | проверить |
| @esbuild/android-arm64 | 0.28.2 | проверить |
| @esbuild/android-x64 | 0.25.12 | проверить |
| @esbuild/android-x64 | 0.28.2 | проверить |
| @esbuild/darwin-arm64 | 0.25.12 | проверить |
| @esbuild/darwin-arm64 | 0.28.2 | проверить |
| @esbuild/darwin-x64 | 0.25.12 | проверить |
| @esbuild/darwin-x64 | 0.28.2 | проверить |
| @esbuild/freebsd-arm64 | 0.25.12 | проверить |
| @esbuild/freebsd-arm64 | 0.28.2 | проверить |
| @esbuild/freebsd-x64 | 0.25.12 | проверить |
| @esbuild/freebsd-x64 | 0.28.2 | проверить |
| @esbuild/linux-arm | 0.25.12 | проверить |
| @esbuild/linux-arm | 0.28.2 | проверить |
| @esbuild/linux-arm64 | 0.25.12 | проверить |
| @esbuild/linux-arm64 | 0.28.2 | проверить |
| @esbuild/linux-ia32 | 0.25.12 | проверить |
| @esbuild/linux-ia32 | 0.28.2 | проверить |
| @esbuild/linux-loong64 | 0.25.12 | проверить |
| @esbuild/linux-loong64 | 0.28.2 | проверить |
| @esbuild/linux-mips64el | 0.25.12 | проверить |
| @esbuild/linux-mips64el | 0.28.2 | проверить |
| @esbuild/linux-ppc64 | 0.25.12 | проверить |
| @esbuild/linux-ppc64 | 0.28.2 | проверить |
| @esbuild/linux-riscv64 | 0.25.12 | проверить |
| @esbuild/linux-riscv64 | 0.28.2 | проверить |
| @esbuild/linux-s390x | 0.25.12 | проверить |
| @esbuild/linux-s390x | 0.28.2 | проверить |
| @esbuild/linux-x64 | 0.25.12 | проверить |
| @esbuild/linux-x64 | 0.28.2 | проверить |
| @esbuild/netbsd-arm64 | 0.25.12 | проверить |
| @esbuild/netbsd-arm64 | 0.28.2 | проверить |
| @esbuild/netbsd-x64 | 0.25.12 | проверить |
| @esbuild/netbsd-x64 | 0.28.2 | проверить |
| @esbuild/openbsd-arm64 | 0.25.12 | проверить |
| @esbuild/openbsd-arm64 | 0.28.2 | проверить |
| @esbuild/openbsd-x64 | 0.25.12 | проверить |
| @esbuild/openbsd-x64 | 0.28.2 | проверить |
| @esbuild/openharmony-arm64 | 0.25.12 | проверить |
| @esbuild/openharmony-arm64 | 0.28.2 | проверить |
| @esbuild/sunos-x64 | 0.25.12 | проверить |
| @esbuild/sunos-x64 | 0.28.2 | проверить |
| @esbuild/win32-arm64 | 0.25.12 | проверить |
| @esbuild/win32-arm64 | 0.28.2 | проверить |
| @esbuild/win32-ia32 | 0.25.12 | проверить |
| @esbuild/win32-ia32 | 0.28.2 | проверить |
| @esbuild/win32-x64 | 0.25.12 | MIT |
| @esbuild/win32-x64 | 0.28.2 | MIT |
| @eslint-community/eslint-utils | 4.10.1 | проверить |
| @eslint-community/regexpp | 4.12.2 | MIT |
| @eslint/config-array | 0.21.2 | Apache-2.0 |
| @eslint/config-helpers | 0.4.2 | Apache-2.0 |
| @eslint/core | 0.17.0 | Apache-2.0 |
| @eslint/eslintrc | 3.3.7 | MIT |
| @eslint/js | 9.39.5 | MIT |
| @eslint/object-schema | 2.1.7 | Apache-2.0 |
| @eslint/plugin-kit | 0.4.1 | Apache-2.0 |
| @floating-ui/core | 1.8.0 | MIT |
| @floating-ui/dom | 1.8.0 | MIT |
| @floating-ui/react-dom | 2.1.9 | проверить |
| @floating-ui/utils | 0.2.12 | MIT |
| @fontsource-variable/jetbrains-mono | 5.3.0 | OFL-1.1 |
| @fontsource-variable/onest | 5.3.1 | OFL-1.1 |
| @humanfs/core | 0.19.2 | Apache-2.0 |
| @humanfs/node | 0.16.8 | Apache-2.0 |
| @humanfs/types | 0.15.0 | Apache-2.0 |
| @humanwhocodes/module-importer | 1.0.1 | Apache-2.0 |
| @humanwhocodes/retry | 0.4.3 | Apache-2.0 |
| @iconify/types | 2.0.0 | MIT |
| @iconify/utils | 3.1.7 | MIT |
| @jridgewell/gen-mapping | 0.3.13 | MIT |
| @jridgewell/remapping | 2.3.5 | MIT |
| @jridgewell/resolve-uri | 3.1.2 | MIT |
| @jridgewell/sourcemap-codec | 1.6.0 | MIT |
| @jridgewell/trace-mapping | 0.3.31 | MIT |
| @mermaid-js/parser | 1.2.1 | MIT |
| @napi-rs/lzma-linux-x64-gnu | 1.5.1 | проверить |
| @orval/angular | 8.39.0 | MIT |
| @orval/axios | 8.39.0 | MIT |
| @orval/core | 8.39.0 | MIT |
| @orval/effect | 8.39.0 | MIT |
| @orval/fetch | 8.39.0 | MIT |
| @orval/hono | 8.39.0 | MIT |
| @orval/mcp | 8.39.0 | MIT |
| @orval/mock | 8.39.0 | MIT |
| @orval/pinia-colada | 8.39.0 | MIT |
| @orval/query | 8.39.0 | MIT |
| @orval/solid-start | 8.39.0 | MIT |
| @orval/swr | 8.39.0 | MIT |
| @orval/zod | 8.39.0 | MIT |
| @playwright/test | 1.63.0 | Apache-2.0 |
| @radix-ui/number | 1.1.3 | MIT |
| @radix-ui/primitive | 1.1.7 | MIT |
| @radix-ui/react-accessible-icon | 1.1.15 | проверить |
| @radix-ui/react-accordion | 1.2.20 | проверить |
| @radix-ui/react-alert-dialog | 1.1.23 | проверить |
| @radix-ui/react-arrow | 1.1.15 | проверить |
| @radix-ui/react-aspect-ratio | 1.1.15 | проверить |
| @radix-ui/react-avatar | 1.2.6 | проверить |
| @radix-ui/react-checkbox | 1.3.11 | проверить |
| @radix-ui/react-collapsible | 1.1.20 | проверить |
| @radix-ui/react-collection | 1.1.15 | проверить |
| @radix-ui/react-compose-refs | 1.1.5 | проверить |
| @radix-ui/react-context | 1.2.2 | проверить |
| @radix-ui/react-context-menu | 2.3.7 | проверить |
| @radix-ui/react-dialog | 1.1.23 | проверить |
| @radix-ui/react-direction | 1.1.4 | проверить |
| @radix-ui/react-dismissable-layer | 1.1.19 | проверить |
| @radix-ui/react-dropdown-menu | 2.1.24 | проверить |
| @radix-ui/react-focus-guards | 1.1.6 | проверить |
| @radix-ui/react-focus-scope | 1.1.16 | проверить |
| @radix-ui/react-form | 0.1.16 | MIT |
| @radix-ui/react-hover-card | 1.1.23 | проверить |
| @radix-ui/react-id | 1.1.4 | MIT |
| @radix-ui/react-label | 2.1.15 | проверить |
| @radix-ui/react-menu | 2.1.24 | MIT |
| @radix-ui/react-menubar | 1.1.24 | проверить |
| @radix-ui/react-navigation-menu | 1.2.22 | проверить |
| @radix-ui/react-one-time-password-field | 0.1.16 | проверить |
| @radix-ui/react-password-toggle-field | 0.1.11 | проверить |
| @radix-ui/react-popover | 1.1.23 | проверить |
| @radix-ui/react-popper | 1.3.7 | проверить |
| @radix-ui/react-portal | 1.1.17 | проверить |
| @radix-ui/react-presence | 1.1.10 | проверить |
| @radix-ui/react-primitive | 2.1.10 | проверить |
| @radix-ui/react-progress | 1.1.16 | проверить |
| @radix-ui/react-radio-group | 1.4.7 | проверить |
| @radix-ui/react-roving-focus | 1.1.19 | проверить |
| @radix-ui/react-scroll-area | 1.2.18 | проверить |
| @radix-ui/react-select | 2.3.7 | проверить |
| @radix-ui/react-separator | 1.1.15 | проверить |
| @radix-ui/react-slider | 1.4.7 | проверить |
| @radix-ui/react-slot | 1.3.3 | MIT |
| @radix-ui/react-switch | 1.3.7 | проверить |
| @radix-ui/react-tabs | 1.1.21 | MIT |
| @radix-ui/react-toast | 1.2.23 | проверить |
| @radix-ui/react-toggle | 1.1.18 | проверить |
| @radix-ui/react-toggle-group | 1.1.19 | проверить |
| @radix-ui/react-toolbar | 1.1.19 | проверить |
| @radix-ui/react-tooltip | 1.2.16 | проверить |
| @radix-ui/react-use-callback-ref | 1.1.4 | проверить |
| @radix-ui/react-use-controllable-state | 1.2.6 | проверить |
| @radix-ui/react-use-effect-event | 0.0.5 | проверить |
| @radix-ui/react-use-escape-keydown | 1.1.5 | проверить |
| @radix-ui/react-use-is-hydrated | 0.1.3 | проверить |
| @radix-ui/react-use-layout-effect | 1.1.4 | проверить |
| @radix-ui/react-use-previous | 1.1.4 | проверить |
| @radix-ui/react-use-rect | 1.1.4 | проверить |
| @radix-ui/react-use-size | 1.1.4 | проверить |
| @radix-ui/react-visually-hidden | 1.2.11 | проверить |
| @radix-ui/rect | 1.1.3 | MIT |
| @rolldown/pluginutils | 1.0.0-beta.27 | MIT |
| @rollup/rollup-android-arm-eabi | 4.63.6 | проверить |
| @rollup/rollup-android-arm64 | 4.63.6 | проверить |
| @rollup/rollup-darwin-arm64 | 4.63.6 | проверить |
| @rollup/rollup-darwin-x64 | 4.63.6 | проверить |
| @rollup/rollup-freebsd-arm64 | 4.63.6 | проверить |
| @rollup/rollup-freebsd-x64 | 4.63.6 | проверить |
| @rollup/rollup-linux-arm-gnueabihf | 4.63.6 | проверить |
| @rollup/rollup-linux-arm-musleabihf | 4.63.6 | проверить |
| @rollup/rollup-linux-arm64-gnu | 4.63.6 | проверить |
| @rollup/rollup-linux-arm64-musl | 4.63.6 | проверить |
| @rollup/rollup-linux-loong64-gnu | 4.63.6 | проверить |
| @rollup/rollup-linux-loong64-musl | 4.63.6 | проверить |
| @rollup/rollup-linux-ppc64-gnu | 4.63.6 | проверить |
| @rollup/rollup-linux-ppc64-musl | 4.63.6 | проверить |
| @rollup/rollup-linux-riscv64-gnu | 4.63.6 | проверить |
| @rollup/rollup-linux-riscv64-musl | 4.63.6 | проверить |
| @rollup/rollup-linux-s390x-gnu | 4.63.6 | проверить |
| @rollup/rollup-linux-x64-gnu | 4.63.6 | проверить |
| @rollup/rollup-linux-x64-musl | 4.63.6 | проверить |
| @rollup/rollup-openbsd-x64 | 4.63.6 | проверить |
| @rollup/rollup-openharmony-arm64 | 4.63.6 | проверить |
| @rollup/rollup-win32-arm64-msvc | 4.63.6 | проверить |
| @rollup/rollup-win32-ia32-msvc | 4.63.6 | проверить |
| @rollup/rollup-win32-x64-gnu | 4.63.6 | MIT |
| @rollup/rollup-win32-x64-msvc | 4.63.6 | MIT |
| @scalar/helpers | 0.16.0 | MIT |
| @scalar/json-magic | 0.15.3 | MIT |
| @scalar/json-schema-validator | 0.1.8 | MIT |
| @scalar/openapi-parser | 0.29.9 | MIT |
| @scalar/openapi-types | 0.9.7 | MIT |
| @scalar/openapi-upgrader | 0.4.1 | MIT |
| @scalar/openapi-validator | 0.1.8 | MIT |
| @scalar/types | 0.22.3 | MIT |
| @sec-ant/readable-stream | 0.4.1 | MIT |
| @sindresorhus/merge-streams | 4.0.0 | MIT |
| @tailwindcss/node | 4.3.3 | MIT |
| @tailwindcss/oxide | 4.3.3 | MIT |
| @tailwindcss/oxide-android-arm64 | 4.3.3 | проверить |
| @tailwindcss/oxide-darwin-arm64 | 4.3.3 | проверить |
| @tailwindcss/oxide-darwin-x64 | 4.3.3 | проверить |
| @tailwindcss/oxide-freebsd-x64 | 4.3.3 | проверить |
| @tailwindcss/oxide-linux-arm-gnueabihf | 4.3.3 | проверить |
| @tailwindcss/oxide-linux-arm64-gnu | 4.3.3 | проверить |
| @tailwindcss/oxide-linux-arm64-musl | 4.3.3 | проверить |
| @tailwindcss/oxide-linux-x64-gnu | 4.3.3 | проверить |
| @tailwindcss/oxide-linux-x64-musl | 4.3.3 | проверить |
| @tailwindcss/oxide-wasm32-wasi | 4.3.3 | проверить |
| @tailwindcss/oxide-win32-arm64-msvc | 4.3.3 | проверить |
| @tailwindcss/oxide-win32-x64-msvc | 4.3.3 | MIT |
| @tailwindcss/vite | 4.3.3 | MIT |
| @tanstack/query-core | 5.104.0 | MIT |
| @tanstack/react-query | 5.104.0 | MIT |
| @testing-library/dom | 10.4.2 | MIT |
| @testing-library/jest-dom | 6.10.0 | MIT |
| @testing-library/react | 16.3.3 | проверить |
| @types/aria-query | 5.0.4 | MIT |
| @types/babel__core | 7.20.5 | MIT |
| @types/babel__generator | 7.27.0 | MIT |
| @types/babel__template | 7.4.4 | MIT |
| @types/babel__traverse | 7.28.0 | MIT |
| @types/chai | 5.2.3 | MIT |
| @types/d3 | 7.4.3 | MIT |
| @types/d3-array | 3.2.2 | MIT |
| @types/d3-axis | 3.0.6 | MIT |
| @types/d3-brush | 3.0.6 | MIT |
| @types/d3-chord | 3.0.6 | MIT |
| @types/d3-color | 3.1.3 | MIT |
| @types/d3-contour | 3.0.6 | MIT |
| @types/d3-delaunay | 6.0.4 | MIT |
| @types/d3-dispatch | 3.0.7 | MIT |
| @types/d3-drag | 3.0.7 | MIT |
| @types/d3-dsv | 3.0.7 | MIT |
| @types/d3-ease | 3.0.2 | MIT |
| @types/d3-fetch | 3.0.7 | MIT |
| @types/d3-force | 3.0.10 | MIT |
| @types/d3-format | 3.0.4 | MIT |
| @types/d3-geo | 3.1.1 | MIT |
| @types/d3-hierarchy | 3.1.7 | MIT |
| @types/d3-interpolate | 3.0.4 | MIT |
| @types/d3-path | 3.1.1 | MIT |
| @types/d3-polygon | 3.0.2 | MIT |
| @types/d3-quadtree | 3.0.6 | MIT |
| @types/d3-random | 3.0.4 | MIT |
| @types/d3-scale | 4.0.9 | MIT |
| @types/d3-scale-chromatic | 3.1.0 | MIT |
| @types/d3-selection | 3.0.12 | MIT |
| @types/d3-shape | 3.2.0 | MIT |
| @types/d3-time | 3.0.4 | MIT |
| @types/d3-time-format | 4.0.3 | MIT |
| @types/d3-timer | 3.0.2 | MIT |
| @types/d3-transition | 3.0.9 | MIT |
| @types/d3-zoom | 3.0.9 | MIT |
| @types/debug | 4.1.13 | MIT |
| @types/deep-eql | 4.0.2 | MIT |
| @types/estree | 1.0.9 | MIT |
| @types/estree-jsx | 1.0.5 | MIT |
| @types/geojson | 7946.0.16 | MIT |
| @types/hast | 3.0.5 | MIT |
| @types/json-schema | 7.0.15 | MIT |
| @types/mdast | 4.0.4 | MIT |
| @types/ms | 2.1.0 | MIT |
| @types/node | 22.20.4 | MIT |
| @types/react | 19.3.0 | MIT |
| @types/react-dom | 19.3.0 | MIT |
| @types/trusted-types | 2.0.7 | MIT |
| @types/unist | 2.0.11 | MIT |
| @types/unist | 3.0.3 | MIT |
| @typescript-eslint/eslint-plugin | 8.71.0 | проверить |
| @typescript-eslint/parser | 8.71.0 | проверить |
| @typescript-eslint/project-service | 8.71.0 | MIT |
| @typescript-eslint/scope-manager | 8.71.0 | MIT |
| @typescript-eslint/tsconfig-utils | 8.71.0 | MIT |
| @typescript-eslint/type-utils | 8.71.0 | проверить |
| @typescript-eslint/types | 8.71.0 | MIT |
| @typescript-eslint/typescript-estree | 8.71.0 | MIT |
| @typescript-eslint/utils | 8.71.0 | проверить |
| @typescript-eslint/visitor-keys | 8.71.0 | MIT |
| @ungap/structured-clone | 1.4.0 | ISC |
| @upsetjs/venn.js | 2.0.0 | MIT |
| @vitejs/plugin-react | 4.7.0 | MIT |
| @vitest/expect | 3.2.7 | MIT |
| @vitest/mocker | 3.2.7 | MIT |
| @vitest/pretty-format | 3.2.7 | MIT |
| @vitest/runner | 3.2.7 | MIT |
| @vitest/snapshot | 3.2.7 | MIT |
| @vitest/spy | 3.2.7 | MIT |
| @vitest/utils | 3.2.7 | MIT |
| acorn | 8.18.0 | MIT |
| acorn-jsx | 5.3.2 | MIT |
| agent-base | 7.1.4 | MIT |
| ajv | 6.15.0 | MIT |
| ajv | 8.20.0 | MIT |
| ajv-draft-04 | 1.0.0 | MIT |
| ajv-formats | 3.0.1 | MIT |
| ansi-regex | 5.0.1 | MIT |
| ansi-styles | 4.3.0 | MIT |
| ansi-styles | 5.2.0 | MIT |
| argparse | 2.0.1 | Python-2.0 |
| aria-hidden | 1.2.6 | MIT |
| aria-query | 5.3.0 | Apache-2.0 |
| aria-query | 5.3.2 | Apache-2.0 |
| assertion-error | 2.0.1 | MIT |
| asynckit | 0.4.0 | MIT |
| bail | 2.0.2 | MIT |
| balanced-match | 1.0.2 | MIT |
| balanced-match | 4.0.4 | MIT |
| baseline-browser-mapping | 2.11.26 | Apache-2.0 |
| brace-expansion | 1.1.21 | MIT |
| brace-expansion | 5.0.12 | MIT |
| browserslist | 4.29.3 | MIT |
| cac | 6.7.14 | MIT |
| call-bind-apply-helpers | 1.0.2 | MIT |
| callsites | 3.1.0 | MIT |
| caniuse-lite | 1.0.30001814 | CC-BY-4.0 |
| ccount | 2.0.1 | MIT |
| chai | 5.3.3 | MIT |
| chalk | 4.1.2 | MIT |
| character-entities | 2.0.2 | MIT |
| character-entities-html4 | 2.1.0 | MIT |
| character-entities-legacy | 3.0.0 | MIT |
| character-reference-invalid | 2.0.1 | MIT |
| check-error | 2.1.3 | MIT |
| chokidar | 5.0.0 | MIT |
| class-variance-authority | 0.7.1 | Apache-2.0 |
| clsx | 2.1.1 | MIT |
| color-convert | 2.0.1 | MIT |
| color-name | 1.1.4 | MIT |
| combined-stream | 1.0.8 | MIT |
| comma-separated-tokens | 2.0.3 | MIT |
| commander | 15.0.0 | MIT |
| commander | 7.2.0 | MIT |
| commander | 8.3.0 | MIT |
| compare-versions | 6.1.1 | MIT |
| concat-map | 0.0.1 | MIT |
| convert-source-map | 2.0.0 | MIT |
| cookie | 1.1.1 | MIT |
| cose-base | 1.0.3 | MIT |
| cose-base | 2.2.0 | MIT |
| cross-spawn | 7.0.6 | MIT |
| css.escape | 1.5.1 | MIT |
| cssstyle | 4.6.0 | MIT |
| csstype | 3.2.3 | MIT |
| cytoscape | 3.34.3 | MIT |
| cytoscape-cose-bilkent | 4.1.0 | MIT |
| cytoscape-fcose | 2.2.0 | MIT |
| d3 | 7.9.0 | ISC |
| d3-array | 2.12.1 | BSD-3-Clause |
| d3-array | 3.2.4 | ISC |
| d3-axis | 3.0.0 | ISC |
| d3-brush | 3.0.0 | ISC |
| d3-chord | 3.0.1 | ISC |
| d3-color | 3.1.0 | ISC |
| d3-contour | 4.0.2 | ISC |
| d3-delaunay | 6.0.4 | ISC |
| d3-dispatch | 3.0.1 | ISC |
| d3-drag | 3.0.0 | ISC |
| d3-dsv | 3.0.1 | ISC |
| d3-ease | 3.0.1 | BSD-3-Clause |
| d3-fetch | 3.0.1 | ISC |
| d3-force | 3.0.0 | ISC |
| d3-format | 3.1.2 | ISC |
| d3-geo | 3.1.1 | ISC |
| d3-hierarchy | 3.1.2 | ISC |
| d3-interpolate | 3.0.1 | ISC |
| d3-path | 1.0.9 | BSD-3-Clause |
| d3-path | 3.1.0 | ISC |
| d3-polygon | 3.0.1 | ISC |
| d3-quadtree | 3.0.1 | ISC |
| d3-random | 3.0.1 | ISC |
| d3-sankey | 0.12.3 | BSD-3-Clause |
| d3-scale | 4.0.2 | ISC |
| d3-scale-chromatic | 3.1.0 | ISC |
| d3-selection | 3.0.0 | ISC |
| d3-shape | 1.3.7 | BSD-3-Clause |
| d3-shape | 3.2.0 | ISC |
| d3-time | 3.1.0 | ISC |
| d3-time-format | 4.1.0 | ISC |
| d3-timer | 3.0.1 | ISC |
| d3-transition | 3.0.1 | ISC |
| d3-zoom | 3.0.0 | ISC |
| dagre-d3-es | 7.0.14 | MIT |
| data-urls | 5.0.0 | MIT |
| dayjs | 1.11.23 | MIT |
| debug | 4.4.3 | MIT |
| decimal.js | 10.6.0 | MIT |
| decode-named-character-reference | 1.3.0 | MIT |
| deep-eql | 5.0.2 | MIT |
| deep-is | 0.1.4 | MIT |
| delaunator | 5.1.0 | ISC |
| delayed-stream | 1.0.0 | MIT |
| dequal | 2.0.3 | MIT |
| detect-libc | 2.1.2 | Apache-2.0 |
| detect-node-es | 1.1.0 | MIT |
| devlop | 1.1.0 | MIT |
| dom-accessibility-api | 0.5.16 | MIT |
| dom-accessibility-api | 0.6.3 | MIT |
| dompurify | 3.4.16 | (MPL-2.0 OR Apache-2.0) |
| dunder-proto | 1.0.1 | MIT |
| electron-to-chromium | 1.5.443 | ISC |
| enhanced-resolve | 5.26.0 | MIT |
| entities | 6.0.1 | BSD-2-Clause |
| es-define-property | 1.0.1 | MIT |
| es-errors | 1.3.0 | MIT |
| es-module-lexer | 1.7.0 | MIT |
| es-object-atoms | 1.1.2 | MIT |
| es-set-tostringtag | 2.1.0 | MIT |
| es-toolkit | 1.52.0 | MIT |
| esbuild | 0.25.12 | MIT |
| esbuild | 0.28.2 | MIT |
| escalade | 3.2.0 | MIT |
| escape-string-regexp | 4.0.0 | MIT |
| escape-string-regexp | 5.0.0 | MIT |
| eslint | 9.39.5 | MIT |
| eslint-plugin-react-hooks | 5.2.0 | MIT |
| eslint-scope | 8.4.0 | BSD-2-Clause |
| eslint-visitor-keys | 3.4.3 | Apache-2.0 |
| eslint-visitor-keys | 4.2.1 | Apache-2.0 |
| eslint-visitor-keys | 5.0.1 | Apache-2.0 |
| espree | 10.4.0 | BSD-2-Clause |
| esquery | 1.7.0 | BSD-3-Clause |
| esrecurse | 4.3.0 | BSD-2-Clause |
| estraverse | 5.3.0 | BSD-2-Clause |
| estree-util-is-identifier-name | 3.0.0 | MIT |
| estree-walker | 3.0.3 | MIT |
| esutils | 2.0.3 | BSD-2-Clause |
| execa | 9.6.1 | MIT |
| expect-type | 1.4.0 | Apache-2.0 |
| extend | 3.0.2 | MIT |
| fast-deep-equal | 3.1.3 | MIT |
| fast-json-stable-stringify | 2.1.0 | MIT |
| fast-levenshtein | 2.0.6 | MIT |
| fast-uri | 3.1.8 | BSD-3-Clause |
| fastdom | 1.0.12 | MIT |
| fdir | 6.5.0 | MIT |
| figures | 6.1.0 | MIT |
| file-entry-cache | 8.0.0 | MIT |
| find-up | 5.0.0 | MIT |
| flat-cache | 4.0.1 | MIT |
| flatted | 3.4.4 | ISC |
| form-data | 4.0.6 | MIT |
| fsevents | 2.3.3 | проверить |
| function-bind | 1.1.2 | MIT |
| gensync | 1.0.0-beta.2 | MIT |
| get-intrinsic | 1.3.0 | MIT |
| get-nonce | 1.0.1 | MIT |
| get-proto | 1.0.1 | MIT |
| get-stream | 9.0.1 | MIT |
| get-tsconfig | 4.14.3 | MIT |
| glob-parent | 6.0.2 | ISC |
| globals | 14.0.0 | MIT |
| gopd | 1.2.0 | MIT |
| graceful-fs | 4.2.11 | ISC |
| hachure-fill | 0.5.2 | MIT |
| has-flag | 4.0.0 | MIT |
| has-symbols | 1.1.0 | MIT |
| has-tostringtag | 1.0.2 | MIT |
| hasown | 2.0.4 | MIT |
| hast-util-to-jsx-runtime | 2.3.6 | MIT |
| hast-util-whitespace | 3.0.0 | MIT |
| html-encoding-sniffer | 4.0.0 | MIT |
| html-url-attributes | 3.0.1 | MIT |
| http-proxy-agent | 7.0.2 | MIT |
| https-proxy-agent | 7.0.6 | MIT |
| human-signals | 8.0.1 | Apache-2.0 |
| iconv-lite | 0.6.3 | MIT |
| ignore | 5.3.2 | MIT |
| ignore | 7.0.11 | MIT |
| import-fresh | 3.3.1 | MIT |
| import-meta-resolve | 4.2.0 | MIT |
| imurmurhash | 0.1.4 | MIT |
| indent-string | 4.0.0 | MIT |
| inline-style-parser | 0.2.7 | MIT |
| internmap | 1.0.1 | ISC |
| internmap | 2.0.3 | ISC |
| is-alphabetical | 2.0.1 | MIT |
| is-alphanumerical | 2.0.1 | MIT |
| is-decimal | 2.0.1 | MIT |
| is-extglob | 2.1.1 | MIT |
| is-glob | 4.0.3 | MIT |
| is-hexadecimal | 2.0.1 | MIT |
| is-plain-obj | 4.1.0 | MIT |
| is-potential-custom-element-name | 1.0.1 | MIT |
| is-stream | 4.0.1 | MIT |
| is-unicode-supported | 2.1.0 | MIT |
| isexe | 2.0.0 | ISC |
| jiti | 2.7.0 | MIT |
| js-tokens | 4.0.0 | MIT |
| js-tokens | 9.0.1 | MIT |
| js-yaml | 4.3.2 | MIT |
| jsdom | 25.0.1 | MIT |
| jsesc | 3.1.0 | MIT |
| json-buffer | 3.0.1 | MIT |
| json-schema-traverse | 0.4.1 | MIT |
| json-schema-traverse | 1.0.0 | MIT |
| json-stable-stringify-without-jsonify | 1.0.1 | MIT |
| json5 | 2.2.3 | MIT |
| katex | 0.16.47 | MIT |
| keyv | 4.5.4 | MIT |
| khroma | 2.1.0 | проверить |
| layout-base | 1.0.2 | MIT |
| layout-base | 2.0.1 | MIT |
| levn | 0.4.1 | MIT |
| lightningcss | 1.32.0 | MPL-2.0 |
| lightningcss-android-arm64 | 1.32.0 | проверить |
| lightningcss-darwin-arm64 | 1.32.0 | проверить |
| lightningcss-darwin-x64 | 1.32.0 | проверить |
| lightningcss-freebsd-x64 | 1.32.0 | проверить |
| lightningcss-linux-arm-gnueabihf | 1.32.0 | проверить |
| lightningcss-linux-arm64-gnu | 1.32.0 | проверить |
| lightningcss-linux-arm64-musl | 1.32.0 | проверить |
| lightningcss-linux-x64-gnu | 1.32.0 | проверить |
| lightningcss-linux-x64-musl | 1.32.0 | проверить |
| lightningcss-win32-arm64-msvc | 1.32.0 | проверить |
| lightningcss-win32-x64-msvc | 1.32.0 | MPL-2.0 |
| locate-path | 6.0.0 | MIT |
| lodash-es | 4.18.1 | MIT |
| lodash.merge | 4.6.2 | MIT |
| longest-streak | 3.1.0 | MIT |
| loupe | 3.2.1 | MIT |
| lru-cache | 10.4.3 | ISC |
| lru-cache | 5.1.1 | ISC |
| lucide-react | 1.52.0 | ISC |
| lz-string | 1.5.0 | MIT |
| magic-string | 0.30.21 | MIT |
| markdown-table | 3.0.4 | MIT |
| marked | 16.4.2 | MIT |
| math-intrinsics | 1.1.0 | MIT |
| mdast-util-find-and-replace | 3.0.3 | MIT |
| mdast-util-from-markdown | 2.1.0 | MIT |
| mdast-util-gfm | 3.1.0 | MIT |
| mdast-util-gfm-autolink-literal | 2.0.1 | MIT |
| mdast-util-gfm-footnote | 2.1.0 | MIT |
| mdast-util-gfm-strikethrough | 2.0.1 | MIT |
| mdast-util-gfm-table | 2.0.0 | MIT |
| mdast-util-gfm-task-list-item | 2.0.0 | MIT |
| mdast-util-mdx-expression | 2.0.1 | MIT |
| mdast-util-mdx-jsx | 3.2.0 | MIT |
| mdast-util-mdxjs-esm | 2.0.1 | MIT |
| mdast-util-phrasing | 4.1.0 | MIT |
| mdast-util-to-hast | 13.2.1 | MIT |
| mdast-util-to-markdown | 2.2.0 | MIT |
| mdast-util-to-string | 4.0.0 | MIT |
| mermaid | 11.17.2 | MIT |
| micromark | 4.0.3 | MIT |
| micromark-core-commonmark | 2.0.4 | MIT |
| micromark-extension-gfm | 3.0.0 | MIT |
| micromark-extension-gfm-autolink-literal | 2.1.0 | MIT |
| micromark-extension-gfm-footnote | 2.1.0 | MIT |
| micromark-extension-gfm-strikethrough | 2.1.0 | MIT |
| micromark-extension-gfm-table | 2.1.2 | MIT |
| micromark-extension-gfm-tagfilter | 2.0.0 | MIT |
| micromark-extension-gfm-task-list-item | 2.1.0 | MIT |
| micromark-factory-destination | 2.0.1 | MIT |
| micromark-factory-label | 2.0.1 | MIT |
| micromark-factory-space | 2.1.0 | MIT |
| micromark-factory-title | 2.0.1 | MIT |
| micromark-factory-whitespace | 2.0.1 | MIT |
| micromark-util-character | 2.1.1 | MIT |
| micromark-util-chunked | 2.0.1 | MIT |
| micromark-util-classify-character | 2.0.1 | MIT |
| micromark-util-combine-extensions | 2.0.1 | MIT |
| micromark-util-decode-numeric-character-reference | 2.0.2 | MIT |
| micromark-util-decode-string | 2.0.1 | MIT |
| micromark-util-edit-map | 1.0.0 | MIT |
| micromark-util-encode | 2.0.1 | MIT |
| micromark-util-html-tag-name | 2.0.1 | MIT |
| micromark-util-normalize-identifier | 2.0.1 | MIT |
| micromark-util-resolve-all | 2.0.1 | MIT |
| micromark-util-sanitize-uri | 2.0.1 | MIT |
| micromark-util-subtokenize | 2.1.0 | MIT |
| micromark-util-symbol | 2.0.1 | MIT |
| micromark-util-types | 2.0.3 | MIT |
| mime-db | 1.52.0 | MIT |
| mime-types | 2.1.35 | MIT |
| min-indent | 1.0.1 | MIT |
| minimatch | 10.2.6 | BlueOak-1.0.0 |
| minimatch | 3.1.5 | ISC |
| ms | 2.1.3 | MIT |
| nanoid | 3.3.19 | MIT |
| nanoid | 5.1.16 | MIT |
| natural-compare | 1.4.0 | MIT |
| node-releases | 2.0.57 | MIT |
| npm-run-path | 6.0.0 | MIT |
| nwsapi | 2.2.28 | MIT |
| optionator | 0.9.4 | MIT |
| orval | 8.39.0 | MIT |
| p-limit | 3.1.0 | MIT |
| p-locate | 5.0.0 | MIT |
| package-manager-detector | 1.9.0 | MIT |
| parent-module | 1.0.1 | MIT |
| parse-entities | 4.0.2 | MIT |
| parse-ms | 4.0.0 | MIT |
| parse5 | 7.3.0 | MIT |
| path-data-parser | 0.1.0 | MIT |
| path-exists | 4.0.0 | MIT |
| path-key | 3.1.1 | MIT |
| path-key | 4.0.0 | MIT |
| pathe | 2.0.3 | MIT |
| pathval | 2.0.1 | MIT |
| picocolors | 1.1.1 | ISC |
| picomatch | 4.0.7 | MIT |
| playwright | 1.63.0 | Apache-2.0 |
| playwright-core | 1.63.0 | Apache-2.0 |
| points-on-curve | 0.2.0 | MIT |
| points-on-path | 0.2.1 | MIT |
| postcss | 8.5.28 | MIT |
| prelude-ls | 1.2.1 | MIT |
| pretty-format | 27.5.1 | MIT |
| pretty-ms | 9.3.1 | MIT |
| property-information | 7.2.0 | MIT |
| punycode | 2.3.1 | MIT |
| radix-ui | 1.6.7 | MIT |
| react | 19.3.0 | MIT |
| react-dom | 19.3.0 | MIT |
| react-is | 17.0.2 | MIT |
| react-markdown | 10.1.0 | MIT |
| react-refresh | 0.17.0 | MIT |
| react-remove-scroll | 2.7.2 | MIT |
| react-remove-scroll-bar | 2.3.8 | проверить |
| react-router | 7.18.4 | MIT |
| react-router-dom | 7.18.4 | MIT |
| react-style-singleton | 2.2.3 | MIT |
| readdirp | 5.1.1 | MIT |
| redent | 3.0.0 | MIT |
| remark-gfm | 4.0.1 | MIT |
| remark-parse | 11.0.0 | MIT |
| remark-rehype | 11.1.2 | MIT |
| remark-stringify | 11.0.0 | MIT |
| require-from-string | 2.0.2 | MIT |
| resolve-from | 4.0.0 | MIT |
| resolve-pkg-maps | 1.0.0 | MIT |
| robust-predicates | 3.0.3 | Unlicense |
| rollup | 4.63.6 | MIT |
| roughjs | 4.6.6 | MIT |
| rrweb-cssom | 0.7.1 | MIT |
| rrweb-cssom | 0.8.0 | MIT |
| rw | 1.3.3 | BSD-3-Clause |
| safer-buffer | 2.1.2 | MIT |
| saxes | 6.0.0 | ISC |
| scheduler | 0.28.0 | MIT |
| semver | 6.3.1 | ISC |
| semver | 7.8.5 | ISC |
| set-cookie-parser | 2.7.2 | MIT |
| shebang-command | 2.0.0 | MIT |
| shebang-regex | 3.0.0 | MIT |
| siginfo | 2.0.0 | ISC |
| signal-exit | 4.1.0 | ISC |
| sonner | 2.0.8 | MIT |
| source-map-js | 1.2.2 | BSD-3-Clause |
| space-separated-tokens | 2.0.2 | MIT |
| stackback | 0.0.2 | MIT |
| std-env | 3.10.0 | MIT |
| strictdom | 1.0.1 | MIT |
| string-argv | 0.3.2 | MIT |
| stringify-entities | 4.0.4 | MIT |
| strip-final-newline | 4.0.0 | MIT |
| strip-indent | 3.0.0 | MIT |
| strip-json-comments | 3.1.1 | MIT |
| strip-literal | 3.1.0 | MIT |
| style-to-js | 1.1.21 | MIT |
| style-to-object | 1.0.14 | MIT |
| stylis | 4.4.0 | MIT |
| supports-color | 7.2.0 | MIT |
| symbol-tree | 3.2.4 | MIT |
| tagged-tag | 1.0.0 | MIT |
| tailwind-merge | 3.7.0 | MIT |
| tailwindcss | 4.3.3 | MIT |
| tapable | 2.3.3 | MIT |
| tinybench | 2.9.0 | MIT |
| tinyexec | 0.3.2 | MIT |
| tinyexec | 1.3.1 | MIT |
| tinyglobby | 0.2.17 | MIT |
| tinypool | 1.1.1 | MIT |
| tinyrainbow | 2.0.0 | MIT |
| tinyspy | 4.0.6 | MIT |
| tldts | 6.1.86 | MIT |
| tldts-core | 6.1.86 | MIT |
| tough-cookie | 5.1.2 | BSD-3-Clause |
| tr46 | 5.1.1 | MIT |
| trim-lines | 3.0.1 | MIT |
| trough | 2.2.0 | MIT |
| ts-api-utils | 2.5.0 | MIT |
| ts-dedent | 2.3.0 | MIT |
| tslib | 2.8.1 | 0BSD |
| type-check | 0.4.0 | MIT |
| type-fest | 5.10.0 | (MIT OR CC0-1.0) |
| typescript | 5.9.3 | Apache-2.0 |
| typescript-eslint | 8.71.0 | MIT |
| undici | 7.29.0 | MIT |
| undici-types | 6.21.0 | MIT |
| unicorn-magic | 0.3.0 | MIT |
| unified | 11.0.5 | MIT |
| unist-util-is | 6.0.1 | MIT |
| unist-util-position | 5.0.0 | MIT |
| unist-util-stringify-position | 4.0.0 | MIT |
| unist-util-visit | 5.1.0 | MIT |
| unist-util-visit-parents | 6.0.2 | MIT |
| update-browserslist-db | 1.3.3 | MIT |
| uri-js | 4.4.1 | BSD-2-Clause |
| use-callback-ref | 1.3.3 | MIT |
| use-sidecar | 1.1.3 | MIT |
| uuid | 14.0.3 | MIT |
| vfile | 6.0.3 | MIT |
| vfile-message | 4.0.3 | MIT |
| vite | 6.4.3 | MIT |
| vite-node | 3.2.4 | MIT |
| vitest | 3.2.7 | MIT |
| w3c-xmlserializer | 5.0.0 | MIT |
| webidl-conversions | 7.0.0 | BSD-2-Clause |
| whatwg-encoding | 3.1.1 | MIT |
| whatwg-mimetype | 4.0.0 | MIT |
| whatwg-url | 14.2.0 | MIT |
| which | 2.0.2 | ISC |
| why-is-node-running | 2.3.0 | MIT |
| word-wrap | 1.2.5 | MIT |
| ws | 8.22.0 | MIT |
| xml-name-validator | 5.0.0 | Apache-2.0 |
| xmlchars | 2.2.0 | MIT |
| yallist | 3.1.1 | ISC |
| yaml | 2.9.1 | ISC |
| yocto-queue | 0.1.0 | MIT |
| yoctocolors | 2.2.0 | MIT |
| zod | 4.6.5 | MIT |
| zwitch | 2.0.4 | MIT |
