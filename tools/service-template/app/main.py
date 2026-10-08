from fsp_platform.app import create_app
from fsp_platform.logging import configure_logging

from app.config import Settings

settings = Settings()
configure_logging(settings.service_name, settings.log_level)
app = create_app(settings.service_name)
