/**
 * AKHU AFIVS — Main JavaScript
 * Global utilities: navbar scroll, alerts, animations.
 */

// ── Navbar scroll effect ──
const navbar = document.getElementById('mainNavbar');
if (navbar) {
  window.addEventListener('scroll', () => {
    if (window.scrollY > 20) {
      navbar.classList.add('scrolled');
    } else {
      navbar.classList.remove('scrolled');
    }
  });
}

// ── Auto-dismiss alerts ──
document.querySelectorAll('.akhu-alert').forEach(alert => {
  setTimeout(() => {
    alert.style.opacity = '0';
    alert.style.transform = 'translateX(100%)';
    alert.style.transition = 'all 0.4s ease';
    setTimeout(() => alert.remove(), 400);
  }, 5000);
});

// ── Smooth anchor scrolling ──
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
  anchor.addEventListener('click', function(e) {
    const target = document.querySelector(this.getAttribute('href'));
    if (target) {
      e.preventDefault();
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  });
});

// ── Intersection Observer for animations ──
const animEls = document.querySelectorAll('.akhu-card, .stat-card, .how-card');
const observer = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      entry.target.style.opacity = '1';
      entry.target.style.transform = 'translateY(0)';
      observer.unobserve(entry.target);
    }
  });
}, { threshold: 0.1 });

animEls.forEach(el => {
  el.style.opacity = '0';
  el.style.transform = 'translateY(20px)';
  el.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
  observer.observe(el);
});

// ── Global CSRF helper ──
function getCsrfToken() {
  return document.cookie.match(/csrftoken=([^;]+)/)?.[1] || 
    document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
}

// ── AJAX helper ──
async function apiPost(url, data) {
  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': getCsrfToken(),
    },
    body: JSON.stringify(data),
  });
  return resp.json();
}

// ── Loading overlay ──
function showLoading(msg = 'Processing...') {
  const overlay = document.createElement('div');
  overlay.className = 'loading-overlay';
  overlay.id = 'globalLoadingOverlay';
  overlay.innerHTML = `
    <div class="loading-spinner"></div>
    <p style="color:var(--text-secondary);margin:0;">${msg}</p>
  `;
  document.body.appendChild(overlay);
}

function hideLoading() {
  document.getElementById('globalLoadingOverlay')?.remove();
}
