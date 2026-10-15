import sys

from pydantic import ValidationError

from car_knowledge_rag.config import Settings


def main() -> None:
    try:
        settings = Settings()
    except ValidationError as error:
        print("Invalid configuration:", file=sys.stderr)
        for issue in error.errors(include_input=False, include_url=False):
            field = ".".join(str(part) for part in issue["loc"])
            print(f"  {field}: {issue['msg']}", file=sys.stderr)
        raise SystemExit(2) from None
    print("CarKnowledgeRAG: Python environment is ready.")
    print(f"Environment: {settings.app_env}")
    print(f"Log level: {settings.log_level}")


if __name__ == "__main__":
    main()
