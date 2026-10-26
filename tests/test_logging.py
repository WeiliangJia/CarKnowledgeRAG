import logging
import subprocess
import sys
import unittest
from pathlib import Path

from car_knowledge_rag.logging_config import UTCFormatter


class LoggingTest(unittest.TestCase):
    def run_logging(self, code: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-c", code],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )

    def test_formatter_uses_utc(self) -> None:
        formatter = UTCFormatter("%(asctime)s", datefmt="%Y-%m-%dT%H:%M:%SZ")
        record = logging.LogRecord("car_knowledge_rag", logging.INFO, "", 0, "", (), None)
        record.created = 0
        self.assertEqual(formatter.format(record), "1970-01-01T00:00:00Z")

    def test_console_log_format_and_destination(self) -> None:
        result = self.run_logging(
            "import logging; "
            "from car_knowledge_rag.logging_config import configure_logging; "
            "configure_logging(); "
            "logging.getLogger('car_knowledge_rag').info('startup check')"
        )
        self.assertEqual(result.stdout, "")
        self.assertRegex(
            result.stderr,
            r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z INFO car_knowledge_rag startup check\r?\n$",
        )

    def test_exception_demo_compares_error_and_traceback(self) -> None:
        result = self.run_logging(
            "from car_knowledge_rag.logging_demo import main; main()"
        )
        self.assertEqual(result.stdout, "")
        message_only, traceback_output = result.stderr.split(
            "Demo conversion failed (with traceback)", maxsplit=1
        )
        self.assertIn("Demo conversion failed (message only)", message_only)
        self.assertNotIn("Traceback", message_only)
        self.assertEqual(result.stderr.count("Traceback (most recent call last):"), 1)
        self.assertIn("logging_demo.py", traceback_output)
        self.assertIn("ValueError:", traceback_output)
        self.assertIn("Demo completed; the demonstration error was handled", traceback_output)
        self.assertEqual(result.returncode, 0)

    def test_importing_demo_does_not_run_it(self) -> None:
        result = self.run_logging("import car_knowledge_rag.logging_demo")
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")

    def test_level_filters_events(self) -> None:
        levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        for index, level in enumerate(levels):
            with self.subTest(level=level):
                result = self.run_logging(
                    "import logging; "
                    "from car_knowledge_rag.logging_config import configure_logging; "
                    f"configure_logging({level!r}); "
                    "logger = logging.getLogger('car_knowledge_rag'); "
                    "logger.debug('debug event'); "
                    "logger.info('info event'); "
                    "logger.warning('warning event'); "
                    "logger.error('error event'); "
                    "logger.critical('critical event')"
                )
                actual = [line.split()[1] for line in result.stderr.splitlines()]
                self.assertEqual(actual, levels[index:])
                self.assertEqual(result.stdout, "")

    def test_reconfiguration_replaces_handler_and_level(self) -> None:
        for first, second, expected in [
            ("INFO", "INFO", ["INFO", "ERROR"]),
            ("DEBUG", "ERROR", ["ERROR"]),
            ("ERROR", "DEBUG", ["DEBUG", "INFO", "ERROR"]),
        ]:
            with self.subTest(first=first, second=second):
                result = self.run_logging(
                    "import logging; "
                    "from car_knowledge_rag.logging_config import configure_logging; "
                    "logging.basicConfig(level=logging.DEBUG); "
                    f"configure_logging({first!r}); "
                    f"configure_logging({second!r}); "
                    "logger = logging.getLogger('car_knowledge_rag.retrieval'); "
                    "logger.debug('debug event'); "
                    "logger.info('info event'); "
                    "logger.error('error event')"
                )
                actual = [line.split()[1] for line in result.stderr.splitlines()]
                self.assertEqual(actual, expected)
                self.assertTrue(
                    all("car_knowledge_rag.retrieval" in line for line in result.stderr.splitlines())
                )
