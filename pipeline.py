"""Create clean, resumable YouTube transcript exports for people and AI tools.

This file owns the real work: it finds videos, fetches captions, removes timing
noise, writes one record per video, and creates exact 500,000-character parts.
Exports are written to a caller-selected folder so raw transcripts stay out of
the source repository.
"""

from __future__ import annotations

import html
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import urlsplit

import requests
import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi

from yt_dlp_transcripts.core import detect_url_type, extract_video_id


MAX_CHARS = 500_000
VIDEO_URL = "https://www.youtube.com/watch?v={}"
YTDLP_CLIENTS = ("android_vr", "tv_embedded", "web_safari")
TIMING_LINE = re.compile(
    r"^\s*(?:\d{1,2}:)?\d{1,2}:\d{2}[,.]\d{3}\s+-->\s+"
    r"(?:\d{1,2}:)?\d{1,2}:\d{2}[,.]\d{3}.*$"
)
TAG = re.compile(r"<[^>]+>")
SPACE = re.compile(r"\s+")


@dataclass
class VideoRecord:
    """The small metadata record saved beside each cleaned transcript."""

    index: int
    video_id: str
    title: str
    url: str
    upload_date: str = ""
    duration: int | None = None
    channel: str = ""
    transcript_chars: int = 0
    transcript_source: str = ""
    status: str = "pending"
    error: str = ""


def clean_transcript(text: str) -> str:
    """Return readable text with VTT/SRT timing and markup removed."""

    lines: list[str] = []
    for raw_line in html.unescape(text or "").splitlines():
        line = raw_line.strip()
        if not line or line.upper() == "WEBVTT" or line.startswith("NOTE"):
            continue
        if TIMING_LINE.match(line) or re.fullmatch(r"\d+", line):
            continue
        line = TAG.sub(" ", line)
        line = SPACE.sub(" ", line).strip()
        if line and (not lines or line != lines[-1]):
            lines.append(line)
    return " ".join(lines).strip()


def split_text(text: str, max_chars: int = MAX_CHARS) -> list[str]:
    """Split text without ever creating a part longer than max_chars."""

    if max_chars < 1:
        raise ValueError("max_chars must be positive")
    text = text.strip()
    if not text:
        return []
    parts: list[str] = []
    while len(text) > max_chars:
        cut = text.rfind("\n", 0, max_chars + 1)
        if cut < max_chars // 2:
            cut = text.rfind(" ", 0, max_chars + 1)
        if cut < 1:
            cut = max_chars
        parts.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    if text:
        parts.append(text)
    assert all(len(part) <= max_chars for part in parts)
    return parts


def _caption_text(url: str, extension: str) -> str:
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    if extension == "json3":
        payload = response.json()
        return " ".join(
            segment.get("utf8", "")
            for event in payload.get("events", [])
            for segment in event.get("segs", [])
        )
    return response.text


def fetch_transcript(video_id: str, language: str = "en") -> tuple[str, str, str]:
    """Fetch manual/automatic captions with a yt-dlp fallback."""

    reason = "No transcript source returned text."
    try:
        fetched = YouTubeTranscriptApi().fetch(video_id, languages=(language,))
        text = clean_transcript(" ".join(snippet.text for snippet in fetched))
        if text:
            return text, "youtube-transcript-api", ""
    except Exception as error:
        reason = type(error).__name__

    for client in YTDLP_CLIENTS:
        options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "ignoreerrors": True,
            "socket_timeout": 10,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": [language, "en-US", "en-GB"],
            "extractor_args": {"youtube": {"player_client": [client]}},
        }
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(VIDEO_URL.format(video_id), download=False) or {}
        except Exception as error:
            reason = f"{client}: {type(error).__name__}"
            continue
        for catalog_name, source_name in (("subtitles", "manual"), ("automatic_captions", "automatic")):
            catalog = info.get(catalog_name, {})
            for lang in (language, "en-US", "en-GB", "en", "en-orig"):
                for caption in catalog.get(lang, []):
                    extension = caption.get("ext", "")
                    if extension not in {"json3", "vtt", "srv1", "srv2", "srv3"}:
                        continue
                    try:
                        text = clean_transcript(_caption_text(caption["url"], extension))
                    except Exception as error:
                        reason = f"{client}: {type(error).__name__}"
                        continue
                    if text:
                        return text, f"yt-dlp-{source_name}-{client}", ""
    return "", "", reason


def _video_entries(url: str) -> tuple[str, list[dict]]:
    """Resolve a link to a stable channel/playlist/video entry list."""

    kind = detect_url_type(url)
    if kind == "unknown":
        raise ValueError("Paste a YouTube video, playlist, or channel URL.")
    if kind == "video":
        video_id = extract_video_id(url)
        return kind, [{"id": video_id, "title": video_id or "Video", "webpage_url": url}]
    if kind == "channel_videos" and "/videos" not in urlsplit(url).path:
        parsed = urlsplit(url)
        url = parsed._replace(path=parsed.path.rstrip("/") + "/videos", query="").geturl()
    options = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
        "ignoreerrors": True,
    }
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False) or {}
    entries = [entry for entry in info.get("entries", []) if entry and entry.get("id")]
    return kind, entries


def _source_label(source_url: str) -> str:
    """Turn the source URL into a readable export name."""

    path = urlsplit(source_url).path.strip("/")
    label = path.split("/")[0].lstrip("@") or "YouTube source"
    label = re.sub(r"[-_]+", " ", label)
    if label.replace(" ", "").lower() == "team3dalpha":
        return "Team 3D Alpha"
    return label.title()


def _read_records(path: Path) -> dict[str, VideoRecord]:
    records: dict[str, VideoRecord] = {}
    if not path.exists():
        return records
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            payload = json.loads(line)
            records[payload["video_id"]] = VideoRecord(**payload)
    return records


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def build_notebook_parts(run_dir: Path, source_label: str, max_chars: int = MAX_CHARS) -> list[Path]:
    """Build NotebookLM-ready Markdown parts from all successful videos."""

    records = sorted(_read_records(run_dir / "records.jsonl").values(), key=lambda row: row.index)
    notebook_dir = run_dir / "notebooklm"
    notebook_dir.mkdir(exist_ok=True)
    for old_file in notebook_dir.glob("*.md"):
        old_file.unlink()
    parts: list[Path] = []
    current = ""

    def flush() -> None:
        nonlocal current
        if not current:
            return
        path = notebook_dir / f"YouTube - {source_label} - part {len(parts) + 1:04d}.md"
        path.write_text(current.rstrip() + "\n", encoding="utf-8")
        parts.append(path)
        current = ""

    for record in records:
        transcript_path = run_dir / "transcripts" / f"{record.video_id}.txt"
        if not transcript_path.exists() or record.status != "complete":
            continue
        transcript = transcript_path.read_text(encoding="utf-8").strip()
        header = (
            f"# {record.title}\n\n"
            f"Source: {record.url}\n"
            f"Video ID: {record.video_id}\n"
        )
        block_limit = max_chars - len(header) - 40
        blocks = split_text(transcript, max_chars=block_limit) or ["(No transcript text was returned.)"]
        for block_index, block in enumerate(blocks, 1):
            full_block = header + f"Video part: {block_index}/{len(blocks)}\n\n" + block + "\n\n"
            if current and len(current) + len(full_block) > max_chars:
                flush()
            current += full_block
    flush()
    return parts


def write_ai_prompt(run_dir: Path, source_url: str, source_label: str, parts: Iterable[Path]) -> Path:
    """Write a provider-neutral prompt for NotebookLM or another AI tool."""

    path = run_dir / f"AI prompt - YouTube - {source_label}.md"
    names = "\n".join(f"- {part.name}" for part in parts)
    path.write_text(
        f"# YouTube - {source_label}\n\n"
        "Use the attached transcript parts as the source of truth. Keep claims tied to the source video URL and say when a video has no transcript. Do not invent missing words.\n\n"
        f"Source channel: {source_url}\n\n"
        "Transcript parts:\n" + names + "\n\n"
        "Suggested first question: What are the main ideas across the channel, and which videos support each idea?\n",
        encoding="utf-8",
    )
    return path


def run_pipeline(
    source_url: str,
    run_dir: str | Path,
    language: str = "en",
    progress: Callable[[dict], None] | None = None,
) -> dict:
    """Run or resume one extraction job and return its verified summary."""

    root = Path(run_dir).resolve()
    transcript_dir = root / "transcripts"
    transcript_dir.mkdir(parents=True, exist_ok=True)
    records_path = root / "records.jsonl"
    state_path = root / "state.json"
    started = time.time()
    kind, entries = _video_entries(source_url)
    existing = _read_records(records_path)
    total = len(entries)
    state = {"status": "running", "source_url": source_url, "kind": kind, "total": total, "completed": 0}
    _write_json(state_path, state)

    def report(completed: int, title: str, status: str) -> None:
        state.update({"completed": completed, "current_title": title, "current_status": status})
        _write_json(state_path, state)
        if progress:
            progress(dict(state))

    pending = []
    completed = 0
    for index, entry in enumerate(entries, 1):
        video_id = entry["id"]
        title = entry.get("title") or video_id
        if video_id in existing and existing[video_id].status == "complete" and (transcript_dir / f"{video_id}.txt").exists():
            completed += 1
            continue
        pending.append((index, video_id, title))

    # ponytail: four workers; raise only after measuring rate limits on a real run.
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(fetch_transcript, video_id, language): (index, video_id, title)
            for index, video_id, title in pending
        }
        for future in as_completed(futures):
            index, video_id, title = futures[future]
            record = VideoRecord(index=index, video_id=video_id, title=title, url=VIDEO_URL.format(video_id))
            report(completed, title, "fetching")
            try:
                transcript, source, reason = future.result()
                if transcript:
                    (transcript_dir / f"{video_id}.txt").write_text(transcript, encoding="utf-8")
                    record.transcript_chars = len(transcript)
                    record.transcript_source = source
                    record.status = "complete"
                else:
                    record.status = "missing"
                    record.error = reason
            except Exception as error:
                record.status = "error"
                record.error = str(error)[:500]
            existing[video_id] = record
            records_path.write_text(
                "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in sorted((asdict(row) for row in existing.values()), key=lambda item: item["index"])),
                encoding="utf-8",
            )
            completed += 1
            report(completed, title, record.status)

    label = _source_label(source_url)
    parts = build_notebook_parts(root, label)
    prompt = write_ai_prompt(root, source_url, label, parts)
    complete = sum(row.status == "complete" for row in existing.values())
    missing = sum(row.status == "missing" for row in existing.values())
    errors = sum(row.status == "error" for row in existing.values())
    summary = {
        "status": "complete" if not missing and not errors else "partial",
        "source_url": source_url,
        "kind": kind,
        "videos": total,
        "transcripts": complete,
        "missing": missing,
        "errors": errors,
        "notebook_parts": len(parts),
        "max_part_chars": MAX_CHARS,
        "source_label": label,
        "ai_prompt": prompt.name,
        "elapsed_seconds": round(time.time() - started, 1),
    }
    _write_json(state_path, summary)
    if progress:
        progress(dict(summary))
    return summary
