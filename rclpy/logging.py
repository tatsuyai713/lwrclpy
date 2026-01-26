"""rclpy-compatible logging module.

Provides get_logger() function and logging severity levels compatible with rclpy.
"""
import logging
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


# Create a dedicated handler for ROS-style logging
_ros_handler: Optional[logging.Handler] = None
_configured_loggers = set()


def _ensure_ros_handler() -> logging.Handler:
    """Get or create the shared ROS logging handler."""
    global _ros_handler
    if _ros_handler is None:
        _ros_handler = logging.StreamHandler(sys.stderr)
        _ros_handler.setFormatter(
            logging.Formatter("[%(levelname)s] [%(name)s]: %(message)s")
        )
    return _ros_handler


class RcutilsLogger:
    """Logger class compatible with rclpy's rcutils logger interface."""
    
    def __init__(self, name: str):
        self._name = name
        self._logger = logging.getLogger(name)
        
        # Configure logger if not already done
        if name not in _configured_loggers:
            self._logger.addHandler(_ensure_ros_handler())
            self._logger.setLevel(logging.DEBUG)  # Let handler filter
            self._logger.propagate = False
            _configured_loggers.add(name)
    
    @property
    def name(self) -> str:
        return self._name
    
    def set_level(self, level: LoggingSeverity):
        """Set the logging level."""
        self._logger.setLevel(level.value)
    
    def get_effective_level(self) -> LoggingSeverity:
        """Get the effective logging level."""
        level = self._logger.getEffectiveLevel()
        try:
            return LoggingSeverity(level)
        except ValueError:
            return LoggingSeverity.INFO
    
    def debug(self, message: str, *args, **kwargs):
        """Log a debug message."""
        self._logger.debug(message, *args, **kwargs)
    
    def info(self, message: str, *args, **kwargs):
        """Log an info message."""
        self._logger.info(message, *args, **kwargs)
    
    def warn(self, message: str, *args, **kwargs):
        """Log a warning message."""
        self._logger.warning(message, *args, **kwargs)
    
    def warning(self, message: str, *args, **kwargs):
        """Log a warning message (alias for warn)."""
        self._logger.warning(message, *args, **kwargs)
    
    def error(self, message: str, *args, **kwargs):
        """Log an error message."""
        self._logger.error(message, *args, **kwargs)
    
    def fatal(self, message: str, *args, **kwargs):
        """Log a fatal message."""
        self._logger.critical(message, *args, **kwargs)
    
    def log(self, level: int, message: str, *args, **kwargs):
        """Log at the specified level."""
        self._logger.log(level, message, *args, **kwargs)
    
    # Throttled logging (rclpy compatibility - simple implementation)
    def debug_throttle(self, period: float, message: str, *args, **kwargs):
        """Log debug message throttled to once per period seconds."""
        self.debug(message, *args, **kwargs)
    
    def info_throttle(self, period: float, message: str, *args, **kwargs):
        """Log info message throttled to once per period seconds."""
        self.info(message, *args, **kwargs)
    
    def warn_throttle(self, period: float, message: str, *args, **kwargs):
        """Log warning message throttled to once per period seconds."""
        self.warn(message, *args, **kwargs)
    
    def error_throttle(self, period: float, message: str, *args, **kwargs):
        """Log error message throttled to once per period seconds."""
        self.error(message, *args, **kwargs)
    
    # Once logging (rclpy compatibility - simple implementation)
    def debug_once(self, message: str, *args, **kwargs):
        """Log debug message only once."""
        self.debug(message, *args, **kwargs)
    
    def info_once(self, message: str, *args, **kwargs):
        """Log info message only once."""
        self.info(message, *args, **kwargs)
    
    def warn_once(self, message: str, *args, **kwargs):
        """Log warning message only once."""
        self.warn(message, *args, **kwargs)
    
    def error_once(self, message: str, *args, **kwargs):
        """Log error message only once."""
        self.error(message, *args, **kwargs)
    
    # Skip first logging
    def debug_skipfirst(self, message: str, *args, **kwargs):
        """Log debug message, skipping the first occurrence."""
        self.debug(message, *args, **kwargs)
    
    def info_skipfirst(self, message: str, *args, **kwargs):
        """Log info message, skipping the first occurrence."""
        self.info(message, *args, **kwargs)
    
    def warn_skipfirst(self, message: str, *args, **kwargs):
        """Log warning message, skipping the first occurrence."""
        self.warn(message, *args, **kwargs)
    
    def error_skipfirst(self, message: str, *args, **kwargs):
        """Log error message, skipping the first occurrence."""
        self.error(message, *args, **kwargs)
    
    def get_child(self, suffix: str) -> "RcutilsLogger":
        """Get a child logger with the given suffix."""
        child_name = f"{self._name}.{suffix}"
        return RcutilsLogger(child_name)


def get_logger(name: str) -> RcutilsLogger:
    """Get a logger with the given name.
    
    This is the main entry point for getting loggers in rclpy style.
    
    Args:
        name: The name of the logger (typically the node name)
    
    Returns:
        RcutilsLogger instance
    """
    return RcutilsLogger(name)


def set_logger_level(name: str, level: LoggingSeverity):
    """Set the logging level for a named logger."""
    logger = get_logger(name)
    logger.set_level(level)


__all__ = [
    "get_logger",
    "set_logger_level",
    "LoggingSeverity",
    "RcutilsLogger",
]
