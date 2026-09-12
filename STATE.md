# Current project state

This file records the current YouTube Transcript Studio build and the next authorised action in plain English.

- Objective: provide a simple local frontend for video, playlist, and channel transcript extraction.
- Reused base: `LinuxIsCool/yt-dlp-transcripts`, MIT licensed.
- Verified source: Team 3D Alpha channel inventory returned 1,755 video IDs on 12 September 2026.
- Current code state: the resumable pipeline and frontend are being added.
- Export rule: raw transcripts belong in a local run folder, never in the Git repository.
- Next action: run focused tests, start the local app, then process the Team 3D Alpha URL.
