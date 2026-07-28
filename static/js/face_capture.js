/**
 * AKHU AFIVS — Face Capture JavaScript (Fully Automated & Voice-Guided)
 */

// Force disable any speech synthesis globally to ensure absolute silence
if ('speechSynthesis' in window) {
  window.speechSynthesis.speak = function() {};
  window.speechSynthesis.cancel = function() {};
}

const video = document.getElementById('cameraVideo');
const canvas = document.getElementById('captureCanvas');
const statusEl = document.getElementById('cameraStatus');
const statusText = document.getElementById('statusText');
const faceGuide = document.getElementById('faceGuide');
const capturedPreview = document.getElementById('capturedPreview');
const capturedPreviewWrapper = document.getElementById('capturedPreviewWrapper');
const captureSuccess = document.getElementById('captureSuccess');

let stream = null;
let faceCheckInterval = null;
let stabilityCounter = 0;
let isSaving = false;
const CSRF = document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';

// Local shape detection API fallback
let localDetector = null;
if ('FaceDetector' in window) {
  localDetector = new FaceDetector({ fastMode: true, maxDetectedFaces: 1 });
}

// Speech synthesis helpers
let lastSpokenText = '';
let lastSpokenTime = 0;

function speak(text) {
  return; // Disabled per user request
  if (text === lastSpokenText && Date.now() - lastSpokenTime < 5000) {
    return; // Debounce 5s for the same voice prompt
  }
  if ('speechSynthesis' in window) {
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    const lang = document.documentElement.lang || 'uz';
    utterance.lang = lang === 'uz' ? 'uz-UZ' : 'en-US';
    
    // Attempt to find a native voice
    const voices = window.speechSynthesis.getVoices();
    const targetVoice = voices.find(v => v.lang.startsWith(lang));
    if (targetVoice) {
      utterance.voice = targetVoice;
    }
    
    lastSpokenText = text;
    lastSpokenTime = Date.now();
    window.speechSynthesis.speak(utterance);
  }
}

// Ensure speech synthesis voices are loaded early
if ('speechSynthesis' in window) {
  window.speechSynthesis.getVoices();
}

async function initCamera() {
  try {
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: {
          width: { ideal: 1280 },
          height: { ideal: 720 },
          facingMode: 'user',
        },
        audio: false,
      });
    } catch (e) {
      console.warn("Real camera failed, creating mock video stream for testing:", e);
      stream = createMockVideoStream();
    }
    video.srcObject = stream;
    
    // Apply continuous autofocus & exposure constraints if supported
    try {
      const track = stream.getVideoTracks()[0];
      if (track && track.getCapabilities) {
        const capabilities = track.getCapabilities();
        const advancedConstraints = {};
        if (capabilities.focusMode && capabilities.focusMode.includes('continuous')) {
          advancedConstraints.focusMode = 'continuous';
        }
        if (capabilities.exposureMode && capabilities.exposureMode.includes('continuous')) {
          advancedConstraints.exposureMode = 'continuous';
        }
        if (capabilities.whiteBalanceMode && capabilities.whiteBalanceMode.includes('continuous')) {
          advancedConstraints.whiteBalanceMode = 'continuous';
        }
        if (Object.keys(advancedConstraints).length > 0) {
          await track.applyConstraints({ advanced: [advancedConstraints] });
          console.log("Applied autofocus/exposure:", advancedConstraints);
        }
      }
    } catch (err) {
      console.warn("Could not apply autofocus/exposure:", err);
    }

    video.onloadedmetadata = () => {
      const lang = (document.documentElement.lang || 'uz').toLowerCase().startsWith('uz') ? 'uz' : 'en';
      setStatus('active', lang === 'uz' ? '🟢 Kamera tayyor. Doira ichiga qarang.' : '🟢 Camera Ready — Center your face.');
      speak(lang === 'uz' ? 'Kameraga to\'g\'ri qarang va ko\'zlaringizni oching' : 'Please look straight at the camera and open your eyes');
      startFaceDetection();
    };
  } catch (err) {
    console.error('Camera error:', err);
    setStatus('error', '❌ Camera access denied.');
  }
}

function createMockVideoStream() {
  const canvas = document.createElement('canvas');
  canvas.width = 640;
  canvas.height = 480;
  const ctx = canvas.getContext('2d');
  
  function drawFrame() {
    ctx.fillStyle = '#0f172a';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    
    ctx.strokeStyle = 'rgba(37, 99, 235, 0.2)';
    ctx.lineWidth = 1;
    for (let i = 0; i < canvas.width; i += 40) {
      ctx.beginPath(); ctx.moveTo(i, 0); ctx.lineTo(i, canvas.height); ctx.stroke();
    }
    for (let j = 0; j < canvas.height; j += 40) {
      ctx.beginPath(); ctx.moveTo(0, j); ctx.lineTo(canvas.width, j); ctx.stroke();
    }
    
    ctx.fillStyle = '#f59e0b';
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
    ctx.fillText('MOCK WEBCAM ACTIVE', 320, 390);
    
    requestAnimationFrame(drawFrame);
  }
  
  drawFrame();
  return canvas.captureStream(30);
}

function setStatus(type, text) {
  statusEl.className = `camera-status ${type}`;
  statusText.textContent = text;
  const overlayText = document.getElementById('cameraInstructionText');
  if (overlayText) {
    overlayText.textContent = text;
  }
}

function startFaceDetection() {
  stabilityCounter = 0;
  isSaving = false;
  if (faceCheckInterval) clearInterval(faceCheckInterval);
  faceCheckInterval = setInterval(checkFaceInFrame, 1000);
}

async function checkFaceInFrame() {
  if (!stream || isSaving) return;
  
  // Fast client-side face check if native FaceDetector is supported
  if (localDetector) {
    const lang = (document.documentElement.lang || 'uz').toLowerCase().startsWith('uz') ? 'uz' : 'en';
    try {
      const faces = await localDetector.detect(video);
      if (faces.length === 0) {
        faceGuide.classList.remove('active');
        setStatus('active', lang === 'uz' ? '👤 Kameraga qarang.' : '👤 Please look at the camera.');
        stabilityCounter = 0;
        return;
      }
      
      const face = faces[0];
      const box = face.boundingBox;
      const videoWidth = video.videoWidth || 640;
      const videoHeight = video.videoHeight || 480;
      const faceCenterX = box.x + box.width / 2;
      const faceCenterY = box.y + box.height / 2;
      
      const devX = Math.abs(faceCenterX - videoWidth / 2) / videoWidth;
      const devY = Math.abs(faceCenterY - videoHeight / 2) / videoHeight;
      
      if (devX > 0.22 || devY > 0.22) {
        faceGuide.classList.remove('active');
        setStatus('active', lang === 'uz' ? '⚠️ Yuzingizni doira ichiga joylashtiring.' : '⚠️ Center your face in the oval.');
        stabilityCounter = 0;
        return;
      }
    } catch (e) {
      console.warn("Local FaceDetector failed, falling back to server:", e);
    }
  }

  try {
    const frameData = captureFrame(240, 0.25);
    const resp = await fetch('/api/verification/detect-face/', {

      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF },
      body: JSON.stringify({ frame: frameData }),
    });

    if (!resp.ok) {
      console.warn("detect-face HTTP status:", resp.status);
      return;
    }

    const result = await resp.json();
    const lang = (document.documentElement.lang || 'uz').toLowerCase().startsWith('uz') ? 'uz' : 'en';

    if (!result.face_detected) {
      faceGuide.classList.remove('active');
      setStatus('active', lang === 'uz' ? '👤 Kameraga qarang.' : '👤 Please look at the camera.');
      speak(lang === 'uz' ? 'Kameraga qarang' : 'Please look at the camera');
      stabilityCounter = 0;
      return;
    }

    if (!result.lighting_ok) {
      faceGuide.classList.remove('active');
      const brightness = result.brightness || 0;
      if (brightness < 45) {
        setStatus('active', lang === 'uz' ? '⚠️ Yorug\'lik yetarli emas.' : '⚠️ Low light detected.');
        speak(lang === 'uz' ? 'Yorug\'lik yetarli emas' : 'Low light detected');
      } else {
        setStatus('active', lang === 'uz' ? '⚠️ Yorug\'lik juda kuchli.' : '⚠️ Too much light.');
        speak(lang === 'uz' ? 'Yorug\'lik juda kuchli' : 'Too much light');
      }
      stabilityCounter = 0;
      return;
    }

    if (!result.face_centered) {
      faceGuide.classList.remove('active');
      setStatus('active', lang === 'uz' ? '⚠️ Yuzingizni doira ichiga joylashtiring.' : '⚠️ Center your face in the oval.');
      speak(lang === 'uz' ? 'Yuzingizni doira ichiga joylashtiring' : 'Center your face in the oval');
      stabilityCounter = 0;
      return;
    }

    if (!result.eyes_open) {
      faceGuide.classList.remove('active');
      setStatus('active', lang === 'uz' ? '👁️ Ko\'zlaringizni oching.' : '👁️ Please open your eyes.');
      speak(lang === 'uz' ? 'Ko\'zlaringizni oching' : 'Please open your eyes');
      stabilityCounter = 0;
      return;
    }

    // All conditions met
    faceGuide.classList.add('active');
    stabilityCounter++;
    const remaining = 2 - stabilityCounter;
    
    if (remaining > 0) {
      setStatus('active', lang === 'uz' ? `🟢 Yuz holati mos. Qimirlamang...` : `🟢 Face position OK. Hold still...`);
        setStatus('active', lang === 'uz' ? '⏳ Rasmga olinmoqda...' : '⏳ Capturing...');
      speak(lang === 'uz' ? 'Rasmga olinmoqda' : 'Capturing photo');
      isSaving = true;
      clearInterval(faceCheckInterval);
      const selfiePhoto = captureFrame(640, 0.70);
      await triggerSelfieSave(selfiePhoto);
    }
  } catch (e) {
    console.error("Face check loop error:", e);
  }
}

function captureFrame(maxDim = 240, quality = 0.25) {
  const origW = video.videoWidth || 640;
  const origH = video.videoHeight || 480;

  let targetW = origW;
  let targetH = origH;

  if (maxDim && (origW > maxDim || origH > maxDim)) {
    if (origW > origH) {
      targetW = maxDim;
      targetH = Math.round((origH * maxDim) / origW);
    } else {
      targetH = maxDim;
      targetW = Math.round((origW * maxDim) / origH);
    }
  }

  canvas.width = targetW;
  canvas.height = targetH;
  const ctx = canvas.getContext('2d');
  ctx.scale(-1, 1);
  ctx.drawImage(video, -targetW, 0, targetW, targetH);
  ctx.setTransform(1, 0, 0, 1, 0, 0);

  let dataUrl = canvas.toDataURL('image/jpeg', quality);

  // Hard safety limit for ALL requests (detection and selfie save):
  // Keep payload under 11,000 chars (~11KB) to prevent Nginx proxy 500 error on external proxy
  if (dataUrl.length > 11000) {
    canvas.width = 400;
    canvas.height = Math.round((origH * 400) / origW);
    const ctx2 = canvas.getContext('2d');
    ctx2.scale(-1, 1);
    ctx2.drawImage(video, -canvas.width, 0, canvas.width, canvas.height);
    ctx2.setTransform(1, 0, 0, 1, 0, 0);
    dataUrl = canvas.toDataURL('image/jpeg', 0.40);
  }

  return dataUrl;
}

async function triggerSelfieSave(imageData) {
  const lang = (document.documentElement.lang || 'uz').toLowerCase();
  try {
    const resp = await fetch('/api/verification/save-selfie/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF },
      body: JSON.stringify({ image: imageData }),
    });

    if (!resp.ok && resp.status !== 422) {
      console.warn("Save selfie HTTP status:", resp.status);
      setStatus('error', lang.startsWith('uz') ? '❌ Qayta urinib ko\'ring' : '❌ Please try again');
      isSaving = false;
      setTimeout(() => { startFaceDetection(); }, 2000);
      return;
    }

    const result = await resp.json();

    if (result.success) {
      if (capturedPreview) {
        capturedPreview.src = imageData;
      }
      if (capturedPreviewWrapper) {
        capturedPreviewWrapper.style.display = 'block';
      }
      if (captureSuccess) {
        captureSuccess.classList.remove('d-none');
      }

      setStatus('captured', lang.startsWith('uz') ? '📸 Rasm saqlandi!' : '📸 Photo saved!');
      speak(lang.startsWith('uz') ? 'Rasm muvaffaqiyatli saqlandi' : 'Photo saved successfully');

      setTimeout(() => {
        if (stream) {
          stream.getTracks().forEach(t => t.stop());
        }
        window.location.href = '/step/3/';
      }, 1500);
    } else {
      let rawErr = result.error || '';
      let displayErr = rawErr;
      if (lang.startsWith('uz')) {
        if (rawErr.includes('closer') || rawErr.includes('size') || rawErr.includes('ratio')) {
          displayErr = "Kameraga yaqinroq turing";
        } else if (rawErr.includes('blurry') || rawErr.includes('blur')) {
          displayErr = "Rasm xira. Qimirlamay turing";
        } else if (rawErr.includes('one face') || rawErr.includes('Multiple faces')) {
          displayErr = "Kamerada faqat bir kishi bo'lsin";
        } else if (rawErr.includes('Spoof') || rawErr.includes('live')) {
          displayErr = "Kameraga jonli yuzingiz bilan qarang";
        } else if (rawErr.includes('dark')) {
          displayErr = "Yorug'lik yetarli emas";
        } else if (rawErr.includes('bright')) {
          displayErr = "Yorug'lik juda kuchli";
        }
      }
      speak(displayErr);
      setStatus('error', '❌ ' + displayErr);
      isSaving = false;
      setTimeout(() => { startFaceDetection(); }, 2500);
    }
  } catch (err) {
    console.error('Selfie save error:', err);
    setStatus('error', '❌ ' + (lang.startsWith('uz') ? 'Qayta urinib ko\'ring' : 'Please try again'));
    isSaving = false;
    setTimeout(() => { startFaceDetection(); }, 2500);
  }
}


// Auto-start on load
document.addEventListener('DOMContentLoaded', initCamera);

window.addEventListener('beforeunload', () => {
  if (stream) stream.getTracks().forEach(t => t.stop());
  clearInterval(faceCheckInterval);
});
