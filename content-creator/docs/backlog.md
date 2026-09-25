# Backlog / Wishlist

Deliberately deferred ideas — things we decided NOT to build now, so we don't
lose them and don't accidentally relitigate "should we build this" every time
it comes up. Not a roadmap with dates; just a list to revisit.

---

## Two-stage AI image generation (image + text baked in by AI)

**What:** Instead of generating a background image via AI and overlaying
template text on top (the v1.1 approach), generate the image and then use an
AI editing/inpainting call to add the caption/heading text directly into the
image itself — full automation, no separate templating step.

**Why deferred:** current image-gen models are unreliable at rendering
legible text, especially with Portuguese accents (á, ã, ç, etc.), and doing
this now risks slides that need manual fixing — the opposite of the "no
further edit required" goal. It also roughly doubles the AI calls (and cost)
per slide over the v1.1 approach for a benefit we can't yet realize reliably.

**Revisit when:** image-gen models get noticeably better at multilingual
text rendering, or we want to remove the template-rendering step entirely as
a deliberate simplification once quality across regular generation is solid.

---

## "AURA v2" scope — broken out from the AURA v4 reference

**Reference:** `docs/reference/AURA_v4.html` — a working (client-side only,
localStorage-backed) prototype the user built by hand before this project,
showing the intended UI/UX and feature shape. It called the Anthropic API
directly from the browser for text analysis and listed Gemini (Imagen 3)
and Canva as the tools it expected the user to hand off to for images and
final design. The user described it as a rough first attempt they never
fully finished, with several functionalities that are partly mock/hard-coded
— the vision is real, the implementation wasn't solid, so nothing below
should be copied as-is; each needs its own evaluation of how to actually
build it.

**Why deferred:** Content Creator is being built one deliberate step at a
time (v1: caption/carousel text with quality gates; v1.1: carousel image
generation). Each item below is a substantial feature in its own right and
needs its own brainstorming → spec → plan cycle rather than being folded
into the current image-generation work. Split into separate items (below)
instead of one big blob so each can be picked up, spec'd, and built on its
own — but see **Cross-dependencies** at the end before picking one in
isolation.

**Revisit when:** v1.1 (image generation) is complete and stable.

---

### 1. Windsor.ai — real analytics integration

**What:** A real, working Windsor.ai API integration for Instagram/social
analytics (followers, reach, engagement, top posts, audience breakdown) —
replacing AURA v4's `WINDSOR` object, which is a static JSON blob the user
had to update by hand, not a live integration.

**Why:** User confirmed this is something they're keen to get working for
real this time, not mocked.

**Reinforced by OpenSquad:** The `marianabotelho-content-ig` squad (a
separate, already-running multi-agent pipeline for this same brand) has
this exact gap on its own future-ideas list — a "read published-post
metrics weekly and feed the patterns back into angle/ideation decisions"
agent, currently blocked on analytics integration. Worth treating
Windsor.ai not just as a dashboard data source but as a feedback loop
into content decisions (e.g. "what pillar/angle performed best last
month" informing the next ideation pass) — see item #2 below.

### 2. Calendar

**What:** Monthly content calendar — scheduling posts, assigning
funnel-phase/pillar/status per post. User confirmed the calendar concept
itself is good and wants to build it incrementally.

**Note:** AURA v4 has two `calHTML` definitions; the second (simpler,
list-only) silently overrides the first (richer month-grid with day badges
and a grid/list toggle), so the grid view is actually dead code in the
reference. Worth deciding fresh what the real calendar UI should be rather
than assuming the reference's grid view is a working design to copy.

**Reinforced by OpenSquad:** The same squad's monthly-planning step
(run once/month, separately from the daily pipeline) adds concrete details
worth folding into this: a theme-of-the-month, a *quarterly* featured-product
rotation, a hard cap on product-heavy posts per month (max 2/month in their
case), and a per-month "north-star metric" the plan is optimized against —
on top of the pillar-percentage/funnel-phase model already listed in item #5.

### 3. Design system / look-and-feel spec doc

**What:** A spec doc for the shared visual language — colors, layout,
typography, "disposition" — so the content-creator project's interface
matches AURA v4's look and feel.

**Why:** User wants visual continuity with the reference prototype's UI,
not just its functionality.

**Reinforced by OpenSquad:** The `website-builder` squad's "Brand Wizard"
agent is a concrete pattern for *how* to actually produce this spec:
an interview-driven flow that asks one question at a time, proposes 3
color-palette options + 2 typography pairings + voice/tone examples, and
requires explicit approval before writing the final brand-kit file (colors
with hex/RGB/usage notes, typography, voice, design references). Worth
reusing this "propose options → get approval → lock the spec" shape instead
of writing the design doc in one shot.

### 4. Stories module

**What:** A dedicated Stories feature — generating a daily sequence of
Stories ideas (AURA v4's version: 7 stories per day, ~80/15/5 split between
connection/education/offer). Called out by the user as its own backlog
item, distinct from Carousel, because the right approach for Stories is
believed to be different from how Carousel content gets built.

### 5. Notable content-model patterns, applied to content-creator

**What:** These aren't standalone features — they're modeling patterns
from AURA v4 worth carrying into the new project's data model:
- Funnel-phase tagging (e.g. reativação / consistência / conversão) per
  post, mapped across the month.
- Content-pillar percentage allocation (validated to sum to 100%).
- Keyword-based CTA taxonomy, categorized by content type (services /
  education / community / products) — implies comment-keyword-to-DM
  automation downstream.
- Niche-specific trend/event calendar overlay (e.g. moon phases,
  holidays, seasonal moments) as a content-idea generator.
- Post status pipeline (e.g. Pending → In Production → Ready →
  Published) — content-creator already has a working version of this
  (`idea → reviewed → approved/rejected → images_ready → archived` in
  `db.py`); this item is about reconciling/extending it (e.g. adding a
  `Published` state once auto-publish (#9) exists), not building one
  from scratch.
- Export-everything-to-Markdown pattern (single post / full month / whole
  brand context) — same shape as AURA v4's "Claude Project" export
  (`perfil.md`, `servicos.md`, `estrategia.md`, `instrucoes.md`).

**Why:** These need their own decision on how (or whether) each applies to
content-creator's actual data model — not a one-to-one port.

---

**Cross-dependencies — which items can't be picked in isolation:**

- **Design system (#3) should land before or alongside whichever UI
  feature gets built first** (Calendar or Stories). Building either one
  without it risks a restyle later once the design doc exists.
- **Calendar (#2) + funnel-phase tagging, pillar %, status pipeline, and
  the trend/event overlay (all part of #5) are one tightly coupled
  cluster.** They all live on the same post/calendar data model — build
  them together rather than picking, say, "status pipeline" alone.
- **Stories (#4) depends on Calendar's daily context** (today's date,
  scheduled post, trend/event overlay) to know what to generate stories
  about — build it after or alongside Calendar, not before.
- **Windsor.ai (#1) is independently buildable**, but its main payoff is
  feeding Dashboard analytics and "what performed well" examples into AI
  prompts — most valuable once a Dashboard/analytics view exists to
  consume it.
- **Keyword-CTA taxonomy and export-to-Markdown (both part of #5) are the
  two loosely-coupled pieces** — each attaches to the per-post model
  independently and can be picked up anytime once posts exist, without
  waiting on the Calendar cluster.

---

## North-star vision — autonomous social media marketing agent

**What:** The long-term goal behind this project: a full social-media
marketing agent that handles marketing for a brand's social profiles
end-to-end — content, engagement/growth tactics, and converting leads
into actual clients — not just a content-drafting tool.

**Why deferred:** Explicitly a big, later goal. The plan is to start from
scratch and small, one feature at a time — everything in the "AURA v2"
section above is a building block toward this, not the end state itself.

**Revisit when:** Enough building blocks exist (calendar, stories,
analytics, CTA/lead patterns) that stitching them into an agentic,
autonomous layer becomes a realistic next step — worth its own
brainstorming session once that point is reached, since "agent" implies
decisions about autonomy, guardrails, and what it's allowed to do without
a human approving each action.

**Adjacent ideas seen elsewhere (not scoped in, just noted for later):**
- A self-auditing meta-agent (OpenSquad's "Nova" does this for its own
  squad) that periodically reviews the tool's own capabilities against
  new AI/MCP tools and proposes upgrades — a possible mechanism for
  keeping an eventual agentic layer current without manual re-review.
- A companion website-generation capability (OpenSquad's
  `website-builder` squad turns an approved brand-kit into a static
  site) — tangential to a *social-media* agent, but the same brand-kit
  driving both social content and a website is consistent with "full
  marketing agent." Not scoped in; just worth remembering it exists.

## Multiple social profiles per brand

**What:** For now one brand pack = one Instagram profile (one Windsor.ai
connection per brand). Later, a brand could connect several profiles or
other networks (TikTok, LinkedIn, YouTube, etc.), each with its own
analytics connection.

**Why deferred:** Keeps the first calendar/strategy/Windsor specs simple.
Design the per-brand connection setting so it can grow into a list later.

---

## Paid scraping services for Sherlock (e.g. Apify)

**What:** Pay-per-use scraping services (cents per profile) that handle
platform blocking for Instagram/TikTok. They would sit in the middle of
Sherlock's fallback chain, before the dummy-account crawl.

**Why deferred:** User does not want additional paid services for now.
Sherlock's first version uses only free sources: website fetch, official
Instagram Business Discovery API, yt-dlp/whisper, dummy-account crawl, and
guided upload. If a paid tier is added later, show the estimated cost first
(same pattern as the daily spend cap).

---

## In-app usage menus / help per feature

**What:** Menus or help screens inside the app itself explaining how to
use each functionality, rather than relying on external docs the user has
to remember to go re-read.

**Why deferred:** Only makes sense once there's more than one or two
modules to document — grows incrementally alongside each feature as it
ships rather than being built upfront for features that don't exist yet.

## App kickoff / getting-started flow

**What:** A clear, defined way to start the application itself — e.g. one
obvious entry point to run it, and/or a first-run setup flow (brand
profile, connecting Windsor.ai, etc.) instead of assuming whoever's
starting it already knows the internals.

**Why deferred:** Same reasoning as the menus above — becomes worth
designing once there's a real set of modules and config steps to walk
someone through, not before.

---

## New ideas sourced from OpenSquad

**Context:** OpenSquad (`C:\Users\Elisson\Documents\Aura\opensquad`) is a
separate, already-running multi-agent framework. Its `marianabotelho-content-ig`
squad runs a real, in-production 11-agent pipeline for this *same* Instagram
brand, and its `website-builder` squad has an adjacent brand-kit/site
pipeline. These are genuinely new capabilities/ideas not already covered
above (enrichments to existing items were folded into items #1–#3 instead
of listed here).

### 6. Competitor / reference-profile research ("Sherlock")

**What:** The capability the user specifically remembered — give it a
profile URL or handle (Instagram, LinkedIn, Twitter/X, YouTube, or a
generic website) and it extracts real content (captions, transcripts,
metrics) and derives a pattern-analysis: content mix, hook/CTA/structural
patterns, vocabulary, engagement drivers, and concrete recommendations.

**How OpenSquad does it:** Browser automation (Playwright) with persisted
per-platform login sessions; video content is transcribed via
`yt-dlp` + `whisper`. Output is a `raw-content.md` + `pattern-analysis.md`
per profile, consolidated across multiple profiles into one synthesized
framework (hook/CTA templates, anti-patterns).

**Note:** content-creator already depends on Playwright (`render.py`
uses it to screenshot HTML slides into PNGs), so the core
browser-automation dependency is already proven to work in this exact
environment — lowering this item's risk somewhat. Persisted-login
profile scraping is still a different usage mode (interactive session
state vs. static content rendering) and would need its own evaluation.

**Why it matters for content-creator:** This maps directly onto pieces
content-creator already has per-brand (`anti-patterns.md`,
`quality-criteria.md`, `tone-of-voice.md`, `output-examples.md` per the
`marianabotelho-ig` brand pack) — instead of hand-authoring those from
scratch, this is a way to *derive* them from real accounts (competitors,
inspiration profiles, or the brand's own historical top posts).

### 7. Angle ideation step (generate several angles, then pick one)

**What:** Before drafting full copy, generate several distinct content
angles for the day's theme (hook, format, pillar, objective, estimated
save-potential) and have a human pick/adjust one — rather than drafting
straight from a topic to a single finished draft.

**Why it matters:** content-creator's current pipeline (`generate_draft` →
`critique_draft`) goes straight from topic to one draft. An explicit
ideation/angle-selection step adds a cheap human checkpoint earlier, before
investing a full draft+critique cycle in a direction the user doesn't want.

### 8. Multiple specialized review passes instead of one general critique

**What:** Instead of a single `critique_draft` checking everything at
once, run several narrower review passes in parallel, each with its own
explicit veto conditions — e.g. scientific/claims accuracy, editorial
voice/language compliance, commercial/CTA-funnel alignment, product/
ingredient-claim compliance (OpenSquad's squad runs exactly these four,
by four different specialized reviewer agents).

**Why it matters:** `docs/decisions.md` already shows quality-criteria.md
growing more criteria over time as new gaps get found (e.g. Critério 6's
vagueness fix) — splitting one large, growing checklist into several
focused reviewers with clear pass/fail authority in their own lane could
be more reliable than one prompt trying to catch everything at once, and
easier to reason about when a draft fails.

### 9. Auto-publish integration

**What:** Actually posting approved content to Instagram (and potentially
other platforms) instead of stopping at "approved draft." Two concrete
approaches exist as prior art:
- **Direct Instagram Graph API** (OpenSquad's `instagram-publisher`
  skill: image hosting via imgBB + Graph API, dry-run supported,
  Instagram-only).
- **Multi-platform publishing API (Blotato)**: one integration covering
  Instagram, LinkedIn, X, TikTok, YouTube — publish or schedule, with
  media upload and status polling.

**Why it matters / caveat:** Notably, OpenSquad itself has *not* wired
either of these into its live pipeline yet (flagged as a gap in its own
audit and future-ideas notes) — so this is a real, unsolved problem even
in the more mature reference system, not just a content-creator gap.

### 10. External-source content mode (news/URL → post)

**What:** A content-generation mode seeded by an external source (a news
article or URL) rather than only from internal ideation/theme-of-the-day —
inferred from an unfinished OpenSquad scaffold (`carrossel-news-cc`:
Researcher → Copywriter → Image Designer → Reviewer → Publisher desks,
paused mid-pipeline, no actual agent files built yet). Speculative/low
-confidence signal — worth remembering as an idea, not a validated pattern,
since that squad was never actually built out.

**Note:** technically smaller than it sounds — content-creator already
has a "Texto de referência" mode that feeds arbitrary pasted text into
`extract_topics` (see `app.py`); this item would mainly need a
fetch-URL-and-extract-text step in front of that existing flow, not a
new pipeline. The speculative part is whether the product idea is worth
building, not whether the plumbing is hard.

---

**Dependency/bundling notes for the new items:**

- **Angle ideation (#7) and multi-pass review (#8) both extend the
  existing draft/critique pipeline** — natural to design together rather
  than separately, since both touch the same generate → review → approve
  flow.
- **Sherlock-style research (#6) is independently useful** (can run
  standalone against any profile) but its highest-value use is feeding
  the brand-pack files (`anti-patterns.md`, `tone-of-voice.md`,
  `quality-criteria.md`) that items #7/#8 depend on — logically upstream
  of them, not blocking them.
- **Auto-publish (#9) is the natural endpoint of the whole pipeline** —
  low priority until the content pipeline itself (drafting, review,
  calendar/scheduling) is solid, since publishing something wrong faster
  isn't the goal.
- **External-source mode (#10) is the most speculative item** — treat as
  a "someday, if it comes up" note rather than a real candidate until
  there's a concrete reason to seed content from outside sources.

---

## Low-friction daily workflow — ideas sourced from CoworkOS

**Context:** CoworkOS (bettercreating.com, a paid template for Claude
Desktop's Cowork tab) is a generic personal-assistant layer: onboarding
interview, scheduled briefings, a memory file that updates from
corrections. It isn't content-specific and isn't worth buying for Aura, but
its ideas fit the goal of making content creation low-friction for people
to whom it doesn't come naturally. Aura can do them better because it
already knows the brand pack, the calendar, and (eventually) the results.

### 11. Morning brief inside Aura

**What:** A daily "today" view: the post planned for today, what's still
due, and yesterday's result, in a short, comforting summary.

**Depends on:** Calendar (#2) for what's planned; Windsor results (#1) for
yesterday's numbers. Works with partial data (calendar only) at first.

### 12. Guided daily flow (checklist so no step is missed)

**What:** Today's steps as a checklist (idea → draft → review → approve →
publish) that shows where you left off and lets you go back and refine.

**Note:** Close to the calendar-post link spec; design together with #11.

### 13. Onboarding coach (first-run interview)

**What:** A conversational first-run interview that fills in the brand pack
(tone, audience, anti-patterns) instead of hand-authoring the files.

**Note:** Overlaps the "App kickoff / getting-started flow" item and the
Brand Wizard pattern in #3. Treat as one design, not three.

### 14. Memory of corrections

**What:** When the user edits a draft, Aura records the preference (e.g.
"always shorten the opener") and applies it to future drafts, with a way to
review and remove what it has learned.

**Why it matters:** Probably the highest-value idea here. It complements
`quality-criteria.md` (which encodes rules by hand) with rules learned from
real edits. Needs a storage design (per brand) and a guard against learning
one-off edits as permanent rules.

**Bundling:** #11 and #12 belong together. #13 belongs with the kickoff
item. #14 stands alone but pairs with #8 (review passes).

---

## Deferred from calendar-cluster spec review

- **Dummy-account crawl for Sherlock** (secondary account with a saved
  Playwright login; opt-in, slow read-only pacing). Deferred; v1 uses
  website fetch, Instagram Business Discovery, yt-dlp/whisper, guided upload.
- **Calendar month-grid view.** v1 is a list view.
- **Markdown export of a month/plan** (part of #5). Benefit unclear for now.
- **Bulk "create all posts" from the calendar.** Image creation isn't
  polished yet; v1 is one post per slot.
