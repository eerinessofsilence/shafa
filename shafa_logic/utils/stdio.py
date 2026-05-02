from __future__ import annotations

import sys
from typing import TextIO


class _SafeTextStream:
    def __init__(self, stream: TextIO) -> None:
        self._stream = stream
        self._shafa_safe_stream = True

    @property
    def encoding(self) -> str | None:
        return getattr(self._stream, "encoding", None)

    def write(self, text: str) -> int:
        try:
            return self._stream.write(text)
        except UnicodeEncodeError:
            encoding = self.encoding or "utf-8"
            safe_text = text.encode(encoding, errors="replace").decode(
                encoding,
                errors="replace",
            )
            return self._stream.write(safe_text)

    def flush(self) -> None:
        self._stream.flush()

    def isatty(self) -> bool:
        return self._stream.isatty()

    def writable(self) -> bool:
        return self._stream.writable()

    def fileno(self) -> int:
        return self._stream.fileno()

    @property
    def buffer(self):
        return getattr(self._stream, "buffer")

    def __getattr__(self, name: str):
        return getattr(self._stream, name)


def _protect_stream(name: str) -> None:
    stream = getattr(sys, name, None)
    if stream is None or getattr(stream, "_shafa_safe_stream", False):
        return

    reconfigure = getattr(stream, "reconfigure", None)
    if callable(reconfigure):
        try:
            reconfigure(errors="replace")
        except (AttributeError, OSError, ValueError):
            pass

    setattr(sys, name, _SafeTextStream(stream))


def install_safe_stdio() -> None:
    _protect_stream("stdout")
    _protect_stream("stderr")
