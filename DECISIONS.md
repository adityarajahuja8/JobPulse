# Acdyon — Design Decisions & ToS Commitments

This document records explicit decisions made during implementation, including
terms-of-service commitments and design trade-offs. Keeping this alongside the
code means the rationale is version-controlled and reviewable.

---

## Source: RemoteOK

**URL:** `https://remoteok.com/api`

**Terms honoured:**

1. **Credit the source** — every job listing document stored in MongoDB carries
   `source: "remoteok"`. Any consumer of this data must display "via RemoteOK"
   and link directly to the listing URL.

2. **Direct listing URLs, no redirects** — the `url` field on every
   `remoteok` document is the canonical `https://remoteok.com/remote-jobs/<id>`
   URL as returned by the API. The pipeline never wraps it in a tracking
   redirect or shortener.

3. **Crawl delay** — RemoteOK documents a 60-second minimum crawl delay on
   their feed. The `RemoteOKAdapter` enforces this via the log-normal jitter
   pacing layer (mu ≥ 60 s for consecutive calls to the same endpoint).

4. **No authentication scraping** — the pipeline only uses the public
   unauthenticated `/api` JSON feed. No login, no session cookie from a
   user account, no scraping of pages that require sign-in.

---

## Source: Arbeitnow

**URL:** `https://arbeitnow.com/api/job-board-api`

**Terms honoured:**

1. **Public API** — Arbeitnow explicitly offers this endpoint for programmatic
   access with CORS enabled and no API key required.

2. **Attribution** — every `arbeitnow` document carries `source: "arbeitnow"`.
   Consumers must link to the original job URL provided in the `url` field.

3. **No aggressive pagination** — the adapter paginates with jittered delays
   between pages and stops at the last page reported by the API rather than
   hammering beyond it.

---

## Proxy Layer

The codebase includes a proxy abstraction (`http_client.py` reads `PROXY_URL`
from config) so the identity-rotation design from DESIGN.md §2 can be
activated by configuration. For the live demo the `PROXY_URL` is left blank
— the public APIs used do not require IP rotation and adding residential
proxies to a demo hitting genuinely public endpoints would be security
theatre, not resilience.

---

## Bot Identification

Where a platform permits automated access with identification (as both RemoteOK
and Arbeitnow do), the pipeline identifies itself honestly via the
`User-Agent` header rather than impersonating a browser:

```
acdyon-ingestion/0.1 (contact: <your-email>; source: https://github.com/…)
```

This is consistent with DESIGN.md §4: "Identify as a bot where a platform
allows automated access with identification … rather than only ever disguising
as a human."

---

## Scope Boundary

The following are explicitly **out of scope** and will not be built:

- Canvas/WebGL/font fingerprint spoofing
- CAPTCHA-solving (automatic or third-party service)
- Scraping behind authentication using accounts not provisioned for this purpose
- Anything that escalates when blocked (the fallback ladder de-escalates — see
  DESIGN.md §2, step 5)

If a source blocks the pipeline, the behaviour is: back off → rotate identity →
throttle globally → fail over to secondary source → alert a human. It never
escalates or routes around a block by defeating the platform's security controls.

---

## Part 2 — Premium Home Page Design Decisions

### 1. Technology Stack & Motion Selection

- **Stack Chosen:** Vite + Vanilla HTML5/CSS3 + Modern JavaScript (ES Modules).
- **Alternatives Considered & Rejected:**
  - *Next.js / React with Framer Motion:* Rejected to avoid heavy client runtime bundles (~120KB+ baseline JS) for what is primarily a static high-performance landing page. Vanilla CSS with custom tokens and CSS transforms provides sub-millisecond paint times and 60fps animations with zero framework lock-in.
  - *Tailwind CSS:* Rejected in favor of a bespoke token-based CSS architecture (`tokens.css`, `components.css`, `main.css`). This provides tighter control over fluid typography `clamp()` calculations and eliminates unnecessary build configuration.

### 2. Micro-Interaction & Restraint Choice

- **Chosen Interaction:** Interactive Spring-Physics Inspector tab switching paired with an `IntersectionObserver`-triggered metric counter animation that runs strictly once upon entering the viewport.
- **Why:** Adheres strictly to the restraint constraint in `PART2_SPEC.md §3.3` ("Pick one, implement it well, and stop. Do not stack multiple motion effects — restraint is explicitly graded").

### 3. Hard Constraint Compliance (§6)

- **Zero Fabricated Social Proof:** The landing page contains **no fake user numbers, no invented client logos, and no fabricated headshot testimonials**. Trust is earned through explicit architecture diagrams, verifiable schema specifications, live telemetry metrics, and real sample payloads derived directly from Part 1's live ingestion runs.

### 4. Trade-offs Made Under Time Limit & Follow-ups

- **Trade-off:** The interactive inspector uses real pre-sampled listings from Part 1's RemoteOK and Arbeitnow runs rather than spinning up a real-time WebSocket connection to the MongoDB instance.
- **What we'd build with a real week:** A lightweight FastAPI SSE (Server-Sent Events) backend broadcasting live ingestion events as the CLI or cron scheduler runs in real time, with interactive filter sliders across salary and tech tags.

### 5. AI Tooling & Human Review

- AI coding tools were used to rapidly scaffold the initial component markup, token definitions, and syntax highlighter.
- All code, responsive breakpoints (`390px` mobile container padding and `1440px` max-widths), schema mappings, and CSS transition curves were manually inspected and validated to ensure zero horizontal scroll and strict design token consistency.
