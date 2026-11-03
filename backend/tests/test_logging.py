import logging

from app.core.config import Settings
from app.main import create_app


def test_app_info_lines_are_shown_and_third_party_loggers_are_left_alone() -> None:
    create_app(Settings(_env_file=None, app_env="test"))
    app_logger = logging.getLogger("app")
    assert app_logger.isEnabledFor(logging.INFO)
    assert len(app_logger.handlers) == 1
    create_app(Settings(_env_file=None, app_env="test"))
    assert len(app_logger.handlers) == 1  # not added twice
    # httpx logs full URLs; SerpApi puts its key there, so httpx stays untouched.
    assert not logging.getLogger("httpx").handlers
