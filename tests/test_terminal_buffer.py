from pysm.windows.pty import TerminalBuffer


def test_terminal_buffer_keeps_recent_content() -> None:
    buffer = TerminalBuffer(max_bytes=8)
    buffer.append("1234")
    buffer.append("56")
    buffer.append("7890")
    sequence, content = buffer.snapshot()
    assert sequence == 3
    assert content.endswith("7890")
    assert "1234" not in content

