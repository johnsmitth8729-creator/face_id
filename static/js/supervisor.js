/**
 * AKHU AFIVS — Supervisor Exam-Day Verification JavaScript
 * Handles live camera feed and real-time face matching.
 */

const video = document.getElementById('examVideo');
const verifyBtn = document.getElementById('verifyNowBtn');
const resultWaiting = document.getElementById('resultWaiting');
const resultBanner = document.getElementById('resultBanner');
const resultBannerInner = document.getElementById('resultBannerInner');
const resultLoading = document.getElementById('resultLoading');
const bannerIcon = document.getElementById('bannerIcon');
const bannerTitle = document.getElementById('bannerTitle');
const bannerSub = document.getElementById('bannerSub');
const bannerScore = document.getElementById('bannerScore');

const CSRF = document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';

let stream = null;

// ── Init Camera ──
async function initCamera() {
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: 'user', width: { ideal: 1280 } },
      audio: false,
    });
    video.srcObject = stream;
    if (typeof AUTO_SCAN_MODE !== 'undefined' && AUTO_SCAN_MODE) {
      initAutoScanCamera();
    }
  } catch (err) {
    console.error('Camera error:', err);
    alert('Camera access denied. Please allow camera permissions.');
  }
}

// ── Capture Frame ──
function captureFrame() {
  const canvas = document.createElement('canvas');
  canvas.width = video.videoWidth || 640;
  canvas.height = video.videoHeight || 480;
  const ctx = canvas.getContext('2d');
  ctx.scale(-1, 1);
  ctx.drawImage(video, -canvas.width, 0, canvas.width, canvas.height);
  return canvas.toDataURL('image/jpeg', 0.9);
}

// ── Auto-Scan 1:N Identification Loop ──
let scanInterval = null;
let scanningInProgress = false;
let lastResultWasSuccess = false;
let identifiedProfileId = null;

function initAutoScanCamera() {
  if (scanInterval) clearInterval(scanInterval);

  scanInterval = setInterval(async () => {
    if (scanningInProgress || !stream || !video.readyState) return;

    scanningInProgress = true;

    const statusOverlay = document.getElementById('scanStatusOverlay');
    if (statusOverlay) {
      statusOverlay.innerHTML = `<span class="badge bg-primary px-3 py-2"><i class="bi bi-activity me-1"></i> SCANNING</span>`;
    }

    const frame = captureFrame();

    try {
      const resp = await fetch(API_EXAM_IDENTIFY, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF_TOKEN || CSRF },
        body: JSON.stringify({ frame: frame }),
      });

      const result = await resp.json();

      if (result.success) {
        if (statusOverlay) {
          statusOverlay.innerHTML = `<span class="badge bg-success px-3 py-2"><i class="bi bi-person-check-fill me-1"></i> IDENTIFIED</span>`;
        }

        showAutoScanResult(result);
        lastResultWasSuccess = true;

        // Pause scanning for 12 seconds to display candidate details, check-in button, then clear and resume
        setTimeout(() => {
          clearAutoScanResult();
          lastResultWasSuccess = false;
          scanningInProgress = false;
        }, 12000);
      } else {
        // No face or no match — show searching state, clear any previous result
        if (statusOverlay) {
          const noFace = result.error && result.error.includes('No face');
          statusOverlay.innerHTML = noFace
            ? `<span class="badge bg-secondary px-3 py-2"><i class="bi bi-eye-slash me-1"></i> NO FACE</span>`
            : `<span class="badge bg-secondary px-3 py-2"><i class="bi bi-person-x-fill me-1"></i> SEARCHING...</span>`;
        }
        // If previous scan was a success, clear the old result
        if (lastResultWasSuccess) {
          clearAutoScanResult();
          lastResultWasSuccess = false;
        }
        scanningInProgress = false;
      }
    } catch (err) {
      console.error('Scan API error:', err);
      scanningInProgress = false;
    }
  }, 2500); // 2.5s intervals — balance between responsiveness and server load
}

function showAutoScanResult(result) {
  const indicator = result.indicator; // green, yellow, red
  const score = result.match_percentage;

  // Set global identified ID
  identifiedProfileId = result.applicant?.id;

  let icon, title, sub, scoreClass;

  if (indicator === 'green') {
    icon = '<i class="bi bi-check-circle-fill" style="color:var(--akhu-success)"></i>';
    title = '✅ ' + (result.message || 'Identity Confirmed');
    sub = `${result.applicant?.full_name} — ${result.applicant?.admission_id}`;
    scoreClass = 'verified';
  } else if (indicator === 'yellow') {
    icon = '<i class="bi bi-exclamation-triangle-fill" style="color:var(--akhu-warning)"></i>';
    title = '⚠️ ' + (result.message || 'Manual Review Required');
    sub = `${result.applicant?.full_name} — ${result.applicant?.admission_id}`;
    scoreClass = 'review_required';
  } else {
    icon = '<i class="bi bi-x-circle-fill" style="color:var(--akhu-danger)"></i>';
    title = '❌ ' + (result.message || 'Identity Mismatch');
    sub = 'Refer applicant to examination committee';
    scoreClass = 'rejected';
  }

  resultBannerInner.className = `result-banner ${indicator}`;
  bannerIcon.innerHTML = icon;
  bannerTitle.textContent = title;
  bannerSub.textContent = sub;
  bannerScore.className = `status-badge ${scoreClass} fs-6`;
  bannerScore.textContent = `${score}% Match`;

  // Update candidate card
  const nameEl = document.getElementById('identifiedName');
  const admEl = document.getElementById('identifiedAdmissionId');
  const passEl = document.getElementById('identifiedPassport');
  if (nameEl) nameEl.textContent = result.applicant?.full_name || '-';
  if (admEl) admEl.textContent = result.applicant?.admission_id || '-';
  if (passEl) passEl.textContent = result.applicant?.passport_number || '-';

  const historyBtn = document.getElementById('identifiedHistoryBtn');
  if (historyBtn && result.applicant?.id) {
    historyBtn.href = `/supervisor/history/${result.applicant.id}/`;
  }

  // Show auto-scan check-in box if matching applicant was identified
  const autoConfirmBox = document.getElementById('autoConfirmAttendanceBox');
  const autoBtn = document.getElementById('autoConfirmAttendanceBtn');
  const autoMsg = document.getElementById('autoAttendanceSuccessMsg');
  
  if (autoConfirmBox) {
    if (result.applicant?.id && indicator === 'green') {
      autoConfirmBox.classList.remove('d-none');
      if (autoBtn) {
        autoBtn.classList.remove('d-none');
        autoBtn.disabled = false;
      }
      if (autoMsg) autoMsg.classList.add('d-none');
    } else if (result.applicant?.id && indicator !== 'green') {
      autoConfirmBox.classList.remove('d-none');
      if (autoBtn) {
        autoBtn.classList.add('d-none');
      }
      if (autoMsg) {
        autoMsg.className = "text-danger small mt-2 fw-bold";
        autoMsg.innerHTML = `<i class="bi bi-x-circle-fill me-1"></i> Yuz mos kelmadi. Tasdiqlash rad etildi!`;
        autoMsg.classList.remove('d-none');
      }
    } else {
      autoConfirmBox.classList.add('d-none');
    }
  }

  resultWaiting.classList.add('d-none');
  resultBanner.classList.remove('d-none');
}

function clearAutoScanResult() {
  const statusOverlay = document.getElementById('scanStatusOverlay');
  if (statusOverlay) {
    statusOverlay.innerHTML = `<span class="badge bg-primary px-3 py-2"><i class="bi bi-activity me-1"></i> SCANNING</span>`;
  }
  resultBanner.classList.add('d-none');
  resultWaiting.classList.remove('d-none');
}

// ── Verify Now (Manual Mode) ──
verifyBtn?.addEventListener('click', async () => {
  if (!stream || !video.readyState) {
    alert('Camera not ready');
    return;
  }

  resultWaiting.classList.add('d-none');
  resultBanner.classList.add('d-none');
  resultLoading.classList.remove('d-none');
  verifyBtn.disabled = true;

  const frame = captureFrame();

  try {
    const resp = await fetch(API_EXAM_VERIFY, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF_TOKEN || CSRF },
      body: JSON.stringify({
        profile_id: PROFILE_ID,
        frame: frame,
      }),
    });

    const result = await resp.json();
    resultLoading.classList.add('d-none');

    if (result.success) {
      showResult(result);
    } else {
      showError(result.error || 'Verification failed');
    }
  } catch (err) {
    resultLoading.classList.add('d-none');
    showError('Network error. Please try again.');
  } finally {
    verifyBtn.disabled = false;
  }
});

function showResult(result) {
  const indicator = result.indicator; // green, yellow, red
  const score = result.match_percentage;

  let icon, title, sub, scoreClass;

  if (indicator === 'green') {
    icon = '<i class="bi bi-check-circle-fill" style="color:var(--akhu-success)"></i>';
    title = '✅ ' + (result.message || 'Identity Confirmed');
    sub = `${result.applicant?.full_name} — ${result.applicant?.admission_id}`;
    scoreClass = 'verified';
  } else if (indicator === 'yellow') {
    icon = '<i class="bi bi-exclamation-triangle-fill" style="color:var(--akhu-warning)"></i>';
    title = '⚠️ ' + (result.message || 'Manual Review Required');
    sub = `${result.applicant?.full_name} — ${result.applicant?.admission_id}`;
    scoreClass = 'review_required';
  } else {
    icon = '<i class="bi bi-x-circle-fill" style="color:var(--akhu-danger)"></i>';
    title = '❌ ' + (result.message || 'Identity Mismatch');
    sub = 'Refer applicant to examination committee';
    scoreClass = 'rejected';
  }

  resultBannerInner.className = `result-banner ${indicator}`;
  bannerIcon.innerHTML = icon;
  bannerTitle.textContent = title;
  bannerSub.textContent = sub;
  bannerScore.className = `status-badge ${scoreClass} fs-6`;
  bannerScore.textContent = `${score}% Match`;

  // Reset and show check-in button only if verified (indicator === 'green')
  const confirmBtn = document.getElementById('confirmAttendanceBtn');
  const confirmMsg = document.getElementById('attendanceSuccessMsg');
  const confirmBox = document.getElementById('confirmAttendanceBox');
  if (confirmBox) {
    confirmBox.classList.remove('d-none');
  }
  if (indicator === 'green') {
    if (confirmBtn) {
      confirmBtn.classList.remove('d-none');
      confirmBtn.disabled = false;
    }
    if (confirmMsg) {
      confirmMsg.classList.add('d-none');
    }
  } else {
    if (confirmBtn) {
      confirmBtn.classList.add('d-none');
    }
    if (confirmMsg) {
      confirmMsg.className = "text-danger small mt-2 fw-bold";
      confirmMsg.innerHTML = `<i class="bi bi-x-circle-fill me-1"></i> Yuz mos kelmadi. Tasdiqlash rad etildi!`;
      confirmMsg.classList.remove('d-none');
    }
  }

  resultWaiting.classList.add('d-none');
  resultBanner.classList.remove('d-none');
}

function showError(msg) {
  resultBannerInner.className = 'result-banner red';
  bannerIcon.innerHTML = '<i class="bi bi-exclamation-triangle-fill" style="color:var(--akhu-danger)"></i>';
  bannerTitle.textContent = 'Verification Error';
  bannerSub.textContent = msg;
  bannerScore.textContent = '';

  const confirmBox = document.getElementById('confirmAttendanceBox');
  if (confirmBox) {
    confirmBox.classList.add('d-none');
  }

  resultWaiting.classList.add('d-none');
  resultBanner.classList.remove('d-none');
}

// ── Bind Check-in Events ──
document.addEventListener('DOMContentLoaded', () => {
  const confirmBtn = document.getElementById('confirmAttendanceBtn');
  confirmBtn?.addEventListener('click', async () => {
    confirmBtn.disabled = true;
    try {
      const resp = await fetch('/api/supervisor/confirm-attendance/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF_TOKEN || CSRF },
        body: JSON.stringify({ profile_id: PROFILE_ID }),
      });
      const res = await resp.json();
      if (res.success) {
        document.getElementById('attendanceSuccessMsg').classList.remove('d-none');
        confirmBtn.classList.add('d-none');
      } else {
        alert(res.error || 'Attendance check-in failed');
        confirmBtn.disabled = false;
      }
    } catch (err) {
      alert('Network error');
      confirmBtn.disabled = false;
    }
  });

  const autoConfirmBtn = document.getElementById('autoConfirmAttendanceBtn');
  autoConfirmBtn?.addEventListener('click', async () => {
    if (!identifiedProfileId) return;
    autoConfirmBtn.disabled = true;
    try {
      const resp = await fetch('/api/supervisor/confirm-attendance/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CSRF_TOKEN || CSRF },
        body: JSON.stringify({ profile_id: identifiedProfileId }),
      });
      const res = await resp.json();
      if (res.success) {
        document.getElementById('autoAttendanceSuccessMsg').classList.remove('d-none');
        autoConfirmBtn.classList.add('d-none');
      } else {
        alert(res.error || 'Attendance check-in failed');
        autoConfirmBtn.disabled = false;
      }
    } catch (err) {
      alert('Network error');
      autoConfirmBtn.disabled = false;
    }
  });
});

initCamera();

window.addEventListener('beforeunload', () => {
  if (stream) stream.getTracks().forEach(t => t.stop());
  if (scanInterval) clearInterval(scanInterval);
});
