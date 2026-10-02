from fsp_platform.config import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "core"
    # SSE (api.md §2.8): heartbeat каждые 20 с; шина ui отключается в тестах без брокера
    sse_heartbeat_seconds: float = 20.0
    ui_bus_enabled: bool = True
