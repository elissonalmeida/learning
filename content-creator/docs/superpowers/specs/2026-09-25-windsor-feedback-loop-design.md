# Windsor Analytics + Feedback Loop — Design (Spec 4 of 4)

Backlog item #1. Consumed by Spec 1 (evidence and goal baselines) and Spec 2
(next month's plan). Status: **drafted without live review — needs user review before tickets.**

## Purpose

Replace AURA v4's hand-edited static analytics with a real Windsor.ai
integration, and use the numbers to (a) give the Coach real evidence, and
(b) close the loop: what performed last month informs next month's plan.

## Connection (per brand)

- One brand pack = one Instagram profile = one Windsor connection (expansion to other networks is in the backlog).
- **Settings screen**, section "Contas ligadas": status, which Windsor account/profile is used, change account, and a gentle "tudo pronto" confirmation after a successful test.
- API key is a secret → `.env` (`WINDSOR_API_KEY`). The selected account id is stored per brand (brand config), never in code.
- The user already has a working Windsor connector for the profile; the plan must verify the current Windsor REST/connector endpoint, field names and auth against Windsor's docs before implementing.

## Data pulled (v1)

Account: followers, reach, impressions, profile visits, follower change.
Posts: date, format, caption, likes, comments, saves, shares, reach, engagement.
Audience breakdown if available. Cached in SQLite (`analytics_snapshots`, `post_metrics`) with `fetched_at`. A **"Atualizar dados" (Refresh) button** on the Resultados tab pulls fresh data on demand, so mid-month the user sees progress from work already done; the tab always shows "last updated <time>". Refresh is user-triggered (no background polling); repeated clicks in quick succession reuse the just-fetched data.

## Insights (computed, then explained gently)

Pure functions over stored metrics, no AI needed for the maths:
- Performance by pillar, format, funnel phase, CTA type, posting day/time.
- Top and bottom posts, saves/reach and comments/reach rates.
- Month-over-month change against the strategy's goal metrics.
AI is used only to phrase insights kindly and suggest adjustments. Copy
follows the tone rule: "Your educational posts were saved most — a lovely
sign to lean on them" — never "your cosmetics posts failed".

## Feedback loop

1. **Coach evidence:** goal scoring switches evidence from "Reasoned" to "Data" where Windsor supports it (Spec 1).
2. **Monthly review:** at month end the app offers a gentle recap (what worked, what to try next) and proposes strategy tweaks as accept/edit/skip items.
3. **Next plan:** `generate_month` (Spec 2) receives performance by pillar/format as input to weight the mix and pick angles.
4. **Post matching:** metrics are matched to calendar slots/ideas by date + caption so pillar/funnel tags are known per published post (fallback: user marks the slot as published and pastes/selects the post).
5. **Examples for prompts:** top-performing captions can be offered as "what worked for you" examples in draft prompts (opt-in, style only).

## Dashboard (new tab **Resultados**)

A dedicated tab the user can return to any time. Simple, calm view: a few headline numbers, trend arrows, best posts, and the
monthly recap. Uses `theme.py`. Missing data → friendly explanation and how to
connect, never an error wall.

## Modules

`windsor.py` (client: `fetch_account`, `fetch_posts`; injectable HTTP for tests),
`insights.py` (pure maths), `prompts/insight_phrase.md`, Settings + Resultados UI.
Cost: no AI cost for fetching; phrasing calls respect the daily cap and are logged.

## Error handling

Bad key, rate limit, empty data, or network failure → gentle message with next
step, cached data still shown with its date. Never blocks the rest of the app.

## Testing

HTTP fully faked; insights functions with fixed fixtures; slot↔post matching
tests; tone banned-word test; AppTest for Settings and Resultados states
(connected / not connected / stale). **One real end-to-end run against the
user's real Windsor connection** before done.

## Out of scope

Multiple profiles/networks (backlog); autonomous decisions without user approval; paid third-party analytics.

## Decisions taken at review (2026-09-25)

- Windsor data lives in its **own tab** (Resultados) with a manual Refresh button; the monthly recap is a section of that tab.

## Open decisions for review (plan time)

- Which Windsor endpoint/fields (verify at plan time).
- How much history to import first and the short-interval refresh reuse window.
