import logging
import sys

from pydantic import ValidationError

from car_knowledge_rag.config import Settings
from car_knowledge_rag.logging_config import configure_logging


logger = logging.getLogger("car_knowledge_rag")


def main() -> None:
    try:
        settings = Settings()
    except ValidationError as error:
        print("Invalid configuration:", file=sys.stderr)
        for issue in error.errors(include_input=False, include_url=False):
            field = ".".join(str(part) for part in issue["loc"])
            print(f"  {field}: {issue['msg']}", file=sys.stderr)
        raise SystemExit(2) from None
    configure_logging(settings.log_level)
    logger.info("Application started environment=%s", settings.app_env)


if __name__ == "__main__":
    main()
