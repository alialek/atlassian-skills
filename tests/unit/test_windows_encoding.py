from __future__ import annotations

import sys

import pytest

from atlassian_skills.cli.main import _configure_windows_encoding


class FakeStream:
    """Stand-in for a TextIOWrapper that records reconfigure() calls."""

    def __init__(self) -> None:
        self.reconfigure_calls: list[dict[str, object]] = []

    def reconfigure(self, **kwargs: object) -> None:
        self.reconfigure_calls.append(kwargs)


class StreamWithoutReconfigure:
    """Stand-in for a stream that lacks reconfigure() — must not crash."""


def _patch_streams(monkeypatch: pytest.MonkeyPatch, stream_factory: type) -> tuple[object, object, object]:
    stdout = stream_factory()
    stderr = stream_factory()
    stdin = stream_factory()
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)
    monkeypatch.setattr(sys, "stdin", stdin)
    return stdout, stderr, stdin


class TestConfigureWindowsEncoding:
    def test_reconfigures_all_three_streams_on_win32(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stdout, stderr, stdin = _patch_streams(monkeypatch, FakeStream)
        monkeypatch.setattr(sys, "platform", "win32")

        _configure_windows_encoding()

        expected = [{"encoding": "utf-8", "errors": "replace"}]
        assert stdout.reconfigure_calls == expected  # type: ignore[attr-defined]
        assert stderr.reconfigure_calls == expected  # type: ignore[attr-defined]
        assert stdin.reconfigure_calls == expected  # type: ignore[attr-defined]

    def test_is_noop_on_linux(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stdout, stderr, stdin = _patch_streams(monkeypatch, FakeStream)
        monkeypatch.setattr(sys, "platform", "linux")

        _configure_windows_encoding()

        assert stdout.reconfigure_calls == []  # type: ignore[attr-defined]
        assert stderr.reconfigure_calls == []  # type: ignore[attr-defined]
        assert stdin.reconfigure_calls == []  # type: ignore[attr-defined]

    def test_is_noop_on_macos(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stdout, _, _ = _patch_streams(monkeypatch, FakeStream)
        monkeypatch.setattr(sys, "platform", "darwin")

        _configure_windows_encoding()

        assert stdout.reconfigure_calls == []  # type: ignore[attr-defined]

    def test_streams_without_reconfigure_do_not_crash(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_streams(monkeypatch, StreamWithoutReconfigure)
        monkeypatch.setattr(sys, "platform", "win32")

        _configure_windows_encoding()  # must not raise


class TestEncodingRegressionSmoke:
    """Simulate a cp949 stdout and confirm atls CLI output does not crash on em dash."""

    def test_em_dash_through_reconfigured_stdout(self, capsys: pytest.CaptureFixture[str]) -> None:
        import io

        # Build a cp949-backed TextIOWrapper and verify raw encode would fail.
        buf = io.BytesIO()
        cp949_wrapper = io.TextIOWrapper(buf, encoding="cp949", write_through=True)
        with pytest.raises(UnicodeEncodeError):
            cp949_wrapper.write("— em dash —")
            cp949_wrapper.flush()

        # After reconfigure, the same payload writes cleanly.
        cp949_wrapper.reconfigure(encoding="utf-8", errors="replace")
        cp949_wrapper.write("— em dash —")
        cp949_wrapper.flush()
        cp949_wrapper.detach()
        assert "— em dash —".encode() in buf.getvalue()
