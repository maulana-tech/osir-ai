"""CSV upload size cap (DoS guard): reject by declared size before reading."""

import pytest

from apps.composer import csv_import


class _Upload:
    def __init__(self, size, content=b""):
        self.size = size
        self.content = content
        self.reads = 0

    def read(self):
        self.reads += 1
        return self.content


def test_oversized_csv_rejected_without_reading():
    upload = _Upload(csv_import.MAX_UPLOAD_BYTES + 1)
    with pytest.raises(ValueError, match="too large"):
        csv_import.parse_upload(upload)
    assert upload.reads == 0


def test_under_cap_csv_proceeds_to_mapping():
    headers, rows = csv_import.parse_upload(_Upload(40, b"date,platform,caption\n2026-05-01,instagram,Hello\n"))
    assert headers == ["date", "platform", "caption"] and rows == [["2026-05-01", "instagram", "Hello"]]
    assert csv_import.auto_mapping(headers) == {"date": 0, "platforms": 1, "caption": 2}
