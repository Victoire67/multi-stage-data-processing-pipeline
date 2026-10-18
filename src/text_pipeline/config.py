"""Runtime configuration read from environment variables.

=========================  ===================================  ==========
Variable                   Meaning                              Default
=========================  ===================================  ==========
``PIPELINE_DATABASE_URL``  PostgreSQL DSN used by the storer    *(unset)*
``PIPELINE_LOG_LEVEL``     Minimum log level                    ``INFO``
``PIPELINE_LOG_FORMAT``    ``json`` or ``text``                 ``json``
=========================  ===================================  ==========
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

_VALID_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
_VALID_FORMATS = {"json", "text"}


@dataclass(frozen=True, slots=True)
class Settings:
    """Validated application settings.

    Attributes:
        database_url: PostgreSQL connection string, or ``None``.
        log_level: Minimum log level name.
        log_format: ``"json"`` or ``"text"``.
    """

    database_url: str | None = None
    log_level: str = "INFO"
    log_format: str = "json"

    def __post_init__(self) -> None:
        """Validate the settings.

        Raises:
            ValueError: If the log level or format is unknown.
        """
        if self.log_level not in _VALID_LEVELS:
            raise ValueError(f"log_level must be one of {sorted(_VALID_LEVELS)}")
        if self.log_format not in _VALID_FORMATS:
            raise ValueError(f"log_format must be one of {sorted(_VALID_FORMATS)}")

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
        """Build settings from environment variables.

        Args:
            environ: Mapping to read from; defaults to ``os.environ``.

        Returns:
            The validated settings.
        """
        env = os.environ if environ is None else environ
        return cls(
            database_url=env.get("PIPELINE_DATABASE_URL") or None,
            log_level=env.get("PIPELINE_LOG_LEVEL", "INFO").upper(),
            log_format=env.get("PIPELINE_LOG_FORMAT", "json").lower(),
        )
