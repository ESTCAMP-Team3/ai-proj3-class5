# Drowsy Guard - Prototype (Flask + SocketIO)
## What this package contains
- `run.py`: Flask + SocketIO server. Endpoints: `/` (UI), `/ingest` (POST D values), `/chat_send` (POST chat messages saved to MongoDB/local file)
- `d_writer.py`: simple client that posts D values from 30 to 100 (1 per second) to `/ingest`
- `templates/index.html`, `static/`: frontend smartphone-style UI. Bottom 1/3 transparent chat overlay. TTS uses Web Speech API.
- `requirements.txt`
- `README.md`
- `notebooks/`: 9 ipynb files (one per stage) for easy editing of UI styles and content.

## How to run locally (quick)
1. Create Python env and install requirements:
   ```bash
   python -m venv venv
   source venv/bin/activate   # or venv\Scripts\activate on Windows
   pip install -r requirements.txt
   ```
2. (Optional) Provide a MongoDB URI in environment variable `MONGO_URI`. If not provided or pymongo not available, chats are saved to `chats_local.json`.
   You can also set `SERVER_URL` before running d_writer.py if server is on a different host.
3. Start server:
   ```bash
   python run.py
   ```
4. In a separate terminal, start the D-score writer:
   ```bash
   python d_writer.py
   ```
5. Open browser at `http://127.0.0.1:5000/` to view the smartphone UI.
6. To enable full LLM-based replies: implement `OPENAI_API_KEY` usage in `run.py`'s `/chat_send` to call OpenAI and return responses. Currently the server returns a simple echoed assistant reply and saves messages to DB/local file.

## Notes & how the UI follows your requirements
- Smartphone ratio and large stage label (occupies ~80% width) implemented in CSS.
- Bottom 1/3 transparent chat overlay implemented and records messages to MongoDB (or local file fallback).
- D-score injections via `/ingest` will update UI in real-time via SocketIO.
- '주의' and escalation stages show centered highlighted messages and trigger TTS.
- L1/L2/L3/FAILSAFE include a flashing background effect and progressively louder TTS (simulated by increasing volume parameter).
- `notebooks/` includes editable ipynb files per-stage for designers to tweak colors/text. See `notebooks/README.md` for how to open them.

## LLM / 프롬프트 지침 (요약)
LLM은 시스템 프롬프트 파일(`prompt_guidelines.md`)을 사용해 일관된 음성/응답 정책을 따릅니다.
- 음성 톤: 한국어, 30대 여성 톤(브라우저 TTS 우선, 서버 TTS는 선택).
- 응답 포맷: 상태전이 메시지는 간단 문장(<=30자), 검증 요청은 질문 형태로 제공.
- 검증 응답: LLM에게 정답 여부 판단을 요청하고, `{"correct": true/false, "explain":"..."}` 형식의 JSON을 기대합니다.
자세한 지침은 `prompt_guidelines.md`를 확인하세요.
