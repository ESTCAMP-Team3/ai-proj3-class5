
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List
import uvicorn

from .models import StartStreamRequest, StopStreamRequest, StreamStatus, LastRecord
from .manager import StreamManager

app = FastAPI(title="JPEG Stream Mediapipe Analyzer", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

mgr = StreamManager()

@app.get("/healthz")
def healthz():
    return {"ok": True}

@app.post("/streams/start", response_model=dict)
def start_stream(req: StartStreamRequest):
    try:
        topic = mgr.start(req)
        return {"started": True, "topic": topic}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/streams/stop", response_model=dict)
def stop_stream(req: StopStreamRequest):
    ok = mgr.stop(req.topic)
    if not ok:
        raise HTTPException(status_code=404, detail=f"No such topic {req.topic}")
    return {"stopped": True, "topic": req.topic}

@app.get("/streams", response_model=List[StreamStatus])
def list_streams():
    return mgr.status_all()

@app.get("/streams/{topic}/last", response_model=LastRecord)
def get_last(topic: str):
    rec = mgr.last_record(topic)
    if rec is None:
        raise HTTPException(status_code=404, detail="No last record")
    return {"topic": topic, "last": rec}

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8002, reload=False)
