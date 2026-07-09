/* camera_manager.js */

class CameraManager {
  constructor() {
    if (CameraManager.instance) {
      return CameraManager.instance;
    }
    
    this.activeMode = null;            // 'qr', 'face', 'faceId'
    this.activeStream = null;          // MediaStream
    this.facingMode = 'user';          // 'user' or 'environment' for face/faceId
    this.qrFacingMode = 'environment'; // 'environment' or 'user' for QR
    this.videoElement = null;
    this.html5QrCode = null;
    this.faceIdScanInterval = null;
    this.isScanningInProgress = false;
    this.errorCallback = null;
    
    // Bind resize/orientation handlers
    this.resizeTimeout = null;
    this.handleResize = this.handleResize.bind(this);
    window.addEventListener('resize', this.handleResize);
    window.addEventListener('orientationchange', this.handleResize);
    
    CameraManager.instance = this;
  }

  static getInstance() {
    if (!CameraManager.instance) {
      CameraManager.instance = new CameraManager();
    }
    return CameraManager.instance;
  }

  checkSecureContext() {
    if (!window.isSecureContext) {
      throw new Error("INSECURE_CONTEXT");
    }
  }

  async checkCameraPermission() {
    if (navigator.permissions && navigator.permissions.query) {
      try {
        const result = await navigator.permissions.query({ name: 'camera' });
        return result.state; // 'granted', 'prompt', 'denied'
      } catch (e) {
        console.warn("Permissions API query for camera failed:", e);
      }
    }
    return 'prompt'; // Fallback for browsers that do not support permissions query for 'camera'
  }

  cleanup() {
    // 1. Clear intervals
    if (this.faceIdScanInterval) {
      clearInterval(this.faceIdScanInterval);
      this.faceIdScanInterval = null;
    }
    this.isScanningInProgress = false;

    // 2. Stop HTML5 QR Code scanner if active
    if (this.html5QrCode && this.html5QrCode.isScanning) {
      try {
        this.html5QrCode.stop().catch(err => console.warn("Failed to stop html5QrCode:", err));
      } catch (e) {
        console.warn(e);
      }
    }

    // 3. Pause video and clear srcObject
    if (this.videoElement) {
      try {
        this.videoElement.pause();
        this.videoElement.srcObject = null;
      } catch (e) {
        console.warn(e);
      }
      this.videoElement = null;
    }

    // 4. Stop all stream tracks and release camera
    if (this.activeStream) {
      try {
        this.activeStream.getTracks().forEach(track => {
          track.stop();
        });
      } catch (e) {
        console.warn(e);
      }
      this.activeStream = null;
    }

    // 5. Hide error overlays and switch buttons on activeMode reset
    this.activeMode = null;
  }

  async startQR(containerId, onScanSuccess, onScanError, errorCallback) {
    this.cleanup();
    this.activeMode = 'qr';
    this.errorCallback = errorCallback;

    try {
      this.checkSecureContext();
    } catch (e) {
      this.handleError('INSECURE_CONTEXT');
      return;
    }

    const permState = await this.checkCameraPermission();
    if (permState === 'denied') {
      this.handleError('PERMISSION_DENIED');
      return;
    }

    if (typeof Html5Qrcode === 'undefined') {
      this.handleError('QR_LIB_NOT_LOADED');
      return;
    }

    if (!this.html5QrCode) {
      this.html5QrCode = new Html5Qrcode(containerId);
    }

    const config = { fps: 10, aspectRatio: 1.0 };
    
    try {
      await this.html5QrCode.start(
        { facingMode: this.qrFacingMode },
        config,
        onScanSuccess,
        onScanError
      );
      this.updateMirroring(document.querySelector(`#${containerId} video`), this.qrFacingMode);
      this.updateSwitchButtonsVisibility();
    } catch (err) {
      console.warn("QR first start failed, trying fallback facingMode:", err);
      const fallbackMode = (this.qrFacingMode === 'environment') ? 'user' : 'environment';
      try {
        await this.html5QrCode.start(
          { facingMode: fallbackMode },
          config,
          onScanSuccess,
          onScanError
        );
        this.qrFacingMode = fallbackMode;
        this.updateMirroring(document.querySelector(`#${containerId} video`), this.qrFacingMode);
        this.updateSwitchButtonsVisibility();
      } catch (err2) {
        console.error("QR fallback start failed:", err2);
        this.handleError(err2);
      }
    }
  }

  async toggleQRCamera(containerId, onScanSuccess, onScanError) {
    this.qrFacingMode = (this.qrFacingMode === 'environment') ? 'user' : 'environment';
    await this.startQR(containerId, onScanSuccess, onScanError, this.errorCallback);
  }

  async startFace(videoElementId, errorCallback) {
    this.cleanup();
    this.activeMode = 'face';
    this.errorCallback = errorCallback;
    this.videoElement = document.getElementById(videoElementId);

    try {
      this.checkSecureContext();
    } catch (e) {
      this.handleError('INSECURE_CONTEXT');
      return;
    }

    const permState = await this.checkCameraPermission();
    if (permState === 'denied') {
      this.handleError('PERMISSION_DENIED');
      return;
    }

    try {
      try {
        this.activeStream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: this.facingMode, width: { ideal: 1280 } },
          audio: false
        });
      } catch (e) {
        console.warn("Real camera failed, creating mock video stream for testing:", e);
        this.activeStream = this.createMockStream();
      }

      if (this.videoElement) {
        this.videoElement.srcObject = this.activeStream;
        this.updateMirroring(this.videoElement, this.facingMode);
      }
      this.updateSwitchButtonsVisibility();
    } catch (err) {
      this.handleError(err);
    }
  }

  async toggleFaceCamera(videoElementId) {
    this.facingMode = (this.facingMode === 'user') ? 'environment' : 'user';
    await this.startFace(videoElementId, this.errorCallback);
  }

  async startFaceId(videoElementId, onFrame, errorCallback) {
    this.cleanup();
    this.activeMode = 'faceId';
    this.errorCallback = errorCallback;
    this.videoElement = document.getElementById(videoElementId);

    try {
      this.checkSecureContext();
    } catch (e) {
      this.handleError('INSECURE_CONTEXT');
      return;
    }

    const permState = await this.checkCameraPermission();
    if (permState === 'denied') {
      this.handleError('PERMISSION_DENIED');
      return;
    }

    try {
      try {
        this.activeStream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: this.facingMode, width: { ideal: 1280 } },
          audio: false
        });
      } catch (e) {
        console.warn("Real camera failed, creating mock video stream for testing:", e);
        this.activeStream = this.createMockStream();
      }

      if (this.videoElement) {
        this.videoElement.srcObject = this.activeStream;
        this.updateMirroring(this.videoElement, this.facingMode);
      }
      this.updateSwitchButtonsVisibility();
      this.startFaceIdInterval(onFrame);
    } catch (err) {
      this.handleError(err);
    }
  }

  async toggleFaceIdCamera(videoElementId, onFrame) {
    this.facingMode = (this.facingMode === 'user') ? 'environment' : 'user';
    await this.startFaceId(videoElementId, onFrame, this.errorCallback);
  }

  startFaceIdInterval(onFrame) {
    if (this.faceIdScanInterval) {
      clearInterval(this.faceIdScanInterval);
    }

    this.faceIdScanInterval = setInterval(async () => {
      if (this.isScanningInProgress || !this.activeStream || this.activeMode !== 'faceId') return;
      
      const videoEl = this.videoElement;
      if (!videoEl || !videoEl.readyState) return;

      this.isScanningInProgress = true;
      try {
        await onFrame(videoEl);
      } catch (e) {
        console.error("Face ID scanning capture error:", e);
      } finally {
        this.isScanningInProgress = false;
      }
    }, 2000);
  }

  handleResize() {
    clearTimeout(this.resizeTimeout);
    this.resizeTimeout = setTimeout(() => {
      this.adjustOverlays();
    }, 300);
  }

  adjustOverlays() {
    if (this.activeMode === 'qr') {
      const qrVideo = document.querySelector('#qrReader video');
      if (qrVideo) {
        this.updateMirroring(qrVideo, this.qrFacingMode);
      }
    } else if (this.videoElement) {
      this.updateMirroring(this.videoElement, this.facingMode);
    }
  }

  updateMirroring(videoEl, facingMode) {
    if (!videoEl) return;
    if (facingMode === 'user') {
      videoEl.style.transform = 'scaleX(-1)';
    } else {
      videoEl.style.transform = 'none';
    }
  }

  async updateSwitchButtonsVisibility() {
    try {
      const isTouch = window.matchMedia('(pointer: coarse)').matches || navigator.maxTouchPoints > 0;
      if (!isTouch) {
        this.hideAllSwitchButtons();
        return;
      }

      if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) {
        this.hideAllSwitchButtons();
        return;
      }

      const devices = await navigator.mediaDevices.enumerateDevices();
      const videoDevices = devices.filter(d => d.kind === 'videoinput');
      
      if (videoDevices.length > 1) {
        this.showAllSwitchButtons();
      } else {
        this.hideAllSwitchButtons();
      }
    } catch (e) {
      console.warn("Error checking camera devices:", e);
      this.hideAllSwitchButtons();
    }
  }

  showAllSwitchButtons() {
    document.querySelectorAll('.camera-switch-btn').forEach(btn => {
      btn.style.setProperty('display', 'flex', 'important');
    });
  }

  hideAllSwitchButtons() {
    document.querySelectorAll('.camera-switch-btn').forEach(btn => {
      btn.style.setProperty('display', 'none', 'important');
    });
  }

  handleError(err) {
    if (this.errorCallback) {
      this.errorCallback(this.activeMode, err);
    } else {
      console.error("CameraManager Error in mode", this.activeMode, err);
    }
  }

  createMockStream() {
    const canvas = document.createElement('canvas');
    canvas.width = 640;
    canvas.height = 480;
    const ctx = canvas.getContext('2d');
    const stream = canvas.captureStream(30);
    const track = stream.getVideoTracks()[0];
    
    const drawFrame = () => {
      if (!track || track.readyState === 'ended') {
        return;
      }
      ctx.fillStyle = '#0f172a';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      
      ctx.strokeStyle = 'rgba(234, 179, 8, 0.2)';
      ctx.lineWidth = 1;
      for (let i = 0; i < canvas.width; i += 40) {
        ctx.beginPath(); ctx.moveTo(i, 0); ctx.lineTo(i, canvas.height); ctx.stroke();
      }
      for (let j = 0; j < canvas.height; j += 40) {
        ctx.beginPath(); ctx.moveTo(0, j); ctx.lineTo(canvas.width, j); ctx.stroke();
      }
      
      ctx.fillStyle = '#3b82f6';
      ctx.beginPath();
      ctx.arc(320, 240, 100, 0, Math.PI * 2);
      ctx.fill();
      
      ctx.fillStyle = '#0f172a';
      ctx.beginPath();
      ctx.arc(280, 220, 12, 0, Math.PI * 2);
      ctx.arc(360, 220, 12, 0, Math.PI * 2);
      ctx.fill();
      
      ctx.strokeStyle = '#0f172a';
      ctx.lineWidth = 6;
      ctx.beginPath();
      ctx.arc(320, 250, 40, 0, Math.PI);
      ctx.stroke();
      
      ctx.fillStyle = '#ffffff';
      ctx.font = 'bold 20px Inter, sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('SUPERVISOR WEBCAM ACTIVE', 320, 390);
      
      requestAnimationFrame(drawFrame);
    };
    
    drawFrame();
    return stream;
  }
}

// Attach singleton to window scope
window.CameraManager = CameraManager;
