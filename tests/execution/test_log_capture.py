import logging

from protest.execution.log_capture import LogCapture


class TestLogCapture:
    def test_records_property_returns_list(self) -> None:
        records: list[logging.LogRecord] = []
        capture = LogCapture(records)

        assert capture.records is records

    def test_text_property_formats_records(self) -> None:
        logger = logging.getLogger("test.text")
        record1 = logger.makeRecord(
            "test.text", logging.INFO, "file.py", 1, "first message", (), None
        )
        record2 = logger.makeRecord(
            "test.text", logging.WARNING, "file.py", 2, "second message", (), None
        )

        capture = LogCapture([record1, record2])

        expected_text = "INFO:test.text:first message\nWARNING:test.text:second message"
        assert capture.text == expected_text

    def test_text_property_empty_when_no_records(self) -> None:
        capture = LogCapture([])

        assert capture.text == ""

    def test_at_level_filters_by_level_string(self) -> None:
        logger = logging.getLogger("test.filter")
        debug_record = logger.makeRecord(
            "test.filter", logging.DEBUG, "file.py", 1, "debug", (), None
        )
        info_record = logger.makeRecord(
            "test.filter", logging.INFO, "file.py", 2, "info", (), None
        )
        warning_record = logger.makeRecord(
            "test.filter", logging.WARNING, "file.py", 3, "warning", (), None
        )

        capture = LogCapture([debug_record, info_record, warning_record])

        warning_and_above = capture.at_level("WARNING")
        assert len(warning_and_above) == 1
        assert warning_and_above[0].getMessage() == "warning"

        info_and_above = capture.at_level("INFO")
        assert len(info_and_above) == 2

    def test_at_level_filters_by_level_int(self) -> None:
        logger = logging.getLogger("test.filter_int")
        debug_record = logger.makeRecord(
            "test.filter_int", logging.DEBUG, "file.py", 1, "debug", (), None
        )
        error_record = logger.makeRecord(
            "test.filter_int", logging.ERROR, "file.py", 2, "error", (), None
        )

        capture = LogCapture([debug_record, error_record])

        errors = capture.at_level(logging.ERROR)
        assert len(errors) == 1
        assert errors[0].getMessage() == "error"

    def test_at_level_case_insensitive(self) -> None:
        logger = logging.getLogger("test.case")
        warning_record = logger.makeRecord(
            "test.case", logging.WARNING, "file.py", 1, "warning", (), None
        )

        capture = LogCapture([warning_record])

        assert len(capture.at_level("warning")) == 1
        assert len(capture.at_level("WARNING")) == 1
        assert len(capture.at_level("Warning")) == 1

    def test_clear_empties_records(self) -> None:
        logger = logging.getLogger("test.clear")
        record = logger.makeRecord(
            "test.clear", logging.INFO, "file.py", 1, "message", (), None
        )

        records = [record]
        capture = LogCapture(records)

        assert len(capture.records) == 1

        capture.clear()

        assert len(capture.records) == 0
        assert len(records) == 0
