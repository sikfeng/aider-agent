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
