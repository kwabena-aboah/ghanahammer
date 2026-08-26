/**
 * GhanaHammer Auction Platform — Main JavaScript
 * Handles: Countdown timers, Vue bidding app, watchlist, utils
 */

// ─── Countdown Timer (used on listing cards) ────────────────────────────────
class GHCountdown {
  constructor(endTimeISO, element, onEnd) {
    this.endTime = new Date(endTimeISO);
    this.el = element;
    this.onEnd = onEnd;
    this.tick();
    this.interval = setInterval(() => this.tick(), 1000);
  }

  tick() {
    const now = new Date();
    const diff = this.endTime - now;
    if (diff <= 0) {
      clearInterval(this.interval);
      this.el.innerHTML = '<span class="text-danger fw-bold">ENDED</span>';
      if (this.onEnd) this.onEnd();
      return;
    }

    const d = Math.floor(diff / 86400000);
    const h = Math.floor((diff % 86400000) / 3600000);
    const m = Math.floor((diff % 3600000) / 60000);
    const s = Math.floor((diff % 60000) / 1000);

    const isUrgent = diff < 3600000; // < 1 hour

    if (d > 0) {
      this.el.innerHTML = `<span class="${isUrgent ? 'gh-countdown ending' : 'gh-countdown'}">${d}d ${h}h ${m}m</span>`;
    } else {
      this.el.innerHTML = `
        <span class="${isUrgent ? 'gh-countdown ending' : 'gh-countdown'}">
          ${pad(h)}:${pad(m)}:${pad(s)}
        </span>`;
    }

    if (isUrgent) this.el.closest('.gh-auction-card')?.classList.add('ending-soon');
  }
}

function pad(n) { return String(n).padStart(2, '0'); }

// Auto-init all countdown elements on page
function initCountdowns() {
  document.querySelectorAll('[data-countdown]').forEach(el => {
    new GHCountdown(el.dataset.countdown, el, () => {
      el.closest('.gh-auction-card')?.classList.add('auction-ended');
    });
  });
}

// ─── Block Timer (detail page boxes) ────────────────────────────────────────
class GHBlockTimer {
  constructor(endTimeISO) {
    this.endTime = new Date(endTimeISO);
    this.dEl = document.getElementById('timer-days');
    this.hEl = document.getElementById('timer-hours');
    this.mEl = document.getElementById('timer-minutes');
    this.sEl = document.getElementById('timer-seconds');
    if (!this.sEl) return;
    this.tick();
    setInterval(() => this.tick(), 1000);
  }

  tick() {
    const diff = Math.max(0, this.endTime - new Date());
    const d = Math.floor(diff / 86400000);
    const h = Math.floor((diff % 86400000) / 3600000);
    const m = Math.floor((diff % 3600000) / 60000);
    const s = Math.floor((diff % 60000) / 1000);
    if (this.dEl) this.dEl.textContent = pad(d);
    if (this.hEl) this.hEl.textContent = pad(h);
    if (this.mEl) this.mEl.textContent = pad(m);
    if (this.sEl) this.sEl.textContent = pad(s);
  }
}

// ─── Watchlist Toggle ────────────────────────────────────────────────────────
async function toggleWatchlist(auctionId, btn) {
  const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value
    || document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';

  try {
    const resp = await fetch(`/api/v1/auctions/${auctionId}/watch/`, {
      method: 'POST',
      headers: { 'X-CSRFToken': csrfToken, 'Content-Type': 'application/json' },
    });
    const data = await resp.json();
    if (data.watching) {
      btn.classList.add('watching');
      btn.innerHTML = '<i class="bi bi-heart-fill"></i>';
      btn.title = 'Remove from watchlist';
    } else {
      btn.classList.remove('watching');
      btn.innerHTML = '<i class="bi bi-heart"></i>';
      btn.title = 'Add to watchlist';
    }
  } catch (e) {
    console.error('Watchlist error:', e);
  }
}

// ─── Copy to Clipboard ───────────────────────────────────────────────────────
function copyToClipboard(text, btn) {
  navigator.clipboard.writeText(text).then(() => {
    const original = btn.innerHTML;
    btn.innerHTML = '<i class="bi bi-check"></i> Copied!';
    setTimeout(() => btn.innerHTML = original, 2000);
  });
}

// ─── Image Gallery ───────────────────────────────────────────────────────────
function initGallery() {
  const thumbs = document.querySelectorAll('.gh-gallery-thumb');
  const mainImg = document.getElementById('gh-gallery-main');
  if (!mainImg) return;
  thumbs.forEach(thumb => {
    thumb.addEventListener('click', () => {
      mainImg.src = thumb.dataset.large || thumb.src;
      thumbs.forEach(t => t.classList.remove('active'));
      thumb.classList.add('active');
    });
  });
}

// ─── Bulk Import File Size Check ─────────────────────────────────────────────
function checkFileSize(input, maxMB = 10) {
  const file = input.files[0];
  if (file && file.size > maxMB * 1024 * 1024) {
    alert(`File is too large. Max ${maxMB}MB allowed.`);
    input.value = '';
    return false;
  }
  return true;
}

// ─── Price Formatter ─────────────────────────────────────────────────────────
function formatGHS(amount) {
  return 'GHS ' + parseFloat(amount).toLocaleString('en-GH', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// ─── AI Price Recommendation Button ──────────────────────────────────────────
async function fetchAIPriceRecommendation(categoryId, title, condition) {
  const csrfToken = document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';
  try {
    const resp = await fetch('/api/v1/ai/price-recommendation/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
      body: JSON.stringify({ category_id: categoryId, title, condition }),
    });
    return await resp.json();
  } catch (e) {
    return { success: false };
  }
}

async function fetchAIDescription(title, categoryName, condition, location, extraNotes) {
  const csrfToken = document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';
  try {
    const resp = await fetch('/api/v1/ai/generate-description/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
      body: JSON.stringify({ title, category_name: categoryName, condition, location, extra_notes: extraNotes }),
    });
    const data = await resp.json();
    return data.description || '';
  } catch (e) {
    return '';
  }
}

// ─── DOMContentLoaded ────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initCountdowns();
  initGallery();

  // Block timer on detail page
  const timerEl = document.getElementById('timer-seconds');
  if (timerEl) {
    const endTime = document.querySelector('[data-end-time]')?.dataset.endTime;
    if (endTime) new GHBlockTimer(endTime);
  }

  // Smooth scroll for anchor links
  document.querySelectorAll('a[href^="#"]').forEach(a => {
    a.addEventListener('click', e => {
      const target = document.querySelector(a.getAttribute('href'));
      if (target) { e.preventDefault(); target.scrollIntoView({ behavior: 'smooth' }); }
    });
  });

  // Auto-dismiss alerts after 6s
  document.querySelectorAll('.alert:not(.alert-permanent)').forEach(alert => {
    setTimeout(() => {
      const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
      bsAlert?.close();
    }, 6000);
  });

  // Image upload preview
  document.querySelectorAll('.gh-img-upload').forEach(input => {
    input.addEventListener('change', function() {
      const preview = document.getElementById(this.dataset.preview);
      if (!preview || !this.files[0]) return;
      const reader = new FileReader();
      reader.onload = e => { preview.src = e.target.result; preview.classList.remove('d-none'); };
      reader.readAsDataURL(this.files[0]);
    });
  });
});

// Expose for use in Vue apps and templates
window.GH = {
  formatGHS,
  toggleWatchlist,
  copyToClipboard,
  fetchAIPriceRecommendation,
  fetchAIDescription,
};
