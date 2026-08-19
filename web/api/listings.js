// Vercel Serverless Function: GET /api/listings

export default async function handler(req, res) {
  res.setHeader('Content-Type', 'application/json');
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Cache-Control', 's-maxage=180, stale-while-revalidate');

  const allNormalized = [];
  const seenUrls = new Set();
  const seenExternalIds = new Set();

  function addUnique(job) {
    if (!job || !job.title || !job.company || !job.url) return;
    const extKey = `${job.source}-${job.external_id}`;
    const urlKey = String(job.url).toLowerCase().trim();

    if (seenUrls.has(urlKey) || seenExternalIds.has(extKey)) return;

    seenExternalIds.add(extKey);
    seenUrls.add(urlKey);
    allNormalized.push(job);
  }

  // 1. Fetch live listings from JSearch RapidAPI /search-v2
  try {
    const rapidKey = process.env.RAPIDAPI_KEY || 'e50277eb37msh360b11bca7c1866p1ca014jsn36fef6c35f06';
    const jsRes = await fetch('https://jsearch.p.rapidapi.com/search-v2?query=Software%20Engineer&country=us&date_posted=all', {
      headers: {
        'x-rapidapi-key': rapidKey,
        'x-rapidapi-host': 'jsearch.p.rapidapi.com',
        'Content-Type': 'application/json'
      }
    });

    if (jsRes.ok) {
      const jsPayload = await jsRes.json();
      const dataObj = jsPayload.data;
      const jobs = Array.isArray(dataObj) ? dataObj : (dataObj && Array.isArray(dataObj.jobs) ? dataObj.jobs : []);

      for (const item of jobs) {
        const extId = String(item.job_id || '');
        if (!extId) continue;

        const loc = item.job_location || item.job_city || (item.job_country ? item.job_country.toUpperCase() : 'Remote');
        const tags = [];
        if (Array.isArray(item.job_required_skills)) {
          tags.push(...item.job_required_skills.map(s => String(s).toLowerCase()));
        }
        if (item.job_employment_type) {
          tags.push(String(item.job_employment_type).toLowerCase());
        }

        addUnique({
          source: 'jsearch',
          external_id: extId,
          title: String(item.job_title || '').trim(),
          company: String(item.employer_name || '').trim(),
          location: loc,
          url: String(item.job_apply_link || '').trim(),
          tags: tags.slice(0, 6),
          salary_min: typeof item.job_min_salary === 'number' ? item.job_min_salary : null,
          salary_max: typeof item.job_max_salary === 'number' ? item.job_max_salary : null,
          visa_sponsorship: null,
          four_day_week: null,
          remote: Boolean(item.job_is_remote),
          posted_at: item.job_posted_at_datetime_utc || new Date().toISOString(),
          ingested_at: new Date().toISOString()
        });
      }
    }
  } catch (jsErr) {
    console.warn('[JSearch Live Ingestion Warning]:', jsErr.message);
  }

  // 2. Fetch live listings from RemoteOK API
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
          });
        }
      }
    }
  } catch (err) {
    console.warn('[RemoteOK Ingestion Warn]:', err.message);
  }

  res.status(200).json({
    status: 'ok',
    source: 'vercel_serverless_stream',
    total: allNormalized.length,
    data: allNormalized
  });
}
