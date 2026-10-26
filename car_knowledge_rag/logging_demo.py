"""An explicit teaching demo; never called by normal application startup."""

import logging

from car_knowledge_rag.logging_config import configure_logging


logger = logging.getLogger("car_knowledge_rag.logging_demo")


def main() -> None:
    configure_logging("INFO")
    try:
        int("demo-not-a-number")
    except ValueError:
        # Log twice only to compare the APIs; real failures should not be logged twice here.
        logger.error("Demo conversion failed (message only)")
        logger.exception("Demo conversion failed (with traceback)")
    logger.info("Demo completed; the demonstration error was handled")


if __name__ == "__main__":
    main()
