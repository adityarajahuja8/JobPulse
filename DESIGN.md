# Part 1 — Ingestion Design Document
### Getting Job Listings Out of Platforms That Don't Want You To

---

## 0. Demo scope (per the guardrail)

The live demo pulls from **one low-risk, public source** — a job-board
API/RSS feed that explicitly permits programmatic access (e.g. RemoteOK's
public JSON feed, Arbeitnow's public API, or a self-hosted sandbox seeded
with fake listings). No login-walled platform, no LinkedIn/Indeed account,
no ToS violation in the deployed demo. Everything below describes the
*general ingestion architecture* — the parts of it that are demoed live
sit entirely on the legitimate-source path; the parts that describe how
I'd approach a harder, bot-defended target are design-only, for the
follow-up conversation.

---

## 1. Detection surface

What actually gives an automated client away, roughly in the order a
target site checks them:

| Layer | Signal | Notes |
|---|---|---|
| **Network** | Single IP making many requests, IP reputation (datacenter ASN vs residential), TLS/JA3 fingerprint mismatch vs claimed browser | Datacenter IPs (most cloud hosts) are trivially flagged before any page logic runs |
| **TLS/HTTP fingerprint** | Cipher suite order, HTTP/2 frame settings, header order/casing that doesn't match the claimed User-Agent | Most naive `requests`/`axios` clients fail this before content is even served |
| **Browser fingerprint** | `navigator.webdriver`, missing plugins/fonts, canvas/WebGL hash, headless Chrome quirks (permissions API, `chrome.runtime` absence), consistent viewport/timezone/locale combos | Headless-detection libraries (e.g. Cloudflare, PerimeterX, Akamai) fingerprint dozens of these in parallel |
| **Behavioral** | Zero mouse movement, uniform click/scroll timing, no dwell time on a page before the next request, requests hitting endpoints in an order no human would (e.g. hitting page 47 with no referrer from page 46) | The hardest to fake convincingly and the one bot-defense vendors weight most heavily |
| **Session/account** | New account with no history immediately scraping at volume, requests without the auth/session cookies a logged-in browsing session would carry, missing or stale CSRF tokens | Cheap for the platform to check, expensive for a scraper to fully simulate |
| **Rate/pattern over time** | Requests per minute far above human reading speed, perfectly even spacing (a human is never perfectly periodic), 24/7 activity with no day/night pattern | Statistical, not per-request — this is why pacing has to look *irregular*, not just *slow* |

My design accounts for network + TLS + behavioral + rate layers directly
(below). Deep browser-fingerprint evasion (canvas/WebGL spoofing) is the
one layer I'd treat as **out of scope by design** — see §4 — because
defeating it thoroughly is exactly the kind of arms race that burns
accounts and crosses from "resilient ingestion" into "actively defeating
a platform's security controls."

---

## 2. Ingestion strategy

**Core principle: look like N different bored humans, not 1 fast robot.**

- **Identity rotation** — pool of residential/mobile proxy exit nodes
  (not datacenter IPs), each bound to a persistent "identity" (cookie
  jar, session, UA string, locale/timezone) for the life of that
  identity. Identities aren't shared across proxies — mixing a US IP
  with an India-locale cookie jar is itself a fingerprint mismatch.
- **Pacing** — requests per identity are spaced with jittered,
  log-normal delays (not uniform sleep()), capped well under what a
  fast human reader would do, with occasional longer "went and did
  something else" pauses. Total throughput is a sum across many slow
  identities rather than one fast one.
- **Session realism** — each identity actually walks the site the way a
  browser session would: hits the search page before a listing page,
  carries forward referrers, respects (and stores) whatever cookies the
  server sets, doesn't jump straight to deep pagination cold.
- **Fallback ladder when a source starts blocking mid-run:**
  1. Back off that identity entirely (cool-down, not retry-immediately).
  2. Rotate to a fresh identity/proxy for the remaining queue.
  3. Drop request volume site-wide and re-check block status after a
     delay window.
  4. If the source stays blocked, fail over to any secondary/mirror
     source (official API tier, RSS, a partner data provider) rather
     than pushing harder against the block.
  5. If nothing legitimate is left, the job queue for that source pauses
     and alerts a human — it does not silently keep hammering.
- **Plan B if the primary approach gets shut down in a week:** this is
  exactly why the architecture treats scraping as one *replaceable*
  ingestion adapter behind a common interface. If a source clamps down
  hard enough that polite scraping stops being viable, the fallback
  isn't "scrape harder" — it's swapping in whatever legitimate channel
  exists (official/partner API, RSS, aggregator, or manual/CSV import)
  behind the same interface, so downstream consumers of the data don't
  notice the source changed underneath them.

---

## 3. Resilience

Things that will happen, and what keeps the pipeline alive through them:

- **Markup changes overnight** — parsing is never done with brittle
  absolute selectors. Extraction targets are matched by semantic anchors
  (labelled fields, structured data blocks like JSON-LD/`<script
  type="application/ld+json">` where the site has it, stable `data-*`
  attributes) with CSS-path selectors as a secondary fallback. Every
  scrape run diffs its output shape against the last known-good schema;
  a shape mismatch (missing fields, empty required values across a
  sample of listings) fails that run *loudly* into a dead-letter queue
  instead of writing garbage into the dataset.
- **Rate-limited mid-run** — the fallback ladder from §2 kicks in
  automatically: back off → rotate → throttle globally → fail over.
- **Empty/anomalous response** — every response is validated before
  it's trusted: expected content-length range, expected element counts,
  a basic "does this look like a CAPTCHA/block page" check (title,
  known block-page strings, unexpected redirect target). Anomalies get
  retried with backoff a bounded number of times, then routed to the
  dead-letter queue with the raw response saved for debugging — never
  silently dropped, never silently accepted as "zero listings today."
- **Observability** — per-run metrics (success rate, block rate,
  latency, schema-drift count) are logged and alertable, so degradation
  shows up as a dashboard trend before it becomes a total outage.
- **Idempotency** — listings are upserted on a stable dedup key (source
  + external ID), so a retried or partially-failed run can't duplicate
  or corrupt data; a run can always be safely re-attempted.

---

## 4. Where I'd stop

**Personal line:** I won't build or ship something whose main engineering
value is defeating another company's bot-detection/security controls
against their stated terms — e.g. active browser-fingerprint spoofing,
CAPTCHA-solving services, or scraping a platform behind a login using a
throwaway or scraped-credential account. That's a different project than
"resilient data ingestion," and it's the one I'd flag rather than build,
even under a deadline.

**Where the design still respects that line while getting the job done:**

- Prefer the least adversarial legitimate channel available for a source
  — official API > partner/paid data feed > public RSS > polite scraping
  of public, unauthenticated pages that `robots.txt` doesn't disallow >
  (stop; don't proceed further than this).
- Identify as a bot where a platform *allows* automated access with
  identification (custom User-Agent with contact info, honoring
  `robots.txt` and documented rate limits) rather than only ever
  disguising as a human.
- Treat "we got blocked" as a signal to stop and reassess, not an
  obstacle to route around harder — the fallback ladder in §2 explicitly
  de-escalates before it fails over, it doesn't escalate.
- Never scrape data behind authentication using an account that isn't
  ours and explicitly provisioned for this purpose, and never in the
  live demo — which is exactly why the guardrail source is a public
  API/RSS feed.

The technical design (rotation, pacing, resilience) is genuinely useful
on *any* source, including fully legitimate ones with strict rate limits
— it's not solely an anti-detection toolkit, which is part of why I'm
comfortable building and demoing it.
