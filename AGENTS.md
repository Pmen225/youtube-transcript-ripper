# Project guide

This file explains how to work on the YouTube Transcript Studio project. The project is a local tool that turns a YouTube video, playlist, or channel link into cleaned transcript files and AI-ready 500,000-character parts.

## Rules

- Keep transcript exports, cookies, API keys, and user data outside Git.
- Use the existing `yt_dlp_transcripts` package for URL detection and extraction helpers when they fit.
- Keep the web app dependency-free beyond the existing project dependencies.
- Run the focused tests and a local health check after code changes.
- Do not claim a NotebookLM or Notion upload until the destination reports the file or page was created.

## Main files

- `app.py`: small local web app and frontend.
- `pipeline.py`: resumable extraction, cleaning, chunking, and AI bundle creation.
- `yt_dlp_transcripts/`: the MIT-licensed upstream extraction core used by the project.
- `tests/test_pipeline.py`: fast checks for the safety-critical text rules.
- `STATE.md`: current run state and next action.
