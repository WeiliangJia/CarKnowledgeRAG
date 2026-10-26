import logging
import logging.config
import time


class UTCFormatter(logging.Formatter):
    converter = time.gmtime


def configure_logging(level: str = "INFO") -> None:
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "utc": {
                    "()": UTCFormatter,
                    "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
                    "datefmt": "%Y-%m-%dT%H:%M:%SZ",
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stderr",
                    "formatter": "utc",
                }
            },
            "loggers": {
                "car_knowledge_rag": {
                    "level": level,
                    "handlers": ["console"],
                    "propagate": False,
                }
            },
        }
    )
