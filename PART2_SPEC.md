# Part 2 — Premium Home Page
### Build Spec / Handoff Doc

This is a build spec, not the implementation — intended to be handed to
an AI coding tool (or a human) to execute against.

---

## 1. Product

> Fill in before handing off:
> - **Product name:**
> - **One-line pitch (who it's for + what pain it kills):**
> - **Is it real or invented?** If invented, note that it needs a
>   believable pitch but *no fabricated social proof* (see §6).

---

## 2. Goal

First-3-seconds "wow, I want an account" reaction. This is judged on
taste — spacing, type, motion restraint — not feature count. One
sharp idea executed cleanly beats five mediocre ones.

---

## 3. Required sections

### 3.1 Hero
- One clear value prop headline (benefit-led, not a feature list).
- One-sentence subhead expanding on it.
- One primary CTA (e.g. "Get started") + one lower-emphasis secondary
  CTA (e.g. "See how it works").
- Visual: a real product screenshot/mock, or a deliberate abstract/
  gradient composition — not a generic stock photo.

### 3.2 "Show the product" section
- At least one section that *shows* the product working, not just
  describes it: a mock dashboard card, an annotated screenshot, or a
  small interactive demo (e.g. a toggle/tab that swaps a preview panel).
- Sample data inside the mock should look like real product data
  (plausible names, numbers, states) — not "Lorem ipsum" or "Item 1,
  Item 2."

### 3.3 Micro-interaction (exactly one)
Pick one, implement it well, and stop:
- Scroll-triggered reveal on the "show the product" section, **or**
- An animated stat/counter that ticks up once when scrolled into view, **or**
- A hover state on the CTA or a feature card with real spring/easing
  physicality (not just a color swap).

Do not stack multiple motion effects — restraint is explicitly graded.

### 3.4 Responsiveness
- Must work cleanly at **390px** (mobile) and **1440px** (desktop).
- No horizontal scroll at either width — verify explicitly, don't assume.
- Design mobile-first, then expand layout for desktop.

### 3.5 Dark mode — all or nothing
- Either implement full, token-based dark mode (every surface, text,
  border, shadow re-themed consistently) **or** skip dark mode
  entirely.
- Half-dark (a dark hero on an otherwise light page, inconsistent
  contrast) is explicitly called out as worse than not attempting it.

---

## 4. Tech / stack

Whatever ships fastest and looks the most polished. No constraint from
the assessment. Reasonable defaults:
- Static HTML/CSS/vanilla JS for speed and zero build overhead, or
- React (Vite/Next.js) + a motion library (Framer Motion / CSS
  scroll-timeline) if the chosen micro-interaction benefits from it.

Single deliverable either way: a responsive, deployed home page.

---

## 5. Deployment

- Deploy to any free static/host provider: Vercel, Netlify, GitHub
  Pages, Cloudflare Pages.
- Confirm the live URL actually renders correctly at both required
  widths after deploy (not just in local dev).

---

## 6. Hard constraint — the biggest grading factor

**No fabricated testimonials, fake user counts, or fake logos.**

- If there's no real social proof, don't invent any — write specific,
  confident product copy instead (what it does, who it's for, why it's
  different) rather than manufactured trust signals like "Trusted by
  10,000+ teams" or invented quote-and-headshot testimonials.
- This is called out as the single biggest thing graded — treat any
  temptation to add a fake stat or logo strip as a hard no, not a
  judgment call.

---

## 7. Bonus (optional, zero-weighted either way)

Hide one small easter egg — a Konami-code trigger, a hover secret, a
console.log message, an unexpected click target. Skip if time is tight;
it costs nothing to omit.

---

## 8. Definition of done

- [ ] Hero: value prop, subhead, primary + secondary CTA
- [ ] Product-showing section with realistic mock data
- [ ] Exactly one polished micro-interaction
- [ ] Verified no horizontal scroll at 390px and 1440px
- [ ] Dark mode fully implemented or fully absent
- [ ] Zero fabricated testimonials/logos/user counts anywhere on the page
- [ ] Deployed to a live URL and manually re-checked post-deploy
- [ ] (Optional) one easter egg hidden

---

## 9. Feeds into `DECISIONS.md` (shared 1-pager across both parts)

When writing the final decisions doc, pull from this section:
- Which alternative approach you considered and rejected for the layout/
  motion/stack, and why this one won.
- One trade-off made under the time limit (e.g. skipped dark mode, kept
  the interactive demo simpler than planned) and what you'd do with a
  real week.
- Where AI tools were used in building this page, and what you personally
  reviewed, tested, or changed afterward.
