
# Drowny-SVR (Merged)

This is a merged project of **drowny-app** and **Camera-Stream-jpeg**.

## What changed
- Added `app/stream_upload.py` (Blueprint) providing:
  - `GET /stream` : camera streaming setup page
  - `POST /api/upload_frame` : receive JPEG frames (headers: `X-Stream-ID`, `X-Seq`)
  - `GET /stream/healthz` : health endpoint
- Added `templates/stream.html` that shows the camera preview and a **서비스 시작** button.
- Added `static/js/uploader.js` implementing a persistent JPEG uploader (24fps @ 640x480 by default).
- A background worker copies received frames to `app/uploads/outbox/<stream>/` (PROCESSING_MODE=outbox).

## Folder
```
/mnt/data/drowny-svr-merged
```
- `app/` : original drowny app + new streaming blueprint
- `run.py` : entrypoint that imports existing app and registers blueprint

## Run (pyenv/venv)
```bash
cd /mnt/data/drowny-svr-merged
python3 -m venv .venv && source .venv/bin/activate
pip install -r app/requirements.txt || pip install Flask flask-socketio flask-sock python-dotenv
python run.py
```

## Login → Stream → Drowny
1. Login using your existing `/login` page.
2. Open **/stream** (you can add a nav link or post-login redirect to `/stream` in your app).
3. Click **서비스 시작** to begin JPEG upload; the uploader keeps running while you navigate to `/drowny_service`.
   - You can add start/pause/resume/stop controls to the Drowny page by calling:  
     `window.DrownyUploader.start() / pause() / resume() / stop()`

## Storage
- Frames saved under `app/uploads/inbox/<user>-<stream_id>/<seq>.jpg`
- Mirrored to `app/uploads/outbox/...` for downstream processing.

## Notes
- If your app uses a different session key than `session['user']`, update `stream_upload.py` accordingly.
- To redirect to `/stream` after login, adjust your login handler in `app/app.py` to `return redirect("/stream")`.
