from __future__ import annotations

from astrbot_plugin_warframe_helper.http_utils import _read_response_bytes


class _FakeContent:
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks
        self.yielded = 0

    async def iter_chunked(self, _size: int):
        for chunk in self._chunks:
            self.yielded += 1
            yield chunk


class _FakeResponse:
    def __init__(
        self,
        chunks: list[bytes],
        *,
        content_length: str | None = None,
    ) -> None:
        self.content = _FakeContent(chunks)
        self.headers = {}
        if content_length is not None:
            self.headers["Content-Length"] = content_length


async def test_bounded_reader_rejects_content_length_before_streaming():
    response = _FakeResponse([b"should-not-be-read"], content_length="11")

    result = await _read_response_bytes(response, max_bytes=10)

    assert result is None
    assert response.content.yielded == 0


async def test_bounded_reader_stops_when_stream_exceeds_limit():
    response = _FakeResponse([b"1234", b"5678", b"not-read"])

    result = await _read_response_bytes(response, max_bytes=6)

    assert result is None
    assert response.content.yielded == 2


async def test_bounded_reader_returns_complete_payload_within_limit():
    response = _FakeResponse([b"12", b"34"], content_length="4")

    result = await _read_response_bytes(response, max_bytes=4)

    assert result == b"1234"
    assert response.content.yielded == 2


async def test_unbounded_reader_streams_complete_payload():
    response = _FakeResponse([b"alpha", b"beta"])

    result = await _read_response_bytes(response, max_bytes=None)

    assert result == b"alphabeta"


async def test_invalid_content_length_falls_back_to_stream_limit():
    response = _FakeResponse([b"123", b"456"], content_length="invalid")

    result = await _read_response_bytes(response, max_bytes=5)

    assert result is None
    assert response.content.yielded == 2

