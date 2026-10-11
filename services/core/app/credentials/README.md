# Open Badge 3.0 — `app/credentials`

Выпуск подписанного кредита подтверждённого грейда (Ed25519, `eddsa-jcs-2022`, издатель `did:web`), отзыв и публичная проверка. Выпуск только для того, что кандидат сам сделал публичным.

| Файл | Что |
|---|---|
| `service.py` | выпуск, отзыв, проверка |
| `signing.py` | подпись и проверка |
| `router.py` | `/me/credentials`, `/public/credentials/*`, `/.well-known/did.json` |

Подробнее: [ADR-0022](../../../../docs/adr/0022-open-badge-jcs.md).
