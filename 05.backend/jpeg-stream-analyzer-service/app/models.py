
from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any, List, Literal

class KafkaConfig(BaseModel):
    bootstrap_servers: str = Field(..., description="e.g., kafka.dongango.com:9094 or host:9092")
    security_protocol: str = Field("PLAINTEXT", description="PLAINTEXT|SASL_PLAINTEXT|SASL_SSL|SSL")
    sasl_mechanism: Optional[str] = Field(None, description="SCRAM-SHA-256|SCRAM-SHA-512|PLAIN")
    sasl_username: Optional[str] = None
    sasl_password: Optional[str] = None
    client_id: Optional[str] = "jpeg-mp-service"

    @validator("security_protocol")
    def _upper(cls, v): return v.upper()
    
    @validator("sasl_mechanism")
    def _upper_mech(cls, v): return v.upper() if v else v

class StartStreamRequest(BaseModel):
    jpeg_dir: str = Field(..., description="Folder path containing sequential JPEG files like 000001.jpeg, 000002.jpeg...")
    kafka: KafkaConfig
    topic: str
    fps: float = Field(30.0, description="Frames per second: 24.0 or 30.0 etc.")
    width: Optional[int] = Field(None, description="Resize width. If omitted, keep original.")
    height: Optional[int] = Field(None, description="Resize height. If omitted, keep original.")
    resume: bool = Field(True, description="If True, continue frame index from last saved state for this topic.")
    process_mode: Literal["thread"] = "thread"

class StopStreamRequest(BaseModel):
    topic: str

class StreamStatus(BaseModel):
    topic: str
    jpeg_dir: str
    fps: float
    width: Optional[int]
    height: Optional[int]
    alive: bool
    frames_emitted: int
    last_frame_idx: int
    last_ts_ms: Optional[int]
    started_at_ms: int

class LastRecord(BaseModel):
    topic: str
    last: Dict[str, Any]
