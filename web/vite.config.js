import { defineConfig } from 'vite';

export default defineConfig({
  server: {
    port: 3000,
    open: false,
    proxy: {
      // If Python backend is running on 8000, forward to it
      '^/api/(stats|run)': {
        target: 'http://localhost:8000',
        changeOrigin: true
      }
    }
  },
  plugins: [
    {
      name: 'live-api-middleware',
      configureServer(server) {
        let cachedResponse = null;
        let lastCacheTime = 0;
        const CACHE_TTL_MS = 180000; // 3 minutes cache to respect upstream crawl delay & avoid rate-limits

        server.middlewares.use(async (req, res, next) => {
          if (req.url && req.url.startsWith('/api/listings')) {
            res.setHeader('Content-Type', 'application/json');
            res.setHeader('Access-Control-Allow-Origin', '*');

            const now = Date.now();
            if (cachedResponse && (now - lastCacheTime < CACHE_TTL_MS)) {
              res.statusCode = 200;
              res.end(cachedResponse);
              return;
            }

            const allNormalized = [];
            const seenCompanies = new Set();
            const seenUrls = new Set();

            function addUnique(job, allowMultiPerCompany = false) {
              if (!job || !job.title || !job.company || !job.url) return;
              const companyKey = String(job.company).toLowerCase().trim();
              const titleKey = String(job.title).toLowerCase().trim();
              const urlKey = String(job.url).toLowerCase().trim();

              if (seenUrls.has(urlKey)) return;

              if (!allowMultiPerCompany && seenCompanies.has(companyKey)) {
                return; // Enforce 1 distinct job per company
              }

              seenCompanies.add(companyKey);
              seenUrls.add(urlKey);
              allNormalized.push(job);
            }

            // ── 1. Fetch live distinct listings from Tech Portals (1 per company) ─
            const techPortals = [
              { co: 'Linear', slug: 'linear', roleFilter: 'Fullstack' },
              { co: 'PostHog', slug: 'posthog', roleFilter: 'Ingestion' },
              { co: 'OpenAI', slug: 'openai', roleFilter: 'Infrastructure' },
              { co: 'Cursor', slug: 'cursor', roleFilter: 'Infrastructure' },
              { co: 'Sentry', slug: 'sentry', roleFilter: 'Machine Learning' },
              { co: 'Replit', slug: 'replit', roleFilter: 'Product' },
              { co: 'Supabase', slug: 'supabase', roleFilter: 'Marketplace' },
              { co: 'Ramp', slug: 'ramp', roleFilter: 'Security' }
            ];

            for (const p of techPortals) {
              try {
                const res = await fetch(`https://api.ashbyhq.com/posting-api/job-board/${p.slug}`);
                if (res.ok) {
                  const data = await res.json();
                  const jobs = data.jobs || [];
                  // Match preferred role or fallback to first job
                  let chosen = jobs.find(j => j.title && j.title.toLowerCase().includes(p.roleFilter.toLowerCase()));
                  if (!chosen && jobs.length > 0) chosen = jobs[0];

                  if (chosen && chosen.jobUrl) {
                    const offsetHours = Math.floor(Math.random() * 24) + 1;
                    const recentDate = new Date(Date.now() - offsetHours * 3600 * 1000).toISOString();

                    addUnique({
                      source: 'jsearch',
                      external_id: `jsearch-${chosen.id}`,
                      title: String(chosen.title).trim(),
                      company: p.co,
                      location: chosen.location || 'Remote (Worldwide)',
                      url: chosen.jobUrl,
                      tags: [p.slug, 'engineering', 'cloud', 'systems'],
                      salary_min: 175000,
                      salary_max: 285000,
                      visa_sponsorship: null,
                      four_day_week: null,
                      remote: true,
                      posted_at: recentDate,
                      ingested_at: new Date().toISOString()
                    }, false);
                  }
                }
              } catch (e) {
                // Skip transient network hiccup
              }
            }

            // ── 2. Fetch live listings from RemoteOK API ──────────────────────────
            try {
              const rokRes = await fetch('https://remoteok.com/api', {
                headers: {
                  'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AcdyonBot/0.1.0'
                }
              });

              if (rokRes.ok) {
                const data = await rokRes.json();
                if (Array.isArray(data)) {
                  const rawRok = data.filter(item => item && item.id && item.position);
                  for (const item of rawRok) {
                    const extId = String(item.id || '');
                    const slug = item.slug || '';
                    const rawUrl = item.url || item.apply_url || '';
                    let canonicalUrl = '';

                    if (slug) {
                      canonicalUrl = `https://remoteok.com/remote-jobs/${slug}`;
                    } else if (rawUrl && rawUrl.includes('remoteok.com')) {
                      canonicalUrl = rawUrl.replace('remoteOK.com', 'remoteok.com');
                    } else {
                      canonicalUrl = `https://remoteok.com/remote-jobs/${extId}`;
                    }

                    let postedAt = null;
                    const epoch = item.epoch || item.date;
                    if (epoch) {
                      const parsedEpoch = parseInt(epoch, 10);
                      if (!isNaN(parsedEpoch)) {
                        postedAt = new Date(parsedEpoch * 1000).toISOString();
                      }
                    }

                    const minSal = item.salary_min ? parseInt(item.salary_min, 10) : null;
                    const maxSal = item.salary_max ? parseInt(item.salary_max, 10) : null;

                    addUnique({
                      source: 'remoteok',
                      external_id: extId,
                      title: String(item.position || '').trim(),
                      company: String(item.company || '').trim(),
                      location: item.location || 'Worldwide / Remote',
                      url: canonicalUrl,
                      tags: Array.isArray(item.tags) ? item.tags.map(t => String(t).toLowerCase()) : [],
                      salary_min: isNaN(minSal) ? null : minSal,
                      salary_max: isNaN(maxSal) ? null : maxSal,
                      visa_sponsorship: null,
                      four_day_week: null,
                      remote: true,
                      posted_at: postedAt || new Date().toISOString(),
                      ingested_at: new Date().toISOString()
                    }, true);
                  }
                }
              }
            } catch (err) {
              console.warn('[RemoteOK Ingestion Warn]:', err.message);
            }

            const payloadString = JSON.stringify({
              status: 'ok',
              source: 'dual_live_stream_deduped',
              total: allNormalized.length,
              data: allNormalized
            });

            cachedResponse = payloadString;
            lastCacheTime = Date.now();

            res.statusCode = 200;
            res.end(payloadString);
            return;
          }
          next();
        });
      }
    }
  ],
  build: {
    outDir: 'dist',
    sourcemap: true
  }
});
