
class FrameUploader {
  constructor({ endpoint = "/api/upload_frame", fps = 24, quality = 0.85 } = {}){
    this.endpoint = endpoint; this.fps = fps; this.quality = quality;
    this.stream = null; this.videoEl = null; this.canvas = null; this.ctx = null;
    this.running = false; this.paused = false; this.seq = 0; this.streamId = null; this.previewCanvas = null;
  }
  async init(videoEl){
    this.videoEl = videoEl;
    this.stream = await navigator.mediaDevices.getUserMedia({ video: { width:{ideal:640, max:640}, height:{ideal:480, max:480}, frameRate:{ideal:24, max:24} }, audio:false });
    this.videoEl.srcObject = this.stream; await this.videoEl.play();
    const vw = this.videoEl.videoWidth || 640, vh = this.videoEl.videoHeight || 480;
    this.canvas = document.createElement('canvas'); this.canvas.width = vw; this.canvas.height = vh; this.ctx = this.canvas.getContext('2d');
  }
  attachPreviewCanvas(canvas){ this.previewCanvas = canvas || null; }
  setFps(fps){ this.fps = Math.max(1, Math.min(30, Number(fps)||24)); }
  setQuality(q){ this.quality = Math.max(0.1, Math.min(1.0, Number(q)||0.85)); }
  async start(){
    if (!this.stream) await this.init(this.videoEl || document.createElement('video'));
    if (this.running) return;
    this.running = true; this.paused = false; this.seq = 0; this.streamId = crypto.randomUUID();
    const frameInterval = 1000 / this.fps; let last = 0;
    const loop = async (now) => {
      if (!this.running) return; requestAnimationFrame(loop);
      if (this.paused) return; if (now - last < frameInterval) return; last = now;
      const vw = this.videoEl.videoWidth || 640, vh = this.videoEl.videoHeight || 480;
      if (this.canvas.width!==vw||this.canvas.height!==vh){ this.canvas.width=vw; this.canvas.height=vh; this.ctx=this.canvas.getContext('2d'); }
      this.ctx.drawImage(this.videoEl, 0, 0, vw, vh);
      if (this.previewCanvas){ const pc=this.previewCanvas; if (pc.width!==vw||pc.height!==vh){ pc.width=vw; pc.height=vh; } pc.getContext('2d').drawImage(this.videoEl,0,0,vw,vh); }
      this.canvas.toBlob(async (blob)=>{
        if (!blob) return;
        try {
          await fetch(this.endpoint, { method:'POST', headers:{ 'Content-Type':'image/jpeg', 'X-Stream-ID': this.streamId, 'X-Seq': String(this.seq++), 'X-Frame-TS': String(Date.now()) }, body: blob, keepalive: true });
        } catch(e){ console.warn('upload error', e); }
      }, 'image/jpeg', this.quality);
    };
    requestAnimationFrame(loop);
  }
  pause(){ this.paused = true; }
  resume(){ this.paused = false; }
  stop(){ this.running = false; this.paused = false; this.streamId = null; if (this.stream){ this.stream.getTracks().forEach(t=>t.stop()); this.stream=null; } }
}
window.DrownyUploader = new FrameUploader();
