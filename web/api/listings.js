// Vercel Serverless Function: GET /api/listings
// Proxies directly to the deployed Python FastAPI backend.

export default async function handler(req, res) {
  res.setHeader('Content-Type', 'application/json');
  res.setHeader('Access-Control-Allow-Origin', '*');

  const backendUrl = process.env.VITE_API_BASE_URL || process.env.PYTHON_BACKEND_URL || 'http://localhost:8000';

  try {
    const backendRes = await fetch(`${backendUrl.replace(/\/$/, '')}/api/listings`);
    if (backendRes.ok) {
      const data = await backendRes.json();
      return res.status(200).json(data);
    } else {
      return res.status(backendRes.status).json({ error: 'Backend API error', status: backendRes.status });
    }
  } catch (err) {
    return res.status(502).json({ error: 'Failed to connect to Python backend API', details: err.message });
  }
}
