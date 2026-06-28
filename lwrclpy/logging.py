import logging
import os
import sys
from enum import IntEnum
from typing import Optional


class LoggingSeverity(IntEnum):
    """Logging severity levels matching rclpy."""

    UNSET = 0
    DEBUG = 10
    INFO = 20
    WARN = 30
    ERROR = 40
    FATAL = 50


_ros_handler: Optional[logging.Handler] = None
_configured_loggers = set()


def _ensure_ros_handler() -> logging.Handler:
    global _ros_handler
    if _ros_handler is None:
        _ros_handler = logging.StreamHandler(sys.stderr)
        _ros_handler.setFormatter(logging.Formatter("[%(levelname)s] [%(name)s]: %(message)s"))
    return _ros_handler


class RcutilsLogger:
    """Logger class compatible with rclpy's rcutils logger interface."""

    def __init__(self, name: str):
        self._name = name
        self._logger = logging.getLogger(name)
        if name not in _configured_loggers:
            self._logger.addHandler(_ensure_ros_handler())
            self._logger.setLevel(logging.DEBUG)
            self._logger.propagate = False
            _configured_loggers.add(name)

    @property
    def name(self) -> str:
        return self._name

    def set_level(self, level: LoggingSeverity):
        self._logger.setLevel(level.value if hasattr(level, "value") else level)

    def get_effective_level(self) -> LoggingSeverity:
        level = self._logger.getEffectiveLevel()
        try:
            return LoggingSeverity(level)
        except ValueError:
            return LoggingSeverity.INFO

    def debug(self, message: str, *args, **kwargs):
        self._logger.debug(message, *args, **kwargs)

    def info(self, message: str, *args, **kwargs):
        self._logger.info(message, *args, **kwargs)

    def warn(self, message: str, *args, **kwargs):
        self._logger.warning(message, *args, **kwargs)

    def warning(self, message: str, *args, **kwargs):
        self._logger.warning(message, *args, **kwargs)

    def error(self, message: str, *args, **kwargs):
        self._logger.error(message, *args, **kwargs)

    def fatal(self, message: str, *args, **kwargs):
        self._logger.critical(message, *args, **kwargs)

    def critical(self, message: str, *args, **kwargs):
        self._logger.critical(message, *args, **kwargs)

    def log(self, level: int, message: str, *args, **kwargs):
        self._logger.log(level, message, *args, **kwargs)

    def get_child(self, suffix: str) -> "RcutilsLogger":
        return RcutilsLogger(f"{self._name}.{suffix}")

    def debug_throttle(self, period: float, message: str, *args, **kwargs):
        self.debug(message, *args, **kwargs)

    def info_throttle(self, period: float, message: str, *args, **kwargs):
        self.info(message, *args, **kwargs)

    def warn_throttle(self, period: float, message: str, *args, **kwargs):
        self.warn(message, *args, **kwargs)

    def warning_throttle(self, period: float, message: str, *args, **kwargs):
        self.warning(message, *args, **kwargs)

    def error_throttle(self, period: float, message: str, *args, **kwargs):
        self.error(message, *args, **kwargs)

    def debug_once(self, message: str, *args, **kwargs):
        self.debug(message, *args, **kwargs)

    def info_once(self, message: str, *args, **kwargs):
        self.info(message, *args, **kwargs)

    def warn_once(self, message: str, *args, **kwargs):
        self.warn(message, *args, **kwargs)

    def warning_once(self, message: str, *args, **kwargs):
        self.warning(message, *args, **kwargs)

    def error_once(self, message: str, *args, **kwargs):
        self.error(message, *args, **kwargs)

    def debug_skipfirst(self, message: str, *args, **kwargs):
        self.debug(message, *args, **kwargs)

    def info_skipfirst(self, message: str, *args, **kwargs):
        self.info(message, *args, **kwargs)

    def warn_skipfirst(self, message: str, *args, **kwargs):
        self.warn(message, *args, **kwargs)

    def warning_skipfirst(self, message: str, *args, **kwargs):
        self.warning(message, *args, **kwargs)

    def error_skipfirst(self, message: str, *args, **kwargs):
        self.error(message, *args, **kwargs)


def get_logger(name: str) -> RcutilsLogger:
    return RcutilsLogger(name)


def set_logger_level(name: str, level: LoggingSeverity):
    get_logger(name).set_level(level)


def get_logger_effective_level(name: str) -> LoggingSeverity:
    return get_logger(name).get_effective_level()


def get_logging_directory() -> str:
    return os.environ.get("ROS_LOG_DIR") or os.environ.get("RCUTILS_LOGGING_DIRECTORY") or os.getcwd()


def initialize():
    _ensure_ros_handler()


def shutdown():
    global _ros_handler
    handler = _ros_handler
    if handler is None:
        return
    for name in list(_configured_loggers):
        logging.getLogger(name).removeHandler(handler)
    handler.close()
    _configured_loggers.clear()
    _ros_handler = None


__all__ = [
    "LoggingSeverity",
    "RcutilsLogger",
    "get_logger",
    "get_logger_effective_level",
    "get_logging_directory",
    "initialize",
    "set_logger_level",
    "shutdown",
]
