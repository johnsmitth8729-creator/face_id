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
      
      if (devX > 0.15 || devY > 0.18) {
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
    const frameData = captureFrame();
    const resp = await fetch('/api/verification/detect-face/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF },
      body: JSON.stringify({ frame: frameData }),
    });
    const result = await resp.json();
    const lang = (document.documentElement.lang || 'uz').toLowerCase().startsWith('uz') ? 'uz' : 'en';

    if (!result.face_detected) {
      faceGuide.classList.remove('active');
      let msg = lang === 'uz' ? '👤 Kameraga qarang.' : '👤 Please look at the camera.';
      if (result.error) {
        msg = `⚠️ Error: ${result.error}`;
        console.error("Backend detector error:", result.error);
      }
      setStatus('active', msg);
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

    if (result.looking_straight === false) {
      faceGuide.classList.remove('active');
      setStatus('active', lang === 'uz' ? "👤 Kameraga to'g'ri qarang." : "👤 Please look straight at the camera.");
      speak(lang === 'uz' ? "Kameraga to'g'ri qarang" : "Please look straight at the camera");
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
      speak(lang === 'uz' ? 'Qimirlamang' : 'Hold still');
    } else {
      setStatus('active', lang === 'uz' ? '⏳ Rasmga olinmoqda...' : '⏳ Capturing...');
      speak(lang === 'uz' ? 'Rasmga olinmoqda' : 'Capturing photo');
      isSaving = true;
      clearInterval(faceCheckInterval);
      await triggerSelfieSave(frameData);
    }
  } catch (e) {
    console.error("Face check loop error:", e);
    setStatus('error', `⚠️ Error: ${e.message || e}`);
  }
}

function captureFrame() {
  canvas.width = video.videoWidth || 640;
  canvas.height = video.videoHeight || 480;
  const ctx = canvas.getContext('2d');
  ctx.scale(-1, 1);
  ctx.drawImage(video, -canvas.width, 0, canvas.width, canvas.height);
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  return canvas.toDataURL('image/jpeg', 0.9);
}

async function triggerSelfieSave(imageData) {
  const lang = document.documentElement.lang || 'uz';
  try {
    const resp = await fetch('/api/verification/save-selfie/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF },
      body: JSON.stringify({ image: imageData }),
    });
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

      setStatus('captured', lang === 'uz' ? '📸 Rasm saqlandi!' : '📸 Photo saved!');
      speak(lang === 'uz' ? 'Rasm muvaffaqiyatli saqlandi' : 'Photo saved successfully');

      setTimeout(() => {
        if (stream) {
          stream.getTracks().forEach(t => t.stop());
        }
        window.location.href = '/step/3/';
      }, 1500);
    } else {
      speak(result.error || (lang === 'uz' ? 'Xatolik yuz berdi' : 'Error saving image'));
      setStatus('error', '❌ ' + (result.error || 'Error'));
      isSaving = false;
      startFaceDetection();
    }
  } catch (err) {
    console.error('Selfie save error:', err);
    setStatus('error', '❌ Server error');
    isSaving = false;
    startFaceDetection();
  }
}

// Auto-start on load
document.addEventListener('DOMContentLoaded', initCamera);

window.addEventListener('beforeunload', () => {
  if (stream) stream.getTracks().forEach(t => t.stop());
  clearInterval(faceCheckInterval);
});
