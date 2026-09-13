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

## Full "AURA" functionality (calendar, ads, stories, analytics, per-profile config)

**What:** A much bigger vision beyond carousel drafting + image generation:
a monthly content calendar, Reels/Stories planning, ad-budget tracking,
Instagram analytics (via Windsor.ai or similar), and a full editable
brand-profile config (audience, tone, services, products, CTAs) — all as
one integrated tool.

**Reference:** `docs/reference/AURA_v4.html` — a working (client-side only,
localStorage-backed) prototype the user built by hand before this project,
showing the intended UI/UX and feature shape. It called the Anthropic API
directly from the browser for text analysis and listed Gemini (Imagen 3)
and Canva as the tools it expected the user to hand off to for images and
final design. The user described it as a rough first attempt with some
hard-coded/fake "AI-generated" responses — the vision is real, the
implementation wasn't solid.

**Why deferred:** Content Creator is being built one deliberate step at a
time (v1: caption/carousel text with quality gates; v1.1: carousel image
generation). Calendar/ads/analytics/stories are each substantial features
in their own right and would need their own brainstorming → spec → plan
cycle rather than being folded into the current image-generation work.

**Revisit when:** v1.1 (image generation) is complete and stable — treat
this as the likely "Content Creator v2" scope, to be broken into its own
sub-projects (e.g. calendar first, then analytics, then ads) rather than
tackled as one big spec.
