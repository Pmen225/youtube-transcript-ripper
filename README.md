# YouTube Transcript Studio

YouTube Transcript Studio is a small local app for turning a YouTube video, playlist, or channel link into clean transcript files. It keeps the raw export on your computer, removes caption timing noise, makes exact 500,000-character Markdown parts, and creates an AI prompt for NotebookLM or another AI tool.

The transcript engine is reused from the MIT-licensed [`LinuxIsCool/yt-dlp-transcripts`](https://github.com/LinuxIsCool/yt-dlp-transcripts) project. The additions here are the local frontend, resumable run state, cleaning, chunking, and AI-ready export bundle.

## Run it

```powershell
python -m pip install -e .
python app.py
```

Open `http://127.0.0.1:8080`, paste a YouTube link, and start the run. The app recognises a single video, playlist, or channel URL. Completed exports are stored in the ignored `exports/` folder.

## Export layout

Each run contains one cleaned text file per video, `records.jsonl`, `state.json`, an `AI prompt - YouTube - <channel>.md` file, and `notebooklm/YouTube - <channel> - part NNNN.md` files. Every NotebookLM part is at most 500,000 characters.

## Safety and limits

- Do not commit transcript exports, cookies, credentials, or API keys.
- A video without accessible captions is recorded as `missing`; it is not silently treated as complete.
- A run with any missing or failed videos is reported as `partial`; the record keeps the failure reason so it can be retried later.
- YouTube can rate-limit large channel runs. The run is resumable, so rerun the same source folder after the limit clears.

## Checks

```powershell
python -m pytest -q
```

The tests cover timestamp removal, duplicate caption-line removal, and the hard chunk-size ceiling.
