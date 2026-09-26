# Final whole-branch review: strategy-coach (#16, #17, #18, #19, #20, #23 + hardening), as merged into main

Reviewed at `main` 54ed84e (detached worktree `learning-worktrees/review-main`). Read-only review, done in one pass by one reviewer.

Scope read in full: `tone_guard.py`, `coach_store.py`, `scoring.py`, `prompts/score_goals.md`, `sherlock/models.py`, `sherlock/gather.py`, `requirements.txt`, `.env.example`, and tests `test_tone_guard.py`, `test_coach_store.py`, `test_scoring.py`, `test_sherlock_website.py`, `test_sherlock_video.py`, `test_sherlock_instagram.py`. Context: spec `2026-09-25-strategy-coach-design.md`, plan Tasks 1-10 (interfaces of 6, 7, 9, 10 checked against the built code), `docs/superpowers/HANDOFF.md`, `ai.py`, `pipeline.py`, `db.py`, `config.py`, `run.bat`.

## Verification run

- `venv\Scripts\python.exe -m pytest -q` from `content-creator/`: **171 passed**, 1 warning (google-genai deprecation, unrelated).
- `import tone_guard, coach_store, scoring, sherlock.models, sherlock.gather` in the app venv (Python 3.14.5): **OK**.
- `pip show yt-dlp` in the app venv: **not installed**. No `yt-dlp` on PATH either. `pip download yt-dlp` resolves `yt_dlp-2026.8.19-py3-none-any.whl` (pure Python), so `run.bat`'s `pip install -r requirements.txt` will install it on the next launch. `whisper` is not installed (optional, as documented).
- Tone sweep: ran `tone_guard.find_harsh_words` over all 290 string constants in the six scoped files plus `prompts/score_goals.md`. The only hits are in `tone_guard.py` itself (the banned-word list and the `GENTLE_TONE_RULE` text, which names the banned words as things to avoid; expected). All canned user-facing copy in `sherlock/` and `scoring.py` is clean.
- Argument-injection probe: `detect_platform("--exec=calc.youtube.com")` returns `"youtube"` and `detect_platform("--config-locations=x.tiktok.com")` returns `"tiktok"`. Running the real yt-dlp (from the downloaded wheel) with `--dump-single-json --skip-download --exec=calc.youtube.com` gives `error: You must provide at least one URL`, so yt-dlp reads that "URL" as an option.

## Strengths

- **Consistent result types.** Every gatherer returns `GatherResult | NeedsUpload` and never raises for network or tool failures. Website and Instagram failures use fixed PT-PT reasons, and tests check that raw exception text (including a fake token) doesn't leak into `reason` (`test_discovery_needs_upload_on_api_error_with_fixed_reason`, `test_gather_website_returns_needs_upload_on_fetch_error`).
- **Hostname-based platform detection** (`_host_is`) instead of substring matching, with tests for look-alike domains and URLs that only mention a platform in the path or query.
- **Instagram Business Discovery is careful with input.** Usernames are allow-listed before building the field expression (which blocks `{}` injection into `fields=`), `ig_user_id` and the token are URL-quoted, and the response read is capped. Null or malformed posts never show up as "None".
- **coach_store**: every query is parameterised (no SQL injection). Kind and state are validated. JSON round-trips with `ensure_ascii=False`. Versions are per brand. `list_decisions(limit=)` returns the last N in chronological order, which is exactly what plan Task 9's `build_context` needs. Timestamps are UTC ISO, same as `db._now`.
- **scoring**: the rank is assigned locally rather than trusted from the model. `bool` is rejected as a score. Duplicate goals are rejected. The evidence label is downgraded when Windsor data or findings are missing, which enforces the honesty rule ("never claim data without data"). The 4-tuple return matches `pipeline._invoke`.
- **Cost pattern fits.** `score_goals` follows the same convention as `ai.extract_topics`, `ai.generate_draft` and the others: it doesn't check the cap itself, returns `(result, tin, tout, cost)`, and callers wrap it in `pipeline._invoke`, which calls `db.would_exceed_daily_cap` and `db.log_api_call`. Plan Task 9 does exactly that. No gap.
- **Brand-agnostic.** No brand-specific text in engine code. All user-facing strings are PT-PT.
- **Windows-aware.** `encoding="utf-8", errors="replace"` on subprocess output, prompts read as UTF-8, no shell invocation.

## Interface fit with the not-yet-built tasks (6, 7, 9, 10)

Checked against the plan text:
- Task 7 `chain.gather_source` calls `gather_website(s)`, `gather_video(s, transcribe=whisper_transcribe)` and `gather_instagram_discovery(s, uid, tok)`. All three signatures match. Scheme-less `www.x.pt` is handled inside `gather_website`, as HANDOFF noted.
- Task 7 `run.finish_upload` uses `need.source` as the label. It works, but see Minor M1: website `NeedsUpload.source` is the normalised URL, not what the user typed.
- Task 9 `draft_strategy` passes `evidence = {"windsor": ..., "findings": [brief strings]}`. This matches `score_goals`' use of `.get`.
- Task 10 `describe_section` reads `g['rank'|'goal'|'metric'|'target'|'reasons'|'evidence']` and `scoring.GOAL_MENU[g['goal']]['label']`. All are guaranteed by `validate_scored_goals` and `score_goals`.
- Task 10 `evidence_label` does `EVIDENCE_LABELS[evidence]`, which raises `KeyError` on unknown values. `coach_store.set_section` doesn't validate `evidence` (Minor M4).
- Task 10 uses only `need.instructions` and `need.source`. `need.reason` isn't displayed in the plan's UI, which softens Important I3, but any later UI or log that shows `reason` would surface raw English yt-dlp stderr.
- Task 10 detects budget hits with `"daily cap" in str(e)`, which depends on the English text in `pipeline._invoke` (pre-existing). See Recommendations.

No blocking interface mismatch.

## Issues

### Critical (Must Fix)

None.

### Important (Should Fix)

**I1. `sherlock/gather.py:82` and `:116`: yt-dlp argument injection. The source is passed as a bare positional argument with no `--` separator.**
A source that starts with `-` is read by yt-dlp as an option. `detect_platform` doesn't stop this: `--exec=calc.youtube.com` and `--config-locations=x.tiktok.com` are classed as youtube/tiktok, so plan Task 7's chain will route them to `gather_video` and, via `transcribe=whisper_transcribe`, to the second call. Real exploitation is limited here (single-user local app, one argument, no whitespace allowed), but this is the textbook fix. Fix: put `"--"` before `url` in both argv lists (and/or reject sources starting with `-`), and add a test asserting `cmd[-2:] == ["--", url]`.

**I2. `sherlock/gather.py:82` and `:116`: no timeout and no playlist limit on yt-dlp.**
`subprocess.run` has no `timeout=`, so a stuck network call blocks the Streamlit script for good. Profile and channel URLs are also likely: the spec lists "TikTok handle/URL", and the plan's own chain test uses `https://www.tiktok.com/@a`. For those, `--dump-single-json` with no `--flat-playlist`/`--playlist-end` walks every video in the channel (minutes, a huge JSON). `_video_text` then keeps only the channel-level title and description, so all of that work is wasted. Worse, `whisper_transcribe` on the same URL runs `-x` over the whole channel's audio. Fix: add `timeout=` (and treat `subprocess.TimeoutExpired` as `NeedsUpload`), add `--no-playlist` to the audio download, and for metadata use `--flat-playlist --playlist-end 10` (or similar), rendering entry titles when `info` has `entries`.

**I3. `sherlock/gather.py:86`: raw yt-dlp stderr becomes the user-facing `NeedsUpload.reason`.**
This is inconsistent with the website and Instagram gatherers, which deliberately use fixed PT-PT reasons and test that raw errors never leak. yt-dlp stderr is English, starts with `ERROR:`, and can include URLs or extractor internals. That breaks both the PT-PT-only rule and the spec's "say so kindly". `test_sherlock_video.py:34-40` asserts this behaviour (`"bloqueado" in result.reason`). Fix: add a `VIDEO_FAIL_REASON = "Não consegui ler este vídeo neste momento."` constant, use it here, and flip the test to assert stderr is not in `reason`, matching the other two gatherers.

**I4. `scoring.py:244-266`: `validate_scored_goals` doesn't require every chosen goal to be scored.**
If the model omits one of the user's 1-3 chosen goals, that goal silently disappears from the ranked strategy. The spec says each chosen goal gets a metric, target, rank, reasons and evidence label. A user who picked it would reasonably expect to see it. Fix: after the loop, `if seen != set(allowed_goals): raise ai.InvalidAIResponseError(...)` (PT-PT), and add a test.

### Minor (Nice to Have)

**M1. `sherlock/gather.py:50-62`: `gather_website` returns the normalised URL as `source`**, while `gather_video` and `gather_instagram_discovery` keep the caller's original string. A NeedsUpload for `www.x.pt` comes back as `https://www.x.pt`, and `research_findings.source_ref` differs from what the user typed. It's harmless today, but the inconsistency will surface once Task 7/10 match `needs_upload` back to input rows. Keep the original `url` argument as `source` and use the normalised one only for fetching.

**M2. `sherlock/gather.py:51-54`: `gather_website` fetches any scheme that `urllib` supports** (`file://`, `ftp://`) and any host (localhost, LAN, 169.254.x). The Task 7 chain only routes `http(s)`/`www.` sources here, so this isn't reachable through the planned flow, and redirects to `file:` are blocked by urllib. It is still one guard away from reading local files into a Claude prompt and the findings table. Fix: reject anything other than `http`/`https` (return `NeedsUpload`). Optionally refuse loopback and private hosts.

**M3. `sherlock/gather.py:145-150`: a misleading reason when the credentials are present but the source has no parseable username** (for example `https://instagram.com/p/abc`, which `detect_platform` classes as instagram). The single `if not (username and ig_user_id and access_token)` check reports "A ligação opcional ao Instagram (Business Discovery) não está configurada." even when it is configured. Also, "Business Discovery" is jargon in user-facing copy (spec principle 3). Split the checks: no username should use a "this link is a post, not a profile" style reason.

**M4. `coach_store.py:121`: `set_section` validates `kind` and `state` but not `evidence`.** Task 10's `evidence_label` does a dict lookup that raises `KeyError` on anything other than `data`/`pattern`/`reasoned`. Validate against `("data", "pattern", "reasoned")` here (duplicating `scoring.EVIDENCE_LEVELS`, or importing it).

**M5. `coach_store.py:148-157`: `set_section_state` on a section that doesn't exist is a silent no-op.** Task 9's `accept_section` would then log an "accept" decision for a section that was never stored. Consider checking `rowcount` and raising.

**M6. `sherlock/gather.py:88-91`: if yt-dlp outputs valid JSON that isn't an object** (for example `[]` or `null` where `.get` fails), `_video_text` raises `AttributeError`, which isn't in the `except (TypeError, ValueError)` and would crash the gather. Add `AttributeError` or an `isinstance(info, dict)` check. The existing test covers `None` stdout (`TypeError`) but not `"[]"`.

**M7. `sherlock/gather.py:114-122`: `TemporaryDirectory` cleanup can raise `PermissionError` on Windows** if ffmpeg or whisper still hold the mp3. Because the `return` sits inside the `with`, a successful transcript would be replaced by the exception and then turned into `None` by the outer `except`. Use `tempfile.TemporaryDirectory(ignore_cleanup_errors=True)`. Also note: `whisper.load_model("base")` silently downloads about 140 MB on first use, and openai-whisper may not install on the venv's Python 3.14 (its numba dependency). Worth one line in `requirements.txt`'s comment or HANDOFF.

**M8. `sherlock/gather.py:42-46`: no Content-Type check.** A URL that serves a PDF or binary gets decoded as text and can pass the 200-character minimum as junk, wasting distill tokens later. Return `NeedsUpload` unless the Content-Type is `text/html` or `text/plain`.

**M9. `scoring.py:271-273`: an unknown goal key in `profile["goals"]` raises a bare `KeyError`** before any AI call. The UI constrains choices, so this is low risk, but a PT-PT `ValueError` would match the module's error style. An empty `goals` list also yields the misleading "não veio como uma lista" error after a paid call. Guard with `if not profile["goals"]` before calling the model.

**M10. Environment: yt-dlp isn't installed in `content-creator/venv` yet.** It's installable (pure-Python wheel, confirmed for this Python) and `run.bat` will install it on the next launch, but until then every video source falls back to "O yt-dlp não está instalado." That path depends on `run.bat` activating the venv so `yt-dlp.exe` is on PATH. `[sys.executable, "-m", "yt_dlp", ...]` would remove that dependency. Also, current yt-dlp warns that YouTube extraction without a JS runtime (deno) is deprecated. Verify during the real end-to-end run.

**M11. Test gap: there's no project-wide tone test over canned copy.** Only `upload_instructions("instagram")` is checked (`test_sherlock_website.py:20`). The spec requires "tone banned-word test on canned copy". Add one parametrised test over all `_UPLOAD_INSTRUCTIONS`, `WEBSITE_FAIL_REASON`, `DISCOVERY_*_REASON`, the other `NeedsUpload` reasons and `GOAL_MENU` labels/metrics (my manual sweep found all of these clean today).

**M12. Test gaps, smaller:** no test that the `score_goals` prompt contains the chosen goals' `GOAL_MENU` lines; no test for missing `metric`/`target` in validation; no test that the yt-dlp argv is safe (see I1).

## Declined to judge

- `pipeline._invoke`'s English, non-gentle budget and error messages ("This call could push today's spend over the $X daily cap"): pre-existing code outside the scope. They matter for the coach, though. See Recommendations.
- `.env.example` / `config.py` defaults containing brand-specific values (`marianabotelho-ig`, the Dropbox DB path): pre-existing and not engine code.
- `config.py` doesn't load `IG_ACCESS_TOKEN`/`IG_BUSINESS_ACCOUNT_ID`: plan Task 10 reads them from `os.environ` directly, which is by design and not built yet.
- The `GRAPH_VERSION = "v21.0"` bump to a newer version: already tracked in HANDOFF for the real end-to-end test.
- Theme and look-and-feel parts of the merged diff (`theme.py`, `.streamlit/config.toml`, `app.py` theme lines, `test_theme.py`): excluded by instruction.
- The pre-AO90 spelling "objectivos" in PT-PT copy: consistent with the plan and still valid PT-PT; a style choice.
- Gendered copy ("quando estiveres pronta") in plan Task 9's `StrategyNotReady`: not built yet. Worth making neutral when Task 9 is implemented, since the engine should stay brand-agnostic.
- Missing tasks #21, #22, #24, #25: out of scope by instruction.

## Recommendations

1. Fix I1-I4 in one small hardening ticket. They're all a few lines each, with tests.
2. Before Task 7/9/10, give `pipeline._invoke` (or the coach callers) a PT-PT gentle budget message and a typed check (`isinstance(e, pipeline.DailyBudgetExceededError)`) instead of Task 10's planned `"daily cap" in str(e)` substring match.
3. During the one real paid end-to-end run, include one TikTok profile URL and one YouTube channel URL to confirm I2's fix, and check yt-dlp's JS-runtime warning for YouTube.

## Assessment

**Ready to merge?** With fixes.

**Reasoning:** The built modules are cohesive, match the spec and the later tasks' interfaces, follow the cost and tone conventions, and all 171 tests pass. The yt-dlp integration still needs hardening before Task 7 wires it in: the `--` separator, a timeout and playlist bounds, and a PT-PT failure reason. Scoring must also reject responses that drop a chosen goal.
