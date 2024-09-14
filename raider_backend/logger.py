"""
This module configures logging for the application using a
dictionary-based configuration.

The logging configuration includes:
- A default formatter that uses Uvicorn's DefaultFormatter with a
    specific format and date format.
- Two handlers:
- A StreamHandler that outputs logs to stderr with an INFO level.
- A FileHandler that writes logs to a file at /tmp/manager.log with a
    DEBUG level.
- A root logger that uses both handlers and has an INFO level.

The configuration is designed to disable existing loggers and not
propagate log messages to ancestor loggers.
"""

LOG_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "()": "uvicorn.logging.DefaultFormatter",
            "fmt": "%(levelprefix)s %(name)s %(asctime)s %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "default": {
            "formatter": "default",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
            "level": "INFO",
        },
        "fileHandler": {
            "formatter": "default",
            "class": "logging.FileHandler",
            "filename": "/tmp/manager.log",
            "level": "DEBUG",
            "mode": "a+",
        },
    },
    "loggers": {
        "": {
            "handlers": [
                "default",
                "fileHandler"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
