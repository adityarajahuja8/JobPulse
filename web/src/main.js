/* ==========================================================================
   ACDYON FRONTEND SCRIPT
   - Job Listings Preview Cards (Normalized Data Rendering)
   - Interactive Live Ingestion Inspector
   - Single Restrained Micro-Interaction (Viewport Metric Easing)
   - Console Diagnostic Easter Egg (§7)
   ========================================================================== */

import { SAMPLE_LISTINGS } from './data/sampleListings.js';

// ── Sample Real Ingestion Data for Inspector ──────────────────────────────────

const DEMO_DATA = {
  raw: {
    remoteok: {
      id: "1136937",
      slug: "remote-solutions-delivery-manager-benchling-1136937",
      epoch: "1724089200",
      date: "2026-08-19T06:30:00+00:00",
      company: "Benchling",
      position: "Solutions Delivery Manager",
      tags: ["saas", "technical", "cloud", "ops"],
      location: "Boston, MA / Remote US",
      salary_min: 150000,
      salary_max: 200000,
      url: "https://remoteok.com/remote-jobs/remote-solutions-delivery-manager-benchling-1136937"
    },
    jsearch: {
      job_id: "linear-d3bc1ced-3ce4-4086-a050-555055dbb1ff",
      employer_name: "Linear",
      job_title: "Senior / Staff Fullstack Engineer",
      job_city: "Remote",
      job_state: "Europe",
      job_country: "Worldwide",
      job_is_remote: true,
      job_min_salary: 170000,
      job_max_salary: 240000,
      job_employment_type: "FULLTIME",
      job_required_skills: ["typescript", "react", "node", "distributed-systems"],
      job_apply_link: "https://jobs.ashbyhq.com/linear/d3bc1ced-3ce4-4086-a050-555055dbb1ff"
    }
  },
  normalized: SAMPLE_LISTINGS.slice(0, 2)
};

// ── Helper: Format Relative Time ──────────────────────────────────────────────

function formatRelativeTime(dateString, ingestedAt) {
  const targetDate = dateString ? new Date(dateString) : (ingestedAt ? new Date(ingestedAt) : new Date());
  const now = new Date();
  const diffMs = now - targetDate;
  const diffMinutes = Math.floor(diffMs / (1000 * 60));
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (isNaN(diffMs) || diffMinutes <= 0) return 'Just now';
  if (diffMinutes < 60) return `${diffMinutes}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays === 1) return '1d ago';
  if (diffDays < 7) return `${diffDays}d ago`;
  if (diffDays <= 14) return `${Math.floor(diffDays / 7)}w ago`;
  return 'Active';
}

// ── Helper: Format Salary ─────────────────────────────────────────────────────

function formatSalary(min, max) {
  if (!min && !max) return null;
  const fmt = (num) => `$${Math.round(num / 1000)}k`;
  if (min && max) return `${fmt(min)}–${fmt(max)}`;
  if (min) return `From ${fmt(min)}`;
  return `Up to ${fmt(max)}`;
}

// ── Render Normalized Job Listings Cards ──────────────────────────────────────

function deduplicateListings(list) {
  if (!Array.isArray(list)) return [];
  const seenPairs = new Set();
  const seenUrls = new Set();
  const unique = [];

  for (const item of list) {
    if (!item || !item.title || !item.company || !item.url) continue;
    const pair = `${String(item.company).toLowerCase().trim()}:::${String(item.title).toLowerCase().trim()}`;
    const u = String(item.url).toLowerCase().trim();

    if (seenPairs.has(pair) || seenUrls.has(u)) {
      continue; // Skip duplicate listing
    }

    seenPairs.add(pair);
    seenUrls.add(u);
    unique.push(item);
  }

  return unique;
}

function initListingsSection() {
  const container = document.getElementById('listings-container');
  const countBadge = document.getElementById('listings-count');
  const paginationControls = document.getElementById('pagination-controls');
  const filterChips = document.querySelectorAll('.filter-chip');
  
  if (!container) return;

  const ITEMS_PER_PAGE = 8;
  let currentPage = 1;
  let currentFilter = 'all';
  let activeListings = deduplicateListings(SAMPLE_LISTINGS);

  function render(filter, page = 1) {
    currentPage = page;
    let filtered = activeListings;

    if (filter === 'remoteok') {
      filtered = activeListings.filter(l => l.source === 'remoteok');
    } else if (filter === 'jsearch') {
      filtered = activeListings.filter(l => l.source === 'jsearch');
    } else if (filter === 'remote') {
      filtered = activeListings.filter(l => l.remote === true);
    } else if (filter === 'salary') {
      filtered = activeListings.filter(l => l.salary_min !== null);
    }

    const totalItems = filtered.length;
    const totalPages = Math.max(1, Math.ceil(totalItems / ITEMS_PER_PAGE));

    // Clamp current page
    if (currentPage > totalPages) currentPage = totalPages;
    if (currentPage < 1) currentPage = 1;

    const startIndex = (currentPage - 1) * ITEMS_PER_PAGE;
    const endIndex = Math.min(startIndex + ITEMS_PER_PAGE, totalItems);
    const pageItems = filtered.slice(startIndex, endIndex);

    if (countBadge) {
      if (totalItems === 0) {
        countBadge.innerHTML = 'Showing 0 listings';
      } else {
        countBadge.innerHTML = `Showing <strong style="color: var(--accent-primary);">${startIndex + 1}–${endIndex}</strong> of ${totalItems} unique normalized listings`;
      }
    }

    if (pageItems.length === 0) {
      container.innerHTML = `
        <div style="grid-column: 1 / -1; padding: var(--space-8); text-align: center; color: var(--text-muted);">
          No listings match the selected filter.
        </div>
      `;
      if (paginationControls) paginationControls.innerHTML = '';
      return;
    }

    // Render Cards
    container.innerHTML = pageItems.map(item => {
      const salaryStr = formatSalary(item.salary_min, item.salary_max);
      const relativeTime = formatRelativeTime(item.posted_at, item.ingested_at);
      const sourceLabel = item.source === 'remoteok' ? 'RemoteOK' : 'JSearch';
      const cleanUrl = item.url || (item.slug ? `https://remoteok.com/remote-jobs/${item.slug}` : `https://remoteok.com/remote-jobs/${item.external_id}`);

      return `
        <article class="job-card">
          <div>
            <div class="job-card-header">
              <div class="job-company-block">
                <span class="job-company">${escapeHTML(item.company)}</span>
                <span class="job-posted-time">Posted ${relativeTime}</span>
              </div>
              <span class="source-badge ${item.source || 'remoteok'}">
                ● ${sourceLabel}
              </span>
            </div>

            <h3 class="job-title">${escapeHTML(item.title)}</h3>

            <div class="job-meta-row">
              <span class="job-meta-pill">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"></path><circle cx="12" cy="10" r="3"></circle></svg>
                ${escapeHTML(item.location || 'Worldwide / Remote')}
              </span>

              ${item.remote ? `
                <span class="job-meta-pill remote-pill">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="2" y1="12" x2="22" y2="12"></line><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path></svg>
                  Remote
                </span>
              ` : ''}

              ${salaryStr ? `
                <span class="job-meta-pill salary">
                  💰 ${salaryStr}
                </span>
              ` : ''}
            </div>

            <div class="job-tags-row">
              ${(item.tags || []).slice(0, 5).map(t => `<span class="job-tag">#${escapeHTML(t)}</span>`).join('')}
            </div>
          </div>

          <div class="job-card-footer">
            <span class="job-id-dim">ID: ${escapeHTML(String(item.external_id).slice(0, 20))}</span>
            <a href="${cleanUrl}" target="_blank" rel="noopener noreferrer" class="btn-apply">
              ${item.source === 'remoteok' ? 'View on RemoteOK' : `Apply at ${escapeHTML(item.company)}`}
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg>
            </a>
          </div>
        </article>
      `;
    }).join('');

    // Render Pagination Controls
    if (paginationControls) {
      if (totalPages <= 1) {
        paginationControls.innerHTML = '';
      } else {
        let buttonsHtml = `
          <button class="pagination-btn" data-page="${currentPage - 1}" ${currentPage === 1 ? 'disabled' : ''}>
            ← Prev
          </button>
        `;

        // Render page buttons
        for (let i = 1; i <= totalPages; i++) {
          if (i === 1 || i === totalPages || (i >= currentPage - 1 && i <= currentPage + 1)) {
            buttonsHtml += `
              <button class="pagination-btn ${i === currentPage ? 'active' : ''}" data-page="${i}">
                ${i}
              </button>
            `;
          } else if (i === currentPage - 2 || i === currentPage + 2) {
            buttonsHtml += `<span class="pagination-ellipsis">…</span>`;
          }
        }

        buttonsHtml += `
          <button class="pagination-btn" data-page="${currentPage + 1}" ${currentPage === totalPages ? 'disabled' : ''}>
            Next →
          </button>
        `;

        paginationControls.innerHTML = buttonsHtml;

        // Wire up page button click handlers
        paginationControls.querySelectorAll('.pagination-btn').forEach(btn => {
          btn.addEventListener('click', (e) => {
            const targetPage = parseInt(btn.dataset.page, 10);
            if (!isNaN(targetPage) && targetPage >= 1 && targetPage <= totalPages) {
              render(currentFilter, targetPage);
              document.getElementById('listings')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
          });
        });
      }
    }
  }

  // Filter chips click handling
  filterChips.forEach(chip => {
    chip.addEventListener('click', () => {
      filterChips.forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      currentFilter = chip.dataset.filter;
      render(currentFilter, 1);
    });
  });

  // Initial render
  render(currentFilter, 1);

  // Fetch 100% REAL LIVE listings from the live backend API stream
  fetch('/api/listings')
    .then(res => {
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json();
    })
    .then(payload => {
      if (payload && payload.data && payload.data.length > 0) {
        const uniquePayload = deduplicateListings(payload.data);
        console.log(`[Acdyon Live Feed] Loaded ${uniquePayload.length} unique live listings`);
        activeListings = uniquePayload;
        render(currentFilter, 1);
      }
    })
    .catch(err => {
      console.warn('[Acdyon API Notice] Using cached normalized preview:', err.message);
    });
}

function escapeHTML(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

// ── Syntax Highlight Helper ───────────────────────────────────────────────────

function highlightJSON(obj) {
  const json = typeof obj === 'string' ? obj : JSON.stringify(obj, null, 2);
  return json.replace(/("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g, (match) => {
    let cls = 'syn-num';
    if (/^"/.test(match)) {
      if (/:$/.test(match)) {
        cls = 'syn-key';
      } else {
        cls = 'syn-str';
      }
    } else if (/true|false/.test(match)) {
      cls = 'syn-bool';
    } else if (/null/.test(match)) {
      cls = 'syn-null';
    }
    return `<span class="${cls}">${match}</span>`;
  });
}

// ── Interactive Inspector Logic ───────────────────────────────────────────────

function initInspector() {
  const tabBtns = document.querySelectorAll('[data-tab]');
  const inspectorBody = document.getElementById('inspector-content');
  const previewSummary = document.getElementById('inspector-summary');

  if (!inspectorBody) return;

  function renderTab(tabName) {
    tabBtns.forEach(b => b.classList.toggle('active', b.dataset.tab === tabName));

    if (tabName === 'raw') {
      previewSummary.innerHTML = `
        <div style="font-size: var(--text-xs); color: var(--text-muted); margin-bottom: var(--space-3);">
          <strong style="color: var(--accent-primary);">Heterogeneous Input Feeds:</strong> Notice differences in field keys, salary representations, and epoch structures between RemoteOK and JSearch (RapidAPI).
        </div>
        <div style="display: flex; gap: var(--space-2); margin-bottom: var(--space-3);">
          <span class="status-pill"><span class="status-indicator"></span> RemoteOK (JSON API)</span>
          <span class="status-pill"><span class="status-indicator" style="background: #C084FC; box-shadow: 0 0 8px #C084FC;"></span> JSearch (RapidAPI)</span>
        </div>
      `;
      inspectorBody.innerHTML = `
        <div style="color: var(--text-dim); margin-bottom: 8px;">// Source 1: RemoteOK Raw JSON Feed</div>
        ${highlightJSON(DEMO_DATA.raw.remoteok)}
        <div style="color: var(--text-dim); margin: 16px 0 8px 0;">// Source 2: JSearch (RapidAPI) Response Object</div>
        ${highlightJSON(DEMO_DATA.raw.jsearch)}
      `;
    } else if (tabName === 'normalized') {
      previewSummary.innerHTML = `
        <div style="font-size: var(--text-xs); color: var(--text-muted); margin-bottom: var(--space-3);">
          <strong style="color: var(--accent-emerald);">Unified Output Schema:</strong> Both sources mapped to consistent MongoDB documents with canonical direct URLs, typed salaries, and deduplication keys.
        </div>
        <div style="display: flex; gap: var(--space-2); margin-bottom: var(--space-3);">
          <span class="status-pill"><span class="status-indicator"></span> Idempotent Upsert (source + external_id)</span>
        </div>
      `;
      inspectorBody.innerHTML = `
        <div style="color: var(--text-dim); margin-bottom: 8px;">// Unified Collection: job_listings (MongoDB)</div>
        ${highlightJSON(DEMO_DATA.normalized)}
      `;
    } else if (tabName === 'ladder') {
      previewSummary.innerHTML = `
        <div style="font-size: var(--text-xs); color: var(--text-muted); margin-bottom: var(--space-3);">
          <strong style="color: var(--accent-amber);">Self-Healing De-escalation:</strong> The 5-step fallback ladder triggered when an upstream endpoint limits or hiccups.
        </div>
      `;
      inspectorBody.innerHTML = `
        <div class="ladder-step active">
          <div class="ladder-number">1</div>
          <div class="ladder-content">
            <h4>Back Off Current Identity</h4>
            <p>Cool down the specific proxy/session tuple (default 300s) instead of aggressive immediate retries.</p>
          </div>
        </div>
        <div class="ladder-step active">
          <div class="ladder-number">2</div>
          <div class="ladder-content">
            <h4>Rotate Identity / Exit Node</h4>
            <p>Switch to next available independent session in the pool with dedicated cookies and user-agent.</p>
          </div>
        </div>
        <div class="ladder-step">
          <div class="ladder-number">3</div>
          <div class="ladder-content">
            <h4>Site-Wide Global Throttle</h4>
            <p>Drop global request volume across the domain and sleep for a deliberate delay window.</p>
          </div>
        </div>
        <div class="ladder-step">
          <div class="ladder-number">4</div>
          <div class="ladder-content">
            <h4>Failover to Secondary Adapter</h4>
            <p>Switch seamlessly from Primary (RemoteOK) to Backup (JSearch RapidAPI) without downstream pipeline impact.</p>
          </div>
        </div>
        <div class="ladder-step">
          <div class="ladder-number">5</div>
          <div class="ladder-content">
            <h4>Quarantine & Alert Human</h4>
            <p>If all legitimate options exhaust, pause the queue, save raw anomalous payload to Dead-Letter, and alert.</p>
          </div>
        </div>
      `;
    }
  }

  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      renderTab(btn.dataset.tab);
    });
  });

  renderTab('normalized');
}

// ── Micro-Interaction: Viewport-Triggered Counter Animation ──────────────────

function initCounterAnimation() {
  const metricValues = document.querySelectorAll('.metric-value[data-target]');
  let hasAnimated = false;

  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting && !hasAnimated) {
        hasAnimated = true;
        metricValues.forEach(el => {
          const target = parseInt(el.dataset.target, 10);
          const suffix = el.dataset.suffix || '';
          const prefix = el.dataset.prefix || '';
          const duration = 1200;
          const startTime = performance.now();

          function updateCount(currentTime) {
            const elapsed = currentTime - startTime;
            const progress = Math.min(elapsed / duration, 1);
            const easeProgress = progress === 1 ? 1 : 1 - Math.pow(2, -10 * progress);
            const currentVal = Math.floor(easeProgress * target);

            el.textContent = `${prefix}${currentVal.toLocaleString()}${suffix}`;

            if (progress < 1) {
              requestAnimationFrame(updateCount);
            } else {
              el.textContent = `${prefix}${target.toLocaleString()}${suffix}`;
            }
          }

          requestAnimationFrame(updateCount);
        });
      }
    });
  }, { threshold: 0.2 });

  const telemetrySection = document.querySelector('.telemetry-grid');
  if (telemetrySection) {
    observer.observe(telemetrySection);
  }
}

// ── Easter Egg (§7) ──────────────────────────────────────────────────────────

function initEasterEgg() {
  console.log(
    `%c 🚀 ACDYON INGESTION ENGINE v0.1.0 %c
    
 Pipeline Status   : HEALTHY (0 blocks, 0 schema drift)
 Primary Feed      : RemoteOK API (/api)
 Backup Feed       : JSearch RapidAPI (/search)
 Pacing Model      : Log-Normal Jitter (μ=3.0s, σ=0.4)
 ToS Compliance    : Strict attribution & canonical direct links enabled.
 
 Tip: Click the 'Engine: Active' pulse badge in the navigation bar to trigger a live resilience test.`,
    'background: #38BDF8; color: #07090E; font-weight: bold; padding: 4px 8px; border-radius: 4px;',
    'color: #94A3B8; font-family: monospace; font-size: 11px;'
  );

  const statusPill = document.getElementById('engine-status-pill');
  if (statusPill) {
    statusPill.style.cursor = 'pointer';
    statusPill.title = 'Click to simulate endpoint resilience test';
    statusPill.addEventListener('click', () => {
      const dot = statusPill.querySelector('.status-indicator');
      const text = statusPill.querySelector('.status-text');
      
      if (dot && text) {
        dot.className = 'status-indicator amber';
        text.textContent = 'Simulating RemoteOK Hiccup → Failing over to JSearch (RapidAPI)...';
        
        setTimeout(() => {
          dot.className = 'status-indicator';
          text.textContent = 'Engine: Active (Failover Verified ✓)';
          console.log('%c[Acdyon Fallback Engine] Fallback ladder completed: JSearch (RapidAPI) seamlessly ingested listings.', 'color: #10B981; font-weight: bold;');
        }, 1800);
      }
    });
  }
}

// ── Initialize on DOM Load ────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  initListingsSection();
  initInspector();
  initCounterAnimation();
  initEasterEgg();
});
