import _test_path  # noqa: F401
import io
import sys

from utils.stdio import install_safe_stdio


class _BrokenEncodingStream(io.StringIO):
    encoding = "cp1251"

    def write(self, value: str) -> int:
        value.encode(self.encoding)
        return super().write(value)


def test_install_safe_stdio_replaces_unencodable_stdout(monkeypatch) -> None:
    stream = _BrokenEncodingStream()
    monkeypatch.setattr(sys, "stdout", stream)

    install_safe_stdio()
    print("test ʼ value")

    assert stream.getvalue() == "test ? value\n"
