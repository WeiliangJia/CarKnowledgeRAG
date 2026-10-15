import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

from car_knowledge_rag.__main__ import main
from car_knowledge_rag.config import Settings


class SettingsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.enterContext(patch.dict(os.environ, {}, clear=True))
        directory = self.enterContext(tempfile.TemporaryDirectory())
        previous_directory = Path.cwd()
        self.addCleanup(os.chdir, previous_directory)
        os.chdir(directory)

    def test_defaults(self) -> None:
        settings = Settings()
        self.assertEqual(settings.app_env, "development")
        self.assertEqual(settings.log_level, "INFO")

    def test_main_displays_defaults(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            main()
        self.assertEqual(
            output.getvalue().splitlines(),
            [
                "CarKnowledgeRAG: Python environment is ready.",
                "Environment: development",
                "Log level: INFO",
            ],
        )

    def test_environment_overrides_defaults(self) -> None:
        os.environ.update(APP_ENV="production", LOG_LEVEL="DEBUG")
        settings = Settings()
        self.assertEqual(settings.app_env, "production")
        self.assertEqual(settings.log_level, "DEBUG")

    def test_dotenv_overrides_defaults(self) -> None:
        Path(".env").write_text(
            "# 本地配置\nAPP_ENV=test\nLOG_LEVEL=WARNING\n", encoding="utf-8"
        )
        settings = Settings()
        self.assertEqual(settings.app_env, "test")
        self.assertEqual(settings.log_level, "WARNING")

    def test_example_file_is_valid(self) -> None:
        example = Path(__file__).resolve().parents[1] / ".env.example"
        Path(".env").write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
        settings = Settings()
        self.assertEqual(settings.app_env, "development")
        self.assertEqual(settings.log_level, "INFO")

    def test_environment_overrides_dotenv(self) -> None:
        Path(".env").write_text("APP_ENV=test\nLOG_LEVEL=WARNING\n", encoding="utf-8")
        os.environ["LOG_LEVEL"] = "ERROR"
        settings = Settings()
        self.assertEqual(settings.app_env, "test")
        self.assertEqual(settings.log_level, "ERROR")

    def test_invalid_environment_does_not_fall_back_to_dotenv(self) -> None:
        Path(".env").write_text("LOG_LEVEL=INFO\n", encoding="utf-8")
        os.environ["LOG_LEVEL"] = "invalid"
        with self.assertRaises(ValidationError):
            Settings()

    def test_invalid_values_are_rejected(self) -> None:
        for field, value in [("APP_ENV", "prod"), ("LOG_LEVEL", "debug"), ("LOG_LEVEL", "")]:
            with self.subTest(field=field, value=value):
                with patch.dict(os.environ, {field: value}):
                    with self.assertRaises(ValidationError):
                        Settings()

    def test_unknown_dotenv_field_is_rejected(self) -> None:
        Path(".env").write_text("LOG_LEVLE=INFO\n", encoding="utf-8")
        with self.assertRaises(ValidationError):
            Settings()

    def test_main_reports_invalid_config_without_input_value(self) -> None:
        os.environ["LOG_LEVEL"] = "private-invalid-value"
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            with self.assertRaises(SystemExit) as raised:
                main()
        self.assertEqual(raised.exception.code, 2)
        self.assertEqual(output.getvalue(), "")
        self.assertIn("log_level:", errors.getvalue())
        self.assertNotIn("private-invalid-value", errors.getvalue())
