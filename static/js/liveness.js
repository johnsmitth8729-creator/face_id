/**
 * AKHU AFIVS — Liveness Detection JavaScript (Fully Automated & Voice-Guided)
 */

// Force disable any speech synthesis globally to ensure absolute silence
if ('speechSynthesis' in window) {
  window.speechSynthesis.speak = function() {};
  window.speechSynthesis.cancel = function() {};
}

const video = document.getElementById('livenessVideo');
const guide = document.getElementById('livenessGuide');
const statusEl = document.getElementById('livenessStatus');
const instructionEl = document.getElementById('challengeInstruction');
const iconEl = document.getElementById('challengeIconEl');
const challengeListEl = document.getElementById('challengeList');
const completeEl = document.getElementById('livenessComplete');
const errorEl = document.getElementById('livenessError');
const errorMsgEl = document.getElementById('livenessErrorMsg');
const overlayText = document.getElementById('livenessInstructionText');

// Local shape detection API fallback
let localDetector = null;
if ('FaceDetector' in window) {
  localDetector = new FaceDetector({ fastMode: true, maxDetectedFaces: 1 });
}

const CSRF = document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';
let stream = null;
let currentChallengeIdx = 0;
let challengeResults = [];
let autoCheckInterval = null;
let isChecking = false;
let challengeStartTime = 0;

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
          facingMode: 'user',
          width: { ideal: 1280 },
          height: { ideal: 720 },
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
          console.log("Applied autofocus/exposure in liveness:", advancedConstraints);
        }
      }
    } catch (err) {
      console.warn("Could not apply autofocus/exposure:", err);
    }

    await video.play();
    
    const lang = document.documentElement.lang || 'uz';
    speak(lang === 'uz' ? 'Endi yuzingizni turli burchaklardan saqlaymiz' : 'Now we will capture your face from different angles');
    
    setTimeout(startNextChallenge, 1500);
  } catch (err) {
    console.error('Camera init error:', err);
    showError('Camera access denied.');
  }
}

function createMockVideoStream() {
  const canvas = document.createElement('canvas');
  canvas.width = 640;
  canvas.height = 480;
  const ctx = canvas.getContext('2d');
  
  function drawFrame() {
    ctx.fillStyle = '#0a1628';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    
    ctx.strokeStyle = 'rgba(245, 158, 11, 0.2)';
    ctx.lineWidth = 1;
    for (let i = 0; i < canvas.width; i += 40) {
      ctx.beginPath(); ctx.moveTo(i, 0); ctx.lineTo(i, canvas.height); ctx.stroke();
    }
    for (let j = 0; j < canvas.height; j += 40) {
      ctx.beginPath(); ctx.moveTo(0, j); ctx.lineTo(canvas.width, j); ctx.stroke();
    }
    
    ctx.fillStyle = '#10b981';
    ctx.beginPath();
    ctx.arc(320, 240, 100, 0, Math.PI * 2);
    ctx.fill();
    
    ctx.fillStyle = '#0a1628';
    ctx.beginPath();
    ctx.arc(280, 220, 12, 0, Math.PI * 2);
    ctx.arc(360, 220, 12, 0, Math.PI * 2);
    ctx.fill();
    
    ctx.strokeStyle = '#0a1628';
    ctx.lineWidth = 6;
    ctx.beginPath();
    ctx.arc(320, 250, 40, 0, Math.PI);
    ctx.stroke();
    
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 20px Inter, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('MOCK LIVENESS WEBCAM', 320, 390);
    
    requestAnimationFrame(drawFrame);
  }
  
  drawFrame();
  return canvas.captureStream(30);
}

function checkFrameBrightness(ctx, width, height) {
  const imgData = ctx.getImageData(0, 0, width, height);
  const data = imgData.data;
  let colorSum = 0;
  const step = 8;
  let count = 0;
  for(let x = 0; x < data.length; x += 4 * step) {
    const r = data[x];
    const g = data[x+1];
    const b = data[x+2];
    const avg = 0.299 * r + 0.587 * g + 0.114 * b;
    colorSum += avg;
    count++;
  }
  return Math.floor(colorSum / count);
}

function buildChallengeList() {
  challengeListEl.innerHTML = '';
  CHALLENGES.forEach((ch, i) => {
    const item = document.createElement('div');
    item.className = 'challenge-item';
    item.id = `challenge-item-${i}`;
    item.innerHTML = `
      <i class="bi ${CHALLENGE_ICONS[ch.type] || 'bi-circle'} challenge-item-icon" id="ci-icon-${i}"></i>
      <span class="challenge-item-text">${ch.instruction}</span>
      <i class="bi bi-circle challenge-check" id="ci-check-${i}"></i>
    `;
    challengeListEl.appendChild(item);
  });
}

function startNextChallenge() {
  if (currentChallengeIdx >= CHALLENGES.length) {
    finishLiveness();
    return;
  }

  const ch = CHALLENGES[currentChallengeIdx];
  iconEl.className = `bi ${CHALLENGE_ICONS[ch.type] || 'bi-eye-fill'}`;
  instructionEl.textContent = ch.instruction;
  
  if (overlayText) {
    overlayText.textContent = ch.instruction;
  }

  document.querySelectorAll('.challenge-item').forEach((el, i) => {
    el.classList.remove('active', 'done', 'failed');
    if (i < currentChallengeIdx) el.classList.add('done');
    else if (i === currentChallengeIdx) el.classList.add('active');
  });

  const lang = document.documentElement.lang || 'uz';
  const text = lang === 'uz' ? "Kameraga qarang..." : "Look at the camera...";
  statusEl.querySelector('span').textContent = text;
  if (overlayText) {
    overlayText.textContent = text;
  }

  // Play voice command for the current pose
  if (ch.type === 'look_left') {
    speak(lang === 'uz' ? 'Iltimos, chapga qarang' : 'Please look left');
  } else if (ch.type === 'look_right') {
    speak(lang === 'uz' ? 'Iltimos, o\'ngga qarang' : 'Please look right');
  } else if (ch.type === 'look_up') {
    speak(lang === 'uz' ? 'Iltimos, yuqoriga qarang' : 'Please look up');
  } else if (ch.type === 'blink') {
    speak(lang === 'uz' ? 'Iltimos, ko\'zingizni yuming' : 'Please blink');
  }

  startAutoChecking();
}

function startAutoChecking() {
  if (autoCheckInterval) clearInterval(autoCheckInterval);
  challengeStartTime = Date.now();

  autoCheckInterval = setInterval(async () => {
    if (isChecking || !stream || !video.readyState) return;

    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth || 640;
    canvas.height = video.videoHeight || 480;
    const ctx = canvas.getContext('2d');
    ctx.scale(-1, 1);
    ctx.drawImage(video, -canvas.width, 0, canvas.width, canvas.height);

    const brightness = checkFrameBrightness(ctx, canvas.width, canvas.height);
    const lang = document.documentElement.lang || 'uz';
    if (brightness < 60 || brightness > 230) {
      const text = brightness < 60
        ? (lang === 'uz' ? "⚠️ Xona juda qorong'u!" : "⚠️ Room is too dark!")
        : (lang === 'uz' ? "⚠️ Yorug'lik juda kuchli!" : "⚠️ Too much light!");
      statusEl.querySelector('span').textContent = text;
      if (overlayText) {
        overlayText.textContent = text;
      }
      return;
    }

    // Fast client-side face check if native FaceDetector is supported
    if (localDetector) {
      try {
        const faces = await localDetector.detect(video);
        if (faces.length === 0) {
          guide.classList.remove('active');
          const text = lang === 'uz' ? '👤 Kameraga qarang.' : '👤 Please look at the camera.';
          statusEl.querySelector('span').textContent = text;
          if (overlayText) overlayText.textContent = text;
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
          guide.classList.remove('active');
          const text = lang === 'uz' ? '⚠️ Yuzingizni doira ichiga joylashtiring.' : '⚠️ Center your face in the oval.';
          statusEl.querySelector('span').textContent = text;
          if (overlayText) overlayText.textContent = text;
          return;
        }
      } catch (e) {
        console.warn("Local FaceDetector failed in liveness, falling back to server:", e);
      }
    }

    isChecking = true;
    const ch = CHALLENGES[currentChallengeIdx];
    const frame = canvas.toDataURL('image/jpeg', 0.7);

    const result = await verifyChallenge(frame, ch.type);
    isChecking = false;

    if (result && result.success) {
      clearInterval(autoCheckInterval);
      autoCheckInterval = null;
      speak(lang === 'uz' ? 'Muvaffaqiyatli' : 'Success');
      passChallenge(currentChallengeIdx);
    } else {
      if (result) {
        let errMsg = result.error;
        if (lang === 'uz') {
          if (errMsg === 'No face detected' || errMsg.includes('landmarks') || errMsg.includes('No face detected')) {
            errMsg = "👤 Yuz aniqlanmadi. Kameraga qarang.";
          } else if (errMsg.includes('Multiple faces')) {
            errMsg = "👤 Kamerada bir nechta yuz aniqlandi. Faqat o'zingiz turing.";
          } else if (errMsg.includes('left')) {
            errMsg = "Iltimos, chapga qarang";
          } else if (errMsg.includes('right')) {
            errMsg = "Iltimos, o'ngga qarang";
          } else if (errMsg.includes('up')) {
            errMsg = "Iltimos, yuqoriga qarang";
          } else if (errMsg.includes('blink')) {
            errMsg = "Iltimos, ko'zingizni bir soniyaga yuming";
          }
        }
        const text = errMsg || (lang === 'uz' ? "Harakat aniqlanmadi. Qayta urinib ko'ring." : "Movement not detected. Please try again.");
        statusEl.querySelector('span').textContent = text;
        if (overlayText) {
          overlayText.textContent = text;
        }
      } else {
        const text = lang === 'uz' ? "Ulanish xatosi" : "Connection error";
        statusEl.querySelector('span').textContent = text;
        if (overlayText) {
          overlayText.textContent = text;
        }
      }
    }
  }, 350); // Check every 350ms
}

async function verifyChallenge(frame, challengeType) {
  try {
    const resp = await fetch(API_VERIFY_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF_TOKEN || CSRF },
      body: JSON.stringify({ frame, challenge_type: challengeType }),
    });
    return await resp.json();
  } catch (err) {
    console.error('Challenge verify error:', err);
    return null;
  }
}

function passChallenge(idx) {
  const item = document.getElementById(`challenge-item-${idx}`);
  const icon = document.getElementById(`ci-icon-${idx}`);
  const check = document.getElementById(`ci-check-${idx}`);

  if (item) item.classList.remove('active');
  if (item) item.classList.add('done');
  if (icon) icon.className = `bi ${CHALLENGE_ICONS[CHALLENGES[idx].type]} challenge-item-icon done`;
  if (check) check.className = 'bi bi-check-circle-fill challenge-check text-success';

  challengeResults.push({ type: CHALLENGES[idx].type, passed: true });
  currentChallengeIdx++;

  setTimeout(startNextChallenge, 400);
}

async function finishLiveness() {
  if (autoCheckInterval) {
    clearInterval(autoCheckInterval);
    autoCheckInterval = null;
  }

  const passed = challengeResults.filter(r => r.passed).length;
  if (passed < CHALLENGES.length) {
    showError('Not all challenges passed. Please try again.');
    return;
  }

  const lang = document.documentElement.lang || 'uz';
  instructionEl.textContent = lang === 'uz' ? 'Yuborilmoqda...' : 'Processing...';
  guide.classList.add('active');

  speak(lang === 'uz' ? 'Barcha holatlar saqlandi. Ma\'lumotlar yuklanmoqda' : 'All angles captured. Saving data');

  try {
    // Mark liveness complete
    await fetch(API_COMPLETE_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF_TOKEN || CSRF },
      body: JSON.stringify({}),
    });

    // Trigger face matching
    instructionEl.textContent = lang === 'uz' ? 'Solishirilmoqda...' : 'Matching faces...';
    const matchResp = await fetch(API_MATCH_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF_TOKEN || CSRF },
      body: JSON.stringify({}),
    });
    const matchResult = await matchResp.json();

    if (stream) stream.getTracks().forEach(t => t.stop());

    if (matchResult.success) {
      if (completeEl) completeEl.classList.remove('d-none');
      setTimeout(() => { window.location.href = LIVENESS_COMPLETE_URL; }, 1200);
    } else {
      showError(matchResult.error || 'Face matching failed. Please try again.');
    }
  } catch (err) {
    showError('An error occurred during verification. Please try again.');
  }
}

function showError(msg) {
  errorMsgEl.textContent = msg;
  errorEl.classList.remove('d-none');
  if (stream) stream.getTracks().forEach(t => t.stop());
}

// Start immediately on load
buildChallengeList();
initCamera();

window.addEventListener('beforeunload', () => {
  if (stream) stream.getTracks().forEach(t => t.stop());
  if (autoCheckInterval) clearInterval(autoCheckInterval);
});
