"""AsyncAPI 3.0 всех событий, команд и `ui.user.*` из реестров контрактов.

У каждого сервиса FastStream дополнительно отдаёт свой `/asyncapi` (только его подписки);
этот документ — общий каталог: `python -m fsp_contracts.asyncapi > asyncapi.json`.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from pydantic import BaseModel
from pydantic.json_schema import models_json_schema

from fsp_contracts.commands import COMMANDS, COMMANDS_EXCHANGE, LLM_MAX_PRIORITY
from fsp_contracts.envelope import Envelope
from fsp_contracts.events import EVENT_PRODUCERS, EVENTS, EVENTS_EXCHANGE
from fsp_contracts.ui import UI_EVENTS, UI_EXCHANGE, UiMessage

REF = "#/components/schemas/{model}"


def _schemas(
    models: list[type[BaseModel]],
) -> tuple[dict[type[BaseModel], str], dict[str, Any]]:
    keys = [(m, "serialization") for m in models]
    refs, top = models_json_schema(keys, ref_template=REF)
    names = {m: refs[(m, "serialization")]["$ref"] for m in models}
    return names, top.get("$defs", {})


def _envelope_payload(envelope_ref: str, type_: str, model_ref: str) -> dict[str, Any]:
    return {
        "allOf": [
            {"$ref": envelope_ref},
            {
                "type": "object",
                "properties": {"type": {"const": type_}, "payload": {"$ref": model_ref}},
            },
        ]
    }


def _msg_name(type_: str) -> str:
    return type_.replace(".", "_")


def build_asyncapi(version: str = "1") -> dict[str, Any]:
    models = sorted(
        {*EVENTS.values(), *(s.model for s in COMMANDS.values()), *UI_EVENTS.values()},
        key=lambda m: (m.__module__, m.__name__),
    )
    refs, schemas = _schemas([Envelope, UiMessage, *models])

    channels: dict[str, Any] = {}
    operations: dict[str, Any] = {}
    messages: dict[str, Any] = {}

    def add(
        channel: str, binding: dict[str, Any], type_: str, model: type, desc: str, op: str
    ) -> None:
        name = _msg_name(f"{channel}__{type_}")
        messages[name] = {
            "name": type_,
            "title": type_,
            "summary": desc,
            "payload": _envelope_payload(refs[Envelope], type_, refs[model]),
        }
        ch = channels.setdefault(
            _msg_name(channel),
            {"address": channel, "messages": {}, "bindings": {"amqp": binding}},
        )
        ch["messages"][name] = {"$ref": f"#/components/messages/{name}"}
        operations[f"{op}_{name}"] = {
            "action": op,
            "channel": {"$ref": f"#/channels/{_msg_name(channel)}"},
            "messages": [{"$ref": f"#/channels/{_msg_name(channel)}/messages/{name}"}],
        }

    for type_, model in EVENTS.items():
        binding = {
            "is": "routingKey",
            "exchange": {"name": EVENTS_EXCHANGE, "type": "topic", "durable": True},
        }
        add(type_, binding, type_, model, f"Событие от {EVENT_PRODUCERS[type_]}", "send")

    for type_, spec in COMMANDS.items():
        queue: dict[str, Any] = {"name": spec.queue, "durable": True}
        if spec.queue == "ml.llm":
            queue["x-max-priority"] = LLM_MAX_PRIORITY
        binding = {
            "is": "routingKey",
            "exchange": {"name": COMMANDS_EXCHANGE, "type": "direct", "durable": True},
            "queue": queue,
        }
        prio = f", приоритет {spec.priority}" if spec.priority is not None else ""
        add(spec.queue, binding, type_, spec.model, f"Команда для {spec.consumer}{prio}", "receive")

    ui_binding = {"is": "routingKey", "exchange": {"name": UI_EXCHANGE, "type": "topic"}}
    for event, model in UI_EVENTS.items():
        name = _msg_name(f"ui__{event}")
        messages[name] = {
            "name": event,
            "title": f"SSE {event}",
            "payload": {
                "allOf": [
                    {"$ref": refs[UiMessage]},
                    {
                        "type": "object",
                        "properties": {
                            "event": {"const": event},
                            "data": {"$ref": refs[model]},
                        },
                    },
                ]
            },
        }
        ch = channels.setdefault(
            "ui_user",
            {"address": "ui.user.{user_id}", "messages": {}, "bindings": {"amqp": ui_binding}},
        )
        ch.setdefault("parameters", {"user_id": {"description": "UUID пользователя"}})
        ch["messages"][name] = {"$ref": f"#/components/messages/{name}"}
    operations["send_ui_user"] = {
        "action": "send",
        "channel": {"$ref": "#/channels/ui_user"},
    }

    return {
        "asyncapi": "3.0.0",
        "info": {
            "title": "ФСП Карьера: события и команды",
            "version": version,
            "description": "Сгенерировано из packages/contracts.",
        },
        "defaultContentType": "application/json",
        "channels": channels,
        "operations": operations,
        "components": {"messages": messages, "schemas": schemas},
    }


def main() -> None:
    json.dump(build_asyncapi(), sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
