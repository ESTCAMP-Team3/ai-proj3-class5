
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterator, Optional, Tuple
import os, time, re
import cv2
import numpy as np

JPEG_RE = re.compile(r"^(?P<idx>\d{6,})\.jpe?g$", re.IGNORECASE)

@dataclass
class FrameSpec:
    width: Optional[int] = None
    height: Optional[int] = None
    fps: float = 30.0

class JPEGFolderReader:
    """
    Incrementally reads 000001.jpeg, 000002.jpeg ... as they appear in a folder.
    Assumes sequential numbering without gaps (or waits until next shows up).
    Yields (frame_idx, wallclock_ms, frame_bgr).
    """
    def __init__(self, folder: str, spec: FrameSpec, poll_interval_sec: float = 0.02):
        self.folder = folder
        self.spec = spec
        self.poll = poll_interval_sec
        self._next_idx = 1
        self._start_ms = int(time.time() * 1000)

    def _read_frame(self, path: str):
        img = cv2.imread(path)
        if img is None:
            return None
        if self.spec.width and self.spec.height:
            img = cv2.resize(img, (self.spec.width, self.spec.height))
        return img

    def __iter__(self) -> Iterator[Tuple[int,int,np.ndarray]]:
        while True:
            fname = f"{self._next_idx:06d}.jpeg"
            alt = f"{self._next_idx:06d}.jpg"
            path = os.path.join(self.folder, fname)
            if not os.path.exists(path):
                path = os.path.join(self.folder, alt)
            if os.path.exists(path):
                frame = self._read_frame(path)
                if frame is not None:
                    now_ms = int(time.time() * 1000)
                    yield self._next_idx, now_ms, frame
                    self._next_idx += 1
                else:
                    # Corrupt or in-progress write; wait a bit and retry
                    time.sleep(self.poll)
            else:
                time.sleep(self.poll)
