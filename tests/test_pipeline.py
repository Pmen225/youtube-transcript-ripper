"""Check the text-cleaning and chunking rules used by every export."""

from pipeline import clean_transcript, split_text


def test_clean_transcript_removes_vtt_timing_and_duplicate_lines() -> None:
    sample = """WEBVTT

1
00:00:01.000 --> 00:00:03.000
Hello &amp; welcome

2
00:00:03.000 --> 00:00:05.000
Hello &amp; welcome
"""
    assert clean_transcript(sample) == "Hello & welcome"


def test_split_text_never_exceeds_limit() -> None:
    parts = split_text("word " * 30, max_chars=40)
    assert len(parts) > 1
    assert all(len(part) <= 40 for part in parts)
    assert "".join(parts).replace(" ", "") == ("word" * 30)


def test_split_text_rejects_bad_limit() -> None:
    try:
        split_text("hello", max_chars=0)
    except ValueError:
        pass
    else:
        raise AssertionError("zero max_chars must fail")
