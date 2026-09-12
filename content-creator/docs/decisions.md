# Decisions & Debugging Log

A running, plain-language record of non-obvious choices, bugs, and what we learned from them. This is meant to be reread later — each entry says what happened, why we chose what we chose, and what it would cost to be wrong. Newest entries at the top.

Format for each entry:

```
## YYYY-MM-DD — Short title

**What:** the choice made, or the bug found.
**Why:** the reasoning, or the root cause.
**Cost if wrong / what to watch for:** what breaks, and how we'd notice.
```

---

## 2026-09-12 — Narrowed the em-dash anti-pattern after it conflicted with the brand's own voice

**What:** Live-tested `generate_draft` on a new topic ("óleo essencial de gerânio para equilíbrio hormonal") before writing any app code, per Task 6. The output used an em-dash for a short clarifying aside ("...pelo nervo olfactivo — a mesma via da lavanda"), which the just-added anti-pattern 13 would have flagged as an AI tell — except the brand's own official `output-examples.md` uses em-dashes exactly that way ("Não é magia — é a regulação do eixo parassimpático."). Narrowed the rule in `anti-patterns.md`, `quality-criteria.md` Critério 11, and the spec appendix: only ban em-dash used as a substitute for a logical connector ("porque"/"mas"/"então") joining two clauses; explicitly allow short apposition/clarification, with the brand's own examples cited as the permitted case.
**Why:** a rule copied from a general-purpose AI-writing guide doesn't automatically fit a specific brand's authentic style — this brand's voice already leans on em-dashes as a stylistic device. Without live-testing the actual prompt against real brand content before locking it into the pipeline, this false positive would have shipped silently and fought the brand voice on every single critique pass.
**Cost if wrong / what to watch for:** if the narrowed rule turns out too permissive (lets real AI-tell em-dash chains through), the tell to watch for is 2+ em-dashes in one sentence/caption doing connector work — a frequency cap is the fallback option that was considered and set aside in favor of this semantic distinction.

---

## 2026-09-12 — AI-slop patterns folded into the brand pack itself, not just a session skill

**What:** Installed the `unslop` skill for this Claude Code session, but also added anti-pattern 13 and quality-criteria Critério 11 directly into the `marianabotelho-ig` brand pack (in the spec's Appendix, since Task 1 hasn't run yet) — em-dash-as-connector, "não só X mas também Y", forced rule of three, empty AI vocabulary, promotional adjectives, filler, generic conclusions.
**Why:** the `unslop` Claude Code skill only improves prose *I* write in this session (docs, commit messages, prompt prototyping). It has no effect on the deployed app, because `ai.py`'s `critique_draft` calls the Claude API directly with only `quality-criteria.md`/`anti-patterns.md` as context — it never sees Claude Code's installed skills. Better text only in this chat and not in Mariana's actual captions would defeat the point.
**Cost if wrong / what to watch for:** if a future brand pack (a second niche) is added, remember to carry equivalent AI-slop checks into its own quality-criteria.md/anti-patterns.md too — they don't come "for free" from the engine code, since brand packs are intentionally self-contained.

---

## 2026-09-12 — GitHub Projects (boards) needs a classic token, not fine-grained

**What:** Authenticated `gh` CLI with a classic personal access token (`repo` + `project` + `read:org` scopes) instead of the fine-grained token created first.
**Why:** GitHub's fine-grained tokens do not support the Projects (v2) API at all as of this writing — the "Projects" permission simply doesn't appear under Account permissions, no matter what's searched for. Issues/PRs work fine with fine-grained tokens; boards currently require a classic token with the `project` scope. `read:org` was also required by `gh auth login` itself for validation, even for a personal (non-org) project.
**Cost if wrong / what to watch for:** if this token expires (90 days) and gets replaced with a fine-grained one again out of habit, board operations (`gh project ...`) will fail with a GraphQL permission error — the fix is always "use a classic token with `project` scope," not "add more repo permissions."

---

## 2026-09-12 — Slides stored as JSON, not a normalized table

**What:** `drafts.slides` is a single JSON column, not a separate `slides` table with one row per slide.
**Why:** v1 never needs to query individual slides (no per-slide analytics, no per-slide editing UI) — normalizing now would be complexity paid for with no current benefit. Chosen deliberately over the DBA-instinct default of "just normalize it."
**Cost if wrong / what to watch for:** if a future feature needs to query/analyze individual slides (e.g. "which slide position gets edited most"), this needs a migration to a normalized `slides` table. No data is lost either way — see the spec's Open Questions section.

---

## 2026-09-12 — Daily spend cap checks *before* the call, using a fixed worst-case estimate

**What:** `pipeline._invoke` blocks a new API call if `today's_logged_spend + ESTIMATED_MAX_CALL_COST_USD (0.20)` would exceed the daily cap — not the call's real cost, which isn't known until the response comes back.
**Why:** the real cost of a call depends on how many tokens the model actually uses, which you can't know before making the call. Using a fixed, conservative per-call estimate as the pre-check is simpler than trying to predict exact token counts, and errs on the side of blocking slightly early rather than overshooting the cap.
**Cost if wrong / what to watch for:** if real calls consistently cost much more than $0.20, the cap could be breached before the pre-check catches it — worth revisiting `ESTIMATED_MAX_CALL_COST_USD` after a few real runs show actual costs in the `api_calls` table.
