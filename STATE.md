# Current project state

This file records the current YouTube Transcript Studio build and the next authorised action in plain English.

- Objective: provide a simple local frontend for video, playlist, and channel transcript extraction.
- Reused base: `LinuxIsCool/yt-dlp-transcripts`, MIT licensed.
- Verified source: Team 3D Alpha channel inventory returned 1,755 video IDs on 12 September 2026.
- Current code state: the resumable pipeline and frontend are published; the test suite passes 26 tests.
- Export rule: raw transcripts belong in a local run folder, never in the Git repository.
- Verified run: 27 clean transcript files were recovered; 1,728 records remain marked missing after YouTube blocked caption requests. Two notebook parts are under the 500,000-character ceiling.
- Next action: retry the missing records only after YouTube permits caption requests or an authorised alternate route is supplied.
