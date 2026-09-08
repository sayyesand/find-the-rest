# Find the Rest v0.8 — beta-hardened Xcode + backend project

This build turns the prototype source into an Xcode project plus a deployable HTTPS backend configuration.

## What is ready
- `ios/FindTheRest.xcodeproj` opens directly in Xcode.
- Main SwiftUI app and Share Extension are separate targets.
- Both targets use the App Group `group.app.findtherest.shared`.
- URL scheme: `findtherest://`.
- The app has Settings where you can enter and test the deployed HTTPS API URL.
- The backend has a production Dockerfile and `render.yaml` blueprint.
- Backend test suite includes matching, media, semantic, benchmark, API, and beta-authentication tests.
- Optional server API-key protection (`FIND_THE_REST_API_KEY`) is supported and the iPhone Settings screen can store/send the key.
- Media uploads are size-limited and MIME-checked before decoding.
- Docker includes a health check and `scripts/smoke_test.sh` verifies a deployment.

## What still requires your accounts
I cannot sign an iOS build or create a TestFlight release without access to your Apple Developer/App Store Connect account. I also cannot create a public cloud deployment without credentials for a hosting provider.

## 1. Deploy the backend
The easiest route is any Docker-capable HTTPS host. This repo includes `render.yaml` and `backend/Dockerfile`.

Required secrets:
- `YOUTUBE_API_KEY` — YouTube Data API v3 key.
- `FIND_THE_REST_API_KEY` — random beta access key (Render blueprint can generate it).

Optional:
- `ENABLE_LOCAL_TRANSCRIPTION=1` only if the host installs the AI requirements and has enough resources.

After deployment, verify:
`https://YOUR-HOST/health`

Expected JSON includes `"ok": true`.

## 2. Open the iPhone project
On a Mac with Xcode 16 or newer:
1. Open `ios/FindTheRest.xcodeproj`.
2. Select the **FindTheRest** target → Signing & Capabilities → choose your Apple Developer Team.
3. Do the same for **FindTheRestShare**.
4. Add/enable **App Groups** on both targets and select the same group. If `group.app.findtherest.shared` is unavailable, create your own group and replace that string in:
   - `FindTheRest/ShareHandoff.swift`
   - `FindTheRestShare/ShareViewController.swift`
   - both `.entitlements` files
5. If the bundle identifiers are already taken, change:
   - `com.findtherest.app`
   - `com.findtherest.app.share`
6. Select your connected iPhone and press Run.

## 3. Connect the app to the backend
On the iPhone:
1. Open **Find the Rest**.
2. Tap **Settings**.
3. Enter the deployed HTTPS URL, for example `https://find-the-rest-api.example.com`.
4. Tap **Save & Test Connection**.
5. You should see **Connected successfully.**

## 4. Test the Share workflow
1. Open a public video in a source app.
2. Tap Share.
3. Choose **Find the Rest**.
4. Tap Post in the Share Extension.
5. The app opens and starts analysis automatically.

Whether iOS supplies the actual movie file depends on the source app. A URL alone is still accepted for candidate discovery. Media/semantic confidence is added only when permitted media is available.

## 5. TestFlight
Once the app builds on device:
1. In Xcode choose a generic/connected iOS destination and **Product → Archive**.
2. In Organizer choose **Distribute App → App Store Connect → Upload**.
3. After processing in App Store Connect, enable the build under TestFlight and add testers.

## Current limitation
The app does not bypass platform restrictions or scrape protected video files. It searches available metadata/public sources and compares media only when that media is legitimately supplied or accessible.


## Beta security notes
- `/health` stays public for hosting health checks.
- Analysis/media endpoints require `X-FindTheRest-Key` only when `FIND_THE_REST_API_KEY` is configured.
- For a private beta, configure the server key and enter the same key in the iPhone app Settings.
- The beta stores this key in app preferences for simplicity; before a public App Store release, move it to Keychain or replace static keys with account-based tokens.
- Uploaded clips are written only to temporary request directories and discarded when processing finishes.

## Smoke test
With the server running:
```bash
export FIND_THE_REST_API_KEY=your-beta-key
./scripts/smoke_test.sh https://YOUR-HOST
```


## v0.9 — Multi-platform discovery foundation

This build adds public-metadata adapters for Instagram, Facebook, TikTok, X, Reddit and ordinary web pages. These adapters only read what an unauthenticated public page exposes; they do not log in, bypass privacy controls, or crawl a creator's gallery.

For `social` and `web` scope, the backend can broaden discovery through a licensed Brave Search API account by setting `BRAVE_SEARCH_API_KEY`. Search results are ranked with the same explainable continuation evidence used elsewhere. Metadata-only confidence remains capped below 85%; higher confidence requires permitted media/semantic comparison.

Platform-specific official APIs can be added behind the adapter boundary as access is approved, without changing the iPhone workflow.


## v0.10 — Cross-platform candidate hunter

This build turns broad search into a ranked candidate hunt.

For a public source post, the backend now generates separate search plans for:
- direct continuations (Part 2 / continued / what happened next),
- full or original versions,
- reposts and mirrors,
- platform-specific continuation searches across YouTube, Instagram, Facebook, TikTok, X and Reddit.

Results are canonicalized so tracking-link variants collapse into one candidate. The ranker gives only a small bonus to same-creator results, allowing a materially stronger cross-platform original or continuation to win. The best result is classified as an official continuation, continuation repost, full original, or related repost before the API returns it.

Provider cost is bounded by `FIND_THE_REST_MAX_SEARCHES` (default 7, maximum 9). Cross-platform web discovery activates only when `BRAVE_SEARCH_API_KEY` is configured. Restricted/private galleries are never crawled or bypassed.

Current automated backend test count: 26 passing.


## v0.11 — Source tracing

This build adds source-tracing evidence so Find the Rest can prefer the actual longer/original upload over a chopped repost when the evidence supports that conclusion.

New signals include:
- explicit original/full/uncut wording,
- candidate duration relative to the source clip,
- whether the candidate predates the source upload,
- creator-authority evidence,
- fragment/repost wording penalties.

YouTube candidates are now enriched with video duration through the official YouTube Data API. Originality is deliberately a secondary ranking signal: it may break a close contest but cannot elevate a weakly related “full original” result over a materially stronger continuation match.

The iPhone result screen now labels likely originals, fragments and reposts, displays known duration, and exposes source-tracing evidence in the “Why this matched” section.

Current automated backend test count: 31 passing.


## v0.12 — Story fingerprinting

This build adds title-independent story fingerprinting.

The backend now extracts distinctive story details from source metadata (and is designed to accept transcript text as the pipeline expands), including names, quoted phrases, uncommon keywords, and numbers/years. It generates additional search queries from those details that do not depend on “Part 2,” “continued,” or matching titles.

Search candidates receive a `story_fingerprint` evidence score. That score can modestly rescue a strong same-story result whose title is completely different, but it is capped so a single generic word cannot overpower contradictory evidence.

The iPhone “Why this matched” section now shows Story fingerprint evidence alongside semantic, source-tracing, creator, sequence, and media signals.

Current automated backend test count: 35 passing.


## v0.13 — Spoken-story fingerprinting

This build makes shared media useful even when a platform exposes poor or empty post metadata.

When the iOS Share Extension supplies a user-shared movie, `/v1/share-analyze` can now:
- accept a caller-provided transcript, or
- transcribe the shared source locally with faster-whisper when local transcription is enabled,
- fold those spoken words into the Story Fingerprint,
- generate fingerprint searches from the spoken narrative,
- rank candidates using story-fingerprint overlap,
- discard the shared media after the request.

The normal lightweight Dockerfile remains transcription-off. `backend/Dockerfile.ai` and `render-transcription.yaml` provide a transcription-enabled deployment option using `requirements-ai.txt`.

No restricted candidate media is downloaded or scraped. Spoken-story fingerprinting operates only on media the user explicitly shares or transcript text the caller provides.

Current automated backend test count: 37 passing.


## v0.14 — Ending-aware continuation matching

This build adds a dedicated ending fingerprint for the last spoken moments of the source.

The backend now:
- extracts the final spoken terms from the source transcript (or falls back to metadata),
- detects cliffhanger language such as “but then,” “until,” “when suddenly,” and question endings,
- generates additional searches from the final narrative details,
- gives later tail terms more weight than earlier ones,
- adds `ending_continuity` and `cliffhanger_strength` to candidate evidence,
- uses ending evidence as a secondary boost rather than allowing it to overpower weak overall matches.

This is intended for the common case where Part 1 ends on a distinctive event, object, person or unresolved action, while the continuation uses a different title.

The iPhone “Why this matched” section now displays Ending continuity and Cliffhanger strength.

Current automated backend test count: 41 passing.


## v0.15 — False-match guard

This build adds negative evidence. Find the Rest no longer only asks “what matches?”; it also asks “what clearly conflicts?”

The guard checks candidate text against the source story fingerprint for:
- conflicting years/numbers,
- conflicting named people/entities,
- missing key story anchors.

These contradictions reduce the candidate score before final ranking. The penalties are bounded so incomplete metadata does not automatically kill a plausible match.

The iPhone “Why this matched” section now displays Contradiction penalty, Name conflict, and Year/number conflict alongside the positive evidence.

Current automated backend test count: 45 passing.


## v0.16 — Continuation chain

This build stops treating every credible result as an isolated match.

The backend now assembles a continuation chain from ranked candidates and can identify:
- explicit Part 2 / Part 3 / later numbered segments,
- unnumbered continuations,
- follow-up/update videos,
- likely full/original versions.

Explicit numbered parts are ordered numerically. Unnumbered updates use relationship and publication evidence. Duplicate reposts claiming the same part number are collapsed so the chain does not show several competing “Part 2” entries.

Chain construction is stricter than ordinary candidate display: candidates with weak chain evidence or strong contradiction penalties are excluded. The API returns `continuation_chain` and `chain_confidence`.

The iPhone app now shows a Story chain section with part labels, confidence, ordering rationale, and direct Open links.

Current automated backend test count: 50 passing.


## v0.17 — Self-healing chain gaps

This build detects holes inside an otherwise credible numbered continuation chain.

If Find the Rest assembles something like Part 2 → Part 4, it now:
- detects that Part 3 is missing,
- generates a targeted search specifically for Part 3,
- requires explicit missing-part wording plus a stricter confidence threshold,
- reruns story fingerprint, ending continuity, contradiction guard, dedupe, and source tracing,
- reinserts the recovered installment only when it clears those checks.

The API now returns `missing_parts` and `recovered_parts`. The iPhone Story chain section shows both recovered installments and any gaps that remain unresolved.

Gap recovery is bounded to four missing parts and only activates when the configured public web search provider is available.

Current automated backend test count: 54 passing.


## v0.18 — Link-by-link chain verification

This build adds a new permitted-media endpoint: `POST /v1/verify-chain`.

When Find the Rest has two or more user-provided/permitted clips, it can now verify each transition in order:
- ending of clip 1 → beginning of clip 2,
- ending of clip 2 → beginning of clip 3,
- and so on.

Each link receives:
- visual boundary continuity,
- audio boundary continuity,
- transcript-semantic continuity,
- scene-semantic continuity,
- a combined link confidence,
- a verified / not verified decision.

Overall chain confidence deliberately weights the weakest transition heavily so a bad Part 2 → Part 3 jump cannot be hidden by other strong links.

The endpoint accepts 2–6 ordered clips and never downloads restricted platform media.

Current automated backend test count: 56 passing.


## v0.19 — Visual fingerprint foundation

This build makes still images, screenshots, and representative video frames first-class evidence.

New backend capabilities:
- `POST /v1/visual-fingerprint`
- `POST /v1/compare-visual`

Visual fingerprints combine:
- average perceptual hash,
- difference perceptual hash,
- coarse color distribution,
- edge-structure energy.

For videos, Find the Rest samples across the clip and keeps up to seven distinctive representative frames while rejecting blank and near-duplicate frames. This is deliberately stronger than relying on the first frame alone.

Visual comparison is designed to tolerate resizing, compression, brightness shifts, and modest overlays better than exact-pixel matching. A visual match is treated as evidence of shared imagery, not proof of authorship or human identity.

The iOS Share Extension now accepts images/screenshots in addition to URLs and movies. Shared screenshots can be fingerprinted directly in the app, while shared videos also receive representative-frame fingerprints.

This is the foundation for later reverse-source discovery, screenshot-to-video matching, repost tracing, visible-text/OCR evidence, and privacy-conscious face-similarity evidence.

Current automated backend test count: 60 passing.


## v0.20 — Visible-text intelligence

This build adds OCR-based visible-text evidence for screenshots, still images, and sampled video frames.

New backend capability:
- `POST /v1/extract-visible-text`

The visible-text layer can surface:
- usernames/handles,
- watermarks,
- hashtags,
- URLs,
- subtitles,
- headlines,
- signs,
- product names,
- distinctive keywords.

For video, OCR samples up to five frames instead of trusting only the first frame. Extracted clues produce suggested search queries and are displayed in the iPhone app under **Visible clues**.

When user-shared media also includes a source URL, OCR text now feeds the actual Story Fingerprint and cross-platform candidate search rather than being merely informational.

Deployment Docker images now install `tesseract-ocr`.

Also fixed in this build:
- question-mark cliffhanger detection now checks the raw transcript tail before punctuation is stripped,
- ending-aware search no longer relies on a single Google-style OR expression,
- search budgets explicitly reserve capacity for normal, Story Fingerprint, and ending-aware search paths so later evidence modes cannot be starved.

OCR is treated as fallible evidence, not ground truth.

Current automated backend test count: 64 passing.


## v0.21 — Exact-match explainability

This build separates real candidate content from the app's internal search labels.

Candidate records now preserve:
- the actual search-result/video description as `snippet`,
- the internal search reason separately,
- concrete `matched_details`.

Story, ending, contradiction, source-tracing, and chain logic now use the candidate title + real snippet rather than internal labels such as “story fingerprint 1.” This removes a subtle source of false-positive confidence.

Matched details report exactly which evidence overlapped:
- names,
- phrases,
- numbers,
- story keywords,
- ending terms.

The iPhone app now shows a **Matched story details** section beneath the best result and displays actual candidate snippets in both the best match and alternate results.

Current automated backend test count: 68 passing.


## v0.22 — Chain semantics and contradiction hardening

This build removes two subtle beta-risk failure modes.

### Years vs ordinary numbers
Story fingerprints now track actual four-digit years separately from generic numbers such as Route 66, room 204, model 360, or Part 3. The contradiction guard only applies a year conflict when both source and candidate contain genuine, disagreeing years. A generic number can no longer create a false year contradiction.

### Episode numbers vs continuation parts
`Episode 248` is no longer interpreted as `Part 248`.

Chain nodes now carry:
- `inferred_part`
- `episode_number`

Only explicit Part/Pt wording produces a part number. Episode numbering remains useful context but does not create false missing-part gaps or overstate continuation structure.

Duplicate explicit parts are now resolved by strongest chain evidence and creator authority before chronology, preventing an earlier weak repost from beating a later stronger official candidate solely because it was posted first.

### iPhone compatibility
The iOS response decoder now supplies safe defaults for newer chain fields if the app briefly talks to an older backend during beta deployment. This reduces version-drift failures during staged releases.

Current automated backend test count: 71 passing.


## v0.23 — Standalone “Find from Screenshot”

This build turns screenshot/image sharing into a true discovery workflow even when no source URL is available.

New backend endpoint:
- `POST /v1/discover-media`

Workflow:
1. user shares a screenshot/image,
2. Find the Rest creates a visual fingerprint,
3. OCR extracts visible text,
4. usernames, watermarks, URLs, hashtags, phrases, and distinctive keywords become search clues,
5. licensed open-web search runs those clues when `BRAVE_SEARCH_API_KEY` is configured,
6. candidates are deduplicated, ranked, and explained,
7. the iPhone app shows **Found from screenshot** and lets the user open the best result directly.

The standalone result includes:
- best candidate,
- alternate candidates,
- confidence,
- actual snippets,
- matched names/phrases/numbers/keywords/handles,
- OCR text,
- representative visual-frame count.

Important limitation: this release does not send perceptual hashes to a third-party reverse-image provider. Therefore text-free screenshots can be fingerprinted but cannot yet perform true internet-scale reverse-image discovery. The app states this rather than fabricating a result.

A screenshot with an accompanying source URL continues to use the richer URL + media analysis path.

Current automated backend test count: 74 passing.


## v0.24 — Reverse-image provider interface + multimodal fusion

This build adds a provider-neutral reverse-image discovery layer for text-free screenshots and images.

New backend adapter:
- `app/reverse_image.py`

Optional configuration:
- `FINDREST_REVERSE_IMAGE_ENDPOINT`
- `FINDREST_REVERSE_IMAGE_KEY`

The configured endpoint is treated as a licensed reverse-image gateway. Find the Rest sends one multipart field named `media` and expects JSON shaped like:

`{"results":[{"url":"...","title":"...","snippet":"...","score":0.82,"creator":"...","platform":"web"}]}`

This keeps the product architecture independent of any single image-search vendor.

Standalone media discovery now runs two independent paths when available:
- OCR / visible-text search
- reverse-image search

Candidates sharing the same URL are fused. When OCR evidence and reverse-image evidence independently agree on the same candidate, the ranking receives a small capped multimodal-agreement boost and exposes `multimodal_agreement` in evidence.

Text-free screenshots can therefore produce source candidates once a reverse-image provider is configured. If no provider is configured, the app remains honest about the limitation rather than fabricating results.

Current automated backend test count: 76 passing.


## v0.25 — Privacy-safe caching + beta feedback

This build adds product-level infrastructure for a serious beta.

### Short-lived result cache
URL-only analysis results are cached in memory using SHA-256-derived keys. The default cache:
- expires after 15 minutes,
- holds at most 256 entries,
- never exposes the source URL inside the cache key,
- never caches raw uploaded screenshots or video.

Environment controls:
- `FINDREST_CACHE_TTL_SECONDS`
- `FINDREST_CACHE_MAX_ITEMS`

### Search IDs
Analysis and standalone media-discovery responses now include a random `search_id`. This lets feedback and later observability refer to a search without retaining the user's media.

### Privacy-safe feedback
New endpoint:
- `POST /v1/feedback`

The iPhone app now offers:
- Correct
- Wrong
- Not enough

Feedback stores only:
- search ID,
- verdict,
- optional best-match URL,
- source platform,
- confidence.

It does **not** store the screenshot/video, transcript, OCR text, candidate snippets, or perceptual fingerprints.

Optional destination:
- `FINDREST_FEEDBACK_PATH`

The UI explicitly tells beta users what feedback does not send.

### Health/privacy visibility
`/health` now exposes cache status plus a human-readable reminder that uploaded media is processed in temporary request directories and discarded.

Current automated backend test count: 79 passing.


## v0.26 — Result intent + “not posted yet” state

This build makes the app's answer more useful than a binary match/no-match response.

Analysis now returns:
- `result_state`
- `result_message`
- `result_state_confidence`
- `available_actions`

Possible states include:
- `continuation_found`
- `full_original_found`
- `related_only`
- `likely_not_posted_yet`
- `no_verified_match`
- `insufficient_context`

The “likely not posted yet” state is intentionally conservative. It only appears when:
- broad public search is actually configured,
- no credible continuation was found,
- and the source contains multipart language or a strong cliffhanger signal.

It is capped below 70% confidence because search failure cannot prove non-publication.

The iPhone app now shows a **What I found** section that summarizes the state and relevant next actions such as:
- Watch continuation
- Watch full original
- Find other copies
- Review related
- Check later
- Share video/screenshot
- Try source link

This makes failed searches useful without pretending certainty.

Current automated backend test count: 84 passing.


## v0.27 — Continuation watch foundation

This build makes “may not be posted yet” actionable.

New endpoints:
- `POST /v1/watch`
- `GET /v1/watch/{watch_id}`
- `POST /v1/watch/{watch_id}/check`

A watch stores only:
- watch ID,
- source URL,
- scope,
- creation/check timestamps,
- latest result state,
- latest best-match URL,
- active/inactive state.

It does not store the original screenshot, video, transcript, OCR text, or visual fingerprint.

The iPhone app now shows **Watch for the Rest** when a result is `likely_not_posted_yet` or `no_verified_match`. After saving, the same control becomes **Check Watch Now**, which reruns the search and replaces the displayed result if something credible appears.

Watches automatically become inactive when a credible continuation or full/original result is found.

This is the backend/UI foundation for later scheduled checks and push notifications. This build does not yet perform background polling or send push notifications on its own.

Optional watch-store location:
- `FINDREST_WATCH_PATH`

Current automated backend test count: 86 passing.


## v0.28 — Beta diagnostics + safer iPhone secrets

This build improves beta reliability and security.

### API key moved to Keychain
The iPhone beta API key is no longer stored in `UserDefaults`.

`APIClient` now stores it in the iOS Keychain using:
- generic-password storage,
- service name `FindTheRest`,
- `kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly`.

Older beta installs migrate the legacy key from `UserDefaults` automatically and then remove the old copy.

### Capability diagnostics
New endpoint:
- `GET /v1/capabilities`

It reports whether the deployment currently has:
- YouTube search,
- open-web search,
- reverse-image search,
- local transcription,
- watch storage,
- feedback storage.

This is intended to distinguish “feature not configured” from “app broken” during beta troubleshooting.

### Watch listing
New endpoint:
- `GET /v1/watches`

This returns active continuation watches so future iPhone watch-management UI can be built without changing the backend contract.

Current automated backend test count: 87 passing.


## v0.29 — iPhone watch manager

This build makes continuation watches manageable from the app instead of only through individual search results.

### New iPhone Watches screen
A bell button in the main toolbar opens the active-watch manager.

The screen supports:
- listing active watches,
- pull-to-refresh,
- manual “Check Now,”
- removing a watch,
- showing the latest known result state.

### Backend watch management
New endpoint:
- `DELETE /v1/watch/{watch_id}`

Removing a watch deactivates it rather than deleting source history from the store. Deactivated watches no longer appear in `GET /v1/watches`.

Existing endpoints continue to support:
- create,
- status,
- manual re-check,
- active-watch listing.

No raw screenshot, video, transcript, OCR text, or visual fingerprint is stored in a continuation watch.

Current automated backend test count: 88 passing.


## v0.30 — Crop/mirror/overlay-resistant visual matching

This build hardens visual matching against common repost transformations.

New robust comparison checks:
- horizontal mirroring,
- center crops at multiple scales,
- top-caption overlays,
- bottom-caption overlays,
- ordinary resizing/compression already handled by perceptual fingerprints.

New endpoint:
- `POST /v1/compare-visual-robust`

It samples permitted source/candidate media and performs symmetric local-region matching. A strong score means the imagery is likely shared; it is not treated as proof of authorship, chronology, or a person's identity.

The implementation is deliberately local and provider-independent, so it can later be fused into automatic candidate verification when candidate media is legally/permissibly available.

New adversarial regression tests cover:
- mirrored imagery,
- caption overlays,
- unrelated visual geometry.

Current automated backend test count: 91 passing.


## v0.31 — Provenance/source-lineage graph

This build adds a provenance layer on top of the ranked candidate list.

The backend now infers a conservative source-lineage graph with nodes for:
- the shared source,
- likely originals/full versions,
- continuations,
- continuation reposts,
- excerpts/fragments,
- related same-creator material.

Possible inferred relationships include:
- `likely_source_of`
- `continues_as`
- `continues_via_repost`
- `excerpt_or_fragment`
- `likely_repost_of`
- `same_creator_related`

The graph combines source-tracing evidence, creator continuity, chronology, continuation wording, story fingerprint overlap, reverse-image evidence when present, and candidate confidence. It does not treat lineage as proof of authorship.

The iPhone UI now includes a **Source lineage** section showing:
- likely relationships,
- relationship confidence,
- the primary reason for each inferred edge,
- overall lineage confidence.

Low-confidence candidates are excluded so a broad web search does not turn into a noisy graph.

New regression tests cover:
- likely original → shared source,
- source → continuation,
- original → fragment,
- exclusion of weak unrelated candidates.

Current automated backend test count: 95 passing.


## v0.32 — Whole-clip audio fingerprint matching

This build adds audio fingerprint comparison beyond the existing two-second seam waveform check.

New endpoint:
- `POST /v1/compare-audio-fingerprint`

The engine:
- decodes user-provided/permitted audio locally with FFmpeg,
- creates overlapping spectral-shape fingerprints,
- normalizes volume,
- compares windows across the whole clips rather than requiring the same timestamp,
- tolerates ordinary re-encoding/noise,
- requires multiple supporting windows for a strong same-audio determination.

This helps detect excerpts/reposts where the video has been cropped, mirrored, captioned, or visually changed but much of the underlying audio remains.

The fingerprint is not speaker identification and a shared-audio match is not treated as proof of authorship.

Regression tests cover:
- large volume changes,
- small codec/noise-like perturbations,
- unrelated spectral content.

Current automated backend test count: 98 passing.


## v0.32 — Robust audio fingerprinting

This build adds an audio fingerprinting layer that complements transcript semantics and exact boundary waveform comparison.

New engine: `backend/app/audio_fingerprint.py`

It:
- decodes permitted media to mono PCM with FFmpeg,
- normalizes away overall volume,
- creates overlapping coarse spectral signatures,
- hashes relative spectral shape rather than raw waveform samples,
- compares multiple windows symmetrically,
- rejects silence instead of manufacturing a fingerprint.

New endpoint:
- `POST /v1/compare-audio-fingerprint`

The matcher is designed to tolerate ordinary re-encoding, volume changes, and light added noise/music better than exact waveform correlation. A strong match is still only evidence that two clips share underlying audio; it is not proof of authorship or chronology.

Regression tests cover volume changes, codec-like noise, unrelated spectral content, and silence.

Current automated backend test count: 99 passing.


## v0.33 — Automatic multimodal media verification

This build adds a single verification pass for a permitted source/candidate media pair.

New endpoint:
- `POST /v1/verify-media-pair`

The verifier combines:
- robust visual similarity,
- audio fingerprint similarity,
- end/start visual boundary continuity,
- end/start audio boundary continuity,
- transcript/story semantic continuity,
- scene semantic continuity.

The fusion layer is availability-aware:
- missing audio is omitted rather than scored as failure,
- missing transcripts are omitted rather than scored as failure,
- agreement across independent channels adds only a modest confidence boost,
- strong contradictions reduce confidence,
- final verdicts are `strong_match`, `likely_match`, `possible_match`, or `not_verified`.

The response exposes per-signal scores and contribution weights so beta failures remain explainable.

The iOS client now has models and an API method ready for a future candidate-media verification picker.

Privacy remains unchanged: only user-provided/permitted media is compared, inside temporary request storage, and restricted social-media content is not downloaded.

Current automated backend test count: 103 passing.


## v0.34 — iPhone candidate-media verification UI

This build makes the v0.33 multimodal verifier directly usable from the iPhone app.

When a source video was shared into Find the Rest, the results screen now includes **Verify a candidate clip**.

The user can:
- choose a permitted candidate video from Files,
- run the existing `/v1/verify-media-pair` verifier,
- see the final verdict,
- see overall verification confidence,
- see how many independent signals agree,
- inspect robust visual, audio fingerprint, boundary visual/audio, transcript/story, and scene scores,
- inspect the contribution of each signal,
- see any contradiction penalty.

Candidate media is compared only after the user explicitly selects it. The app does not scrape or download restricted social-media video.

The picker is intentionally limited to movie files for this beta path.

Current automated test count: 104 passing.


## v0.35 — Scheduler-ready continuation watches

Continuation watches can now be executed safely as a bounded server batch.

New endpoint:
- `POST /v1/watches/check-due`

The runner:
- selects only active watches that are actually due,
- defaults to a six-hour recheck interval,
- defaults to at most 10 watches per invocation,
- isolates failures so one bad source does not abort the batch,
- automatically deactivates a watch when a credible continuation/full original is found,
- reports checked/found/remaining counts without returning stored private media.

Deployment controls:
- `FINDREST_WATCH_INTERVAL_MINUTES` (minimum 60, default 360)
- `FINDREST_WATCH_BATCH_SIZE` (1–25, default 10)

This is deliberately scheduler-ready rather than pretending a scheduler exists. A hosting cron/scheduled job still needs to invoke the endpoint. Push notifications are not enabled yet.

Current automated backend test count: 108 passing.


## v0.36 — Push notification foundation

This build connects continuation watches to a privacy-conscious iPhone push-notification foundation.

Backend additions:
- `POST /v1/push/register`
- `DELETE /v1/push/{installation_id}`
- persistent installation/device-token storage
- short token fingerprints in API responses instead of exposing raw APNs tokens
- watch-to-installation binding
- duplicate event suppression so the same found result is not repeatedly pushed
- notification attempts from both manual watch checks and scheduled batch checks
- push delivery status included in batch-check results
- `/v1/capabilities` now reports whether push delivery is configured

Provider-neutral APNs gateway configuration:
- `FINDREST_PUSH_ENDPOINT`
- `FINDREST_PUSH_KEY`
- `FINDREST_PUSH_STORE_PATH`

The configured gateway receives the APNs device token, environment, notification text and result link. Apple credentials remain outside the app/backend source tree.

iPhone additions:
- notification permission request
- APNs remote-notification registration
- persistent random installation ID
- device-token registration with the Find the Rest backend
- automatic retry of a previously obtained token on later app launches
- watches automatically include the installation ID
- foreground notifications can appear as a banner and sound
- Debug builds use APNs sandbox; Release builds use production
- Xcode entitlements now select the correct APNs environment per build configuration

This still does not claim production push is active until a trusted APNs gateway and Apple push credentials are configured.

Current automated backend test count: 112 passing.


## v0.37 — Backend Capabilities dashboard

Settings now shows a live **Backend capabilities** section so beta testers can tell the difference between a broken feature and a provider that simply has not been configured.

The iPhone app now reads `GET /v1/capabilities` and displays status for:
- YouTube search,
- open-web search,
- reverse-image search,
- local transcription,
- continuation watches,
- feedback capture,
- push notifications.

Disabled services are labeled **Not configured** rather than shown as failures. Each row includes a short explanation of what the capability enables or which provider it requires.

The dashboard refreshes automatically after a successful connection test and can also be refreshed manually.

Current automated test count: 113 passing.


## v0.38 — Durable SQLite continuation-watch storage

Continuation watches now use SQLite instead of the earlier JSON-file store.

Improvements:
- WAL-mode SQLite persistence for safer concurrent access,
- database busy timeout and transactional writes,
- active-watch uniqueness enforced by the database,
- scheduler-friendly indexes for due-watch scans,
- tracking parameters stripped before watch URLs are persisted,
- duplicate tracking variants resolve to the same active watch,
- inactive watch history can remain while a new active watch is created,
- existing JSON watch stores migrate automatically on first use,
- the original JSON is preserved beside the database as a `.legacy-json` backup,
- `FINDREST_WATCH_DB_PATH` is now the preferred deployment setting,
- the existing `FINDREST_WATCH_PATH` setting remains supported for backward compatibility.

The Backend Capabilities screen now reports the watch storage backend as SQLite.

This is still intentionally a beta-scale local database. A managed Postgres database remains the appropriate later step for horizontally scaled multi-instance production deployment.

Current automated test count: 117 passing.


## v0.39 — Privacy-safe beta observability

This build adds operational diagnostics for real beta testing without retaining raw user content.

New endpoint:
- `GET /v1/diagnostics` (API-key protected)

Recorded metrics are deliberately coarse:
- search/verification event counts,
- success/failure counts,
- result-state distribution,
- source-platform distribution,
- candidate counts,
- confidence values,
- cache usage,
- p50/p95/max latency,
- credible-result rate,
- which evidence paths contributed (story fingerprint, ending, provenance, OCR, reverse image, robust visual, audio fingerprint, transcript semantics, etc.).

The diagnostics recorder explicitly drops raw:
- URLs,
- screenshots/videos,
- transcripts,
- OCR/visible text,
- search queries,
- titles/snippets,
- creator names,
- filenames,
- device tokens,
- API keys.

Standalone screenshot/media discovery and multimodal media verification now emit privacy-safe diagnostic events in addition to normal URL analysis.

Retention is bounded:
- `FINDREST_DIAGNOSTICS_MAX_EVENTS` defaults to 1000,
- the JSONL log automatically compacts when it grows beyond the retention window,
- `FINDREST_DIAGNOSTICS_PATH` controls the deployment location.

This gives the beta enough telemetry to find slow paths, weak evidence combinations, and poor result-state calibration without turning Find the Rest into a user-tracking system.

Current automated test count: 120 passing.


## v0.40 — Adversarial benchmark suite

This build adds a deterministic adversarial benchmark that can be run locally or through the protected backend endpoint:

- `GET /v1/benchmark`

The benchmark currently covers:
- fake Part 2 labels with conflicting story details,
- same-creator but unrelated videos,
- official same-creator Part 2 continuations,
- continuation reposts,
- likely full/original versions,
- Episode vs Part numbering,
- duplicate explicit parts,
- tracking-parameter repost variants,
- canonical URL integrity,
- related-only results,
- insufficient-context cases,
- probabilistic “not posted yet” behavior,
- failure to claim nonpublication without broad search coverage,
- Roman-numeral part ordering.

The benchmark reports total pass rate and per-category pass rates for:
- false positives,
- positives,
- repost handling,
- provenance,
- ordering,
- no-answer behavior.

During this build the benchmark exposed a real classification bug: same-creator titles containing `Part 2` were being normalized before continuation classification, which stripped the part number and incorrectly downgraded them to related material. The classifier now evaluates continuation wording with the dedicated continuation detector before normalization, and a permanent regression test protects the fix.

Dedicated media tests continue to cover crop/mirror/overlay robustness, audio re-encoding/noise, OCR, and multimodal verification.

Current automated test count: 124 passing.


## v0.41 — On-device OCR and speech clues

The iPhone app now prefers to extract useful search clues on the device before uploading source media.

New iPhone-side processing:
- Vision OCR (`VNRecognizeTextRequest`) for screenshots/images,
- sampled video-frame OCR using `AVAssetImageGenerator`,
- local speech recognition using `SFSpeechURLRecognitionRequest`,
- request-scoped security-scoped file access,
- a 20-second speech-recognition guard so local transcription cannot hang indefinitely.

New backend endpoint:
- `POST /v1/analyze-clues`

When a shared post includes a source URL and the iPhone successfully extracts visible text and/or speech, the app sends only those text clues plus the public URL for discovery. The source screenshot/video does not need to be uploaded to the Find the Rest backend for that search.

If no useful local clues are available, the existing permitted-media analysis path remains as a fallback.

Standalone screenshots with no source URL still use provider-assisted media discovery, because text-free reverse-image/source finding requires the image itself.

Privacy behavior:
- local-clue requests are not written to the result cache,
- diagnostics record only coarse evidence-path labels such as `on_device_ocr` and `on_device_transcript`,
- raw OCR/transcript text is not written to diagnostics, feedback, or watch storage.

The iOS app now includes the required speech-recognition usage disclosure.

Current automated test count: 126 passing.


## v0.42 — Automatic permitted candidate verification

Find the Rest can now automatically verify the current best candidate when a deployment has a licensed/permitted candidate-media gateway configured.

New backend adapter:
- `backend/app/candidate_media.py`

New endpoint:
- `POST /v1/verify-candidate-url`

Safety and provider behavior:
- Find the Rest does **not** directly download arbitrary social-media candidate URLs.
- The candidate URL is sent only to the configured `FINDREST_CANDIDATE_MEDIA_ENDPOINT`.
- That gateway is responsible for authorization, licensing, provider terms, and returning only media the deployment is permitted to process.
- Only supported video content types are accepted.
- Candidate media is bounded by `FINDREST_CANDIDATE_MEDIA_MAX_BYTES` and processed in a temporary request directory.
- Raw candidate media is discarded after verification.

Configuration:
- `FINDREST_CANDIDATE_MEDIA_ENDPOINT`
- `FINDREST_CANDIDATE_MEDIA_KEY`
- `FINDREST_CANDIDATE_MEDIA_MAX_BYTES`

Verification:
- the existing robust visual,
- audio fingerprint,
- boundary visual/audio,
- transcript semantic,
- scene semantic

signals are now reused by both manual two-file verification and automatic candidate-URL verification through one shared verification pipeline.

The iPhone app now checks backend capabilities after finding a best match. When permitted candidate-media verification is available, it automatically verifies the best match and displays the existing multimodal verification result. If the gateway is not configured, the app does not upload the source merely to discover that fact.

Settings now reports **Automatic media verification** as a backend capability.

Current automated test count: 131 passing.


## v0.43 — Search intent

Find the Rest now asks what the user is actually trying to accomplish instead of treating every lookup as the same search.

New intents:
- Continue the story
- Watch the full original
- Find the original source
- Find other copies
- Identify what’s shown

The selected intent now changes:
- search-query ordering,
- candidate ranking priority,
- source/provenance preference,
- repost preference,
- continuation preference,
- visual/story-clue preference.

Intent is deliberately a bounded tie-breaker. It can reorder close candidates, but it cannot rescue a materially weak match and turn it into a confident answer.

The backend API now carries `intent` through:
- `/v1/analyze`
- `/v1/analyze-clues`
- `/v1/share-analyze`
- continuation watches and scheduled re-checks.

`AnalyzeResponse` now returns `search_intent`, and the iPhone app preserves that goal when creating a watch. Two watches for the same source may coexist when they have different goals—for example, one watching for the next part and another watching for a full original.

The SQLite watch schema migrates automatically with a new `intent` column, and active-watch uniqueness is now based on URL + scope + intent.

Current automated test count: 139 passing.


## v0.44 — Calibrated confidence

Find the Rest now separates a candidate's raw ranking score from the confidence it is allowed to present to the user.

The new confidence layer groups evidence into independent families:
- story semantics,
- continuation signal,
- creator identity,
- chronology,
- provenance,
- visual identity,
- audio identity,
- transcript continuity,
- scene continuity.

Closely related text signals are intentionally collapsed into one evidence family so a pile of similar metadata clues cannot masquerade as independent corroboration.

Calibration rules now:
- cap one-family results below the verified-match threshold,
- cap two-family results at moderate confidence,
- keep metadata-only results below the existing metadata ceiling,
- allow higher confidence only when independent direct-media evidence is available,
- cap "many weak signals" even when many fields are populated,
- suppress confidence further when contradiction evidence is substantial.

`AnalyzeResponse` now exposes:
- `confidence_grade` (`high`, `moderate`, `tentative`, `low`),
- `evidence_family_count`,
- `strong_evidence_family_count`.

The iPhone results screen now shows the calibrated match confidence, confidence grade, number of independent evidence families, and how many are strong.

The candidate's raw score remains available internally for ranking and diagnostics; calibration is a separate safety layer and does not erase the underlying evidence.

Current automated test count: 146 passing.


## v0.45 — Real continuation-watch scheduler deployment hook

Continuation watches now include a deployable authenticated scheduler runner instead of only a scheduler-ready API endpoint.

New runner:
- `backend/scripts/check_due_watches.py`

The runner:
- calls `POST /v1/watches/check-due`,
- sends the API key in `X-FindTheRest-Key` rather than placing credentials in the URL,
- supports either an explicit backend URL or a private host:port,
- retries one transient transport/server failure,
- validates the JSON response,
- logs only aggregate counts,
- never prints watch IDs, source URLs, match URLs, or credentials,
- exits non-zero for configuration, HTTP/transport, malformed-response, or partial-batch failures.

`render.yaml` now defines two services:
- `find-the-rest-api`
- `find-the-rest-watch-scheduler`

The cron job runs hourly at 5 minutes past the hour. Render private-network wiring supplies the API host/port, and `fromService.envVarKey` shares the generated API key with the scheduler without hardcoding it in the repository.

The watch interval remains independently controlled by `FINDREST_WATCH_INTERVAL_MINUTES` (default 360 minutes), so an hourly scheduler can safely discover which watches are actually due.

The due-watch endpoint documentation was also corrected: when a credible result is found and push delivery is configured, it attempts the notification rather than claiming push is unavailable.

Render Blueprint syntax was checked locally and the scheduler wiring is protected by regression tests.

Current automated test count: 150 passing.


## v0.46 — Feedback-to-regression protection

Beta feedback now produces a privacy-safe regression case signature in addition to the ordinary acknowledgement.

New backend module:
- `backend/app/feedback_cases.py`

Each case stores only:
- a short hash of the search ID,
- verdict,
- source platform,
- search intent,
- result state,
- confidence bucket,
- confidence grade,
- independent evidence-family counts,
- a short hash of the best-match URL when one exists.

It deliberately does **not** store:
- raw source URLs,
- raw best-match URLs,
- screenshots,
- video,
- transcripts,
- OCR text,
- titles,
- creator names,
- search queries,
- filenames,
- free-form user text.

The older feedback JSONL store was hardened as well: `best_match_url` is no longer persisted raw and is replaced by a short SHA-256 fingerprint.

New protected endpoint:
- `GET /v1/feedback-summary`

The summary reports:
- total feedback cases,
- verdict counts,
- failure-case count,
- high-confidence wrong-answer count,
- the most common failure patterns by platform, intent, result state and confidence band.

High-confidence wrong answers are deliberately surfaced as the highest-priority calibration failures.

The iPhone feedback buttons now send the result's search intent, state, calibrated confidence grade and independent evidence-family counts. The UI disclosure has been updated to explain that beta feedback sends coarse quality signals rather than user media or extracted content.

Retention is bounded by:
- `FINDREST_FEEDBACK_CASES_MAX` (default 2000).

Current automated test count: 156 passing.


## v0.47 — Real search-coverage accounting

The “likely not posted yet” state now depends on **actual completed public searches**, not merely on whether a Brave Search API key exists.

Each analysis now tracks:
- whether a broad-search provider is configured,
- planned searches attempted,
- searches completed successfully,
- searches that failed,
- completion ratio,
- whether coverage is broad enough to support the nonpublication hint.

A source is considered broad enough for the cautious “may not have been posted yet” state only when:
- a provider is configured,
- at least three planned searches completed,
- at least 60% of attempted searches completed successfully.

If the provider is configured but calls fail, time out, or no plans actually run, Find the Rest now falls back to **No verified match** rather than implying that the continuation may not exist yet.

`AnalyzeResponse` now includes `search_coverage`.

The iPhone results screen displays completed/attempted search coverage. When coverage is incomplete, it explicitly says Find the Rest will not infer that the missing continuation has not been posted.

Privacy-safe diagnostics now record only aggregate search coverage counts/ratios, never queries or URLs.

Injected/custom hunters written before v0.47 remain compatible; when they do not report coverage, the service treats coverage as unknown rather than assuming it was broad.

Current automated test count: 160 passing.


## v0.48 — Reverse-image gateway hardening

The external reverse-image/source-discovery path is now substantially safer for beta deployment.

The configured reverse-image gateway now requires:
- HTTPS,
- a valid hostname,
- no username/password embedded in the endpoint URL,
- optional exact-host allowlisting via `FINDREST_REVERSE_IMAGE_ALLOWED_HOSTS`.

Provider redirects are rejected rather than followed so authorization headers and user-shared image bytes cannot be forwarded to an unexpected host.

Provider responses now require a JSON content type and are bounded by:
- `FINDREST_REVERSE_IMAGE_MAX_RESPONSE_BYTES`
- default 2 MB
- allowed range 64 KB to 8 MB.

Provider fields are length-bounded before becoming candidates.

Reverse-image results now use the same canonical URL normalization as the main candidate hunter, so tracking variants such as `utm_*`, `fbclid`, `gclid`, `si`, and `feature` collapse into one candidate while meaningful content query parameters remain intact.

The screenshot-discovery fusion path now also uses canonical URL deduplication, improving multimodal agreement when OCR discovery and reverse-image discovery return differently tracked links to the same underlying source.

The backend capability flag now reports reverse-image search as configured only when the endpoint passes the HTTPS/host validation.

Current automated test count: 165 passing.


## v0.49 — Candidate-media gateway hardening

The licensed/permitted candidate-media gateway used for automatic verification now has the same deployment-grade trust controls as reverse-image discovery.

The gateway configuration now requires:
- HTTPS,
- a valid hostname,
- no username/password embedded in the endpoint URL,
- optional exact-host allowlisting through `FINDREST_CANDIDATE_MEDIA_ALLOWED_HOSTS`.

Automatic verification capability is reported as enabled only when that configuration passes validation.

Candidate URLs sent to the gateway are now restricted to ordinary HTTP/HTTPS URLs and reject:
- `localhost`,
- `.localhost`,
- loopback IPs,
- private IP ranges,
- link-local addresses,
- reserved/multicast/unspecified literal IPs,
- embedded URL credentials,
- non-web schemes such as `file:`.

This prevents Find the Rest from becoming an SSRF relay into local/internal infrastructure. The trusted candidate-media gateway remains responsible for its own DNS-resolution and provider authorization controls.

Gateway redirects are rejected rather than followed, so authorization headers and candidate URLs cannot be forwarded to another host.

Media responses now:
- accept only the supported video MIME types,
- honor and validate `Content-Length` when provided,
- reject declared or actual payloads above `FINDREST_CANDIDATE_MEDIA_MAX_BYTES`,
- reject invalid content lengths,
- remain confined to the request's temporary working directory.

The gateway still never causes Find the Rest itself to download arbitrary social-media URLs directly.

Current automated test count: 171 passing.


## v0.50 — Verification-aware reranking

Automatic permitted-media verification now affects candidate ordering instead of being displayed as a separate after-the-fact score.

New backend module:
- `backend/app/verification_rank.py`

New protected endpoint:
- `POST /v1/verify-ranked-candidates`

The endpoint accepts the already-ranked candidate set plus the user-provided/permitted source video and then:
- attempts verification only through the configured licensed/permitted candidate-media gateway,
- verifies only the top candidates,
- fuses multimodal evidence into a separate adjusted ranking score,
- can promote a strong/likely verified result,
- can demote a candidate that media verification fails to support,
- can allow a previously second-ranked candidate to become the leading result,
- preserves the original search score for transparency.

Verification is deliberately bounded:
- strong verification produces only a modest positive adjustment,
- likely verification produces a smaller adjustment,
- possible verification mostly holds position,
- failed verification demotes but does not erase strong story/provenance evidence.

Provider cost and latency are capped by:
- `FINDREST_VERIFICATION_RERANK_MAX_CANDIDATES`
- default 2
- absolute maximum 3.

The iPhone now automatically sends the top two search candidates through this verification-rerank pass when permitted candidate media is available. The displayed **Best match** switches to the verification-aware leader when the evidence supports that change.

The UI shows:
- verification-aware score,
- original search score,
- whether media verification promoted, held, or demoted the displayed candidate.

If media evidence changes the leading result, the user is explicitly told that the top candidate changed after comparison.

The original ranking remains available; media verification is an additional bounded evidence layer rather than a replacement for provenance, story, creator, chronology, or contradiction evidence.

Current automated test count: 178 passing.


## v0.51 — Intent-aware outcomes

Result states, messages, and recommended actions now match the goal the user selected.

Previously, search planning and ranking were intent-aware, but the final outcome layer still spoke mainly in continuation/full-original language. This build completes that separation.

Dedicated successful states now include:
- `continuation_found`
- `full_original_found`
- `original_source_found`
- `copies_found`
- `identification_found`

Dedicated no-result states now include:
- `no_verified_match`
- `no_verified_full_original`
- `no_verified_source`
- `no_verified_copy`
- `no_verified_identification`

The classifier now requires goal-specific evidence before claiming success:
- original-source searches require provenance/originality support,
- alternate-copy searches require repost/reverse-image/copy evidence,
- identify-shown searches require visible-text, visual, story, or semantic identification support,
- full-original searches require full/original evidence rather than merely any credible related candidate.

A credible but goal-mismatched candidate is now reported as `related_only` with wording specific to the selected goal.

The cautious `likely_not_posted_yet` state is now exclusive to **Continue the story** searches. It can no longer appear while the user is asking to find the original source, another copy, a full version, or identify what is shown.

The iPhone result labels and action labels have been updated for all new states. Continuation watches are now offered only for the continuation goal.

Watch execution and push completion logic now recognizes all goal-specific successful states through a shared success-state helper, so saved non-continuation goals can complete correctly as well.

Current automated test count: 186 passing.


## v0.52 — Privacy-safe appearance matching

Find the Rest can now compare whether two permitted clips likely show the same visible person/appearance **without trying to identify who that person is**.

New backend module:
- `backend/app/appearance.py`

New protected endpoint:
- `POST /v1/compare-appearance`

The matcher compares broad visual regions across multiple frames:
- face/head-region appearance,
- clothing/upper-body appearance,
- surrounding scene appearance.

It is intentionally pairwise and request-scoped:
- no names,
- no stranger identification,
- no enrollment,
- no persistent face database,
- no reusable biometric profile,
- no retained face embedding.

The “face-region” signal is a local visual-region heuristic, not an identity claim.

Appearance matching is mirror-tolerant and samples multiple frames. Scene similarity receives a deliberately small weight so “same room/background” by itself cannot imply the same visible person.

Appearance evidence is now part of the existing multimodal verification fusion alongside:
- robust visual similarity,
- audio fingerprint,
- visual/audio boundary continuity,
- transcript/story semantics,
- scene semantics.

The new appearance signal receives a bounded weight and can strengthen agreement, but it cannot independently establish a verified match.

Multimodal verification responses now expose:
- `appearance_similarity`
- `face_region_similarity`
- `clothing_region_similarity`

The iPhone verification screen displays these signals and explicitly states that appearance matching does not identify or name a person.

All processing remains limited to user-provided or otherwise permitted media and temporary request storage.

Current automated test count: 193 passing.


## v0.53 — Object, logo, scene, and clothing clues

Standalone screenshot/video discovery now has a dedicated semantic visual-clue layer for cases where OCR, faces, or titles are not enough.

New backend module:
- `backend/app/vision_clues.py`

New protected endpoint:
- `POST /v1/extract-visual-clues`

The visual-clue layer can represent:
- objects,
- logos/brands,
- scene/environment labels,
- clothing/uniform cues.

A provider-neutral gateway can be configured with:
- `FINDREST_VISION_CLUES_ENDPOINT`
- `FINDREST_VISION_CLUES_KEY`
- `FINDREST_VISION_CLUES_ALLOWED_HOSTS`
- `FINDREST_VISION_CLUES_MAX_RESPONSE_BYTES`

The gateway requires HTTPS, rejects embedded URL credentials and redirects, supports an exact hostname allowlist, requires JSON responses, and caps response size.

Without an external semantic provider, Find the Rest still derives coarse local scene descriptors such as:
- bright/dark/mid-tone,
- colorful/muted,
- visually dense/simple.

These local descriptors intentionally do **not** claim object identity.

Screenshot discovery now:
- generates web searches from recognized logos, objects, scenes, and clothing,
- scores candidates using `visual_clue_match`,
- records matched visual details in candidate evidence,
- fuses semantic visual clues with OCR and reverse-image evidence,
- gives a bounded multimodal-agreement boost when independent clue paths converge on the same canonical URL.

`MediaDiscoveryResponse` now includes:
- `visual_objects`
- `visual_logos`
- `visual_scenes`
- `visual_clothing`

The iPhone screenshot result screen now shows those visual clues and matched objects/logos/scenes/clothing alongside OCR/story evidence.

This makes “Identify what’s shown” and screenshot-source discovery materially stronger for things like vehicles, machinery, storefronts, uniforms, signs, furniture, tools, and distinctive environments when a configured semantic visual provider is available.

Current automated test count: 200 passing.


## v0.54 — Beta hardening and adversarial self-check

This build shifts Find the Rest from feature expansion toward deliberate pre-beta failure testing.

The deterministic adversarial benchmark grew from 14 to 23 cases and now additionally checks:
- misleading Part 2 labels with story-anchor drift,
- fake “original” wording without provenance,
- same-creator/same-topic videos that are not continuations,
- intent mismatch between continuation evidence and original-source searches,
- publication-hint leakage into non-continuation intents,
- query-parameter ordering and tracking dedupe,
- weak related candidates that must stay related,
- copy-specific success behavior,
- identify-shown candidates that lack actual identification evidence.

One new adversarial fixture initially failed because it did not contain a genuine conflicting story anchor. The fixture was corrected so it now tests a real contradiction rather than weakening the guard to make the benchmark pass.

New backend module:
- `backend/app/beta_readiness.py`

New protected endpoint:
- `GET /v1/beta-readiness`

The readiness self-check reports critical and optional deployment gates. Critical gates are:
- 100% deterministic adversarial benchmark pass rate,
- non-default backend API authentication,
- public web discovery configured,
- built-in watch storage available.

Optional readiness gates report:
- YouTube discovery,
- reverse-image discovery,
- automatic candidate-media verification,
- object/logo/scene recognition,
- scheduler inclusion,
- push delivery.

`beta_ready` becomes true only when every critical gate passes. Optional provider gaps remain visible without falsely declaring the core build broken.

This endpoint is intentionally conservative and does not claim that configuration checks replace TestFlight/device testing or real-world adversarial examples.

Current deterministic benchmark: 23/23 passing.
Current automated test count: 205 passing.


## v0.55 — Release-candidate hardening

This build intentionally adds no new discovery feature. It hardens the product boundary and makes beta readiness visible from the iPhone.

### iPhone release check

Settings now includes **Release readiness** and a **Run Release Check** button.

It reads the protected `/v1/beta-readiness` self-check and displays:
- overall core beta status,
- critical gates passed,
- total gates passed,
- every individual gate,
- whether a failed gate is required or optional,
- the concrete configuration issue for failed gates.

A successful **Save & Test Connection** now automatically refreshes both backend capabilities and release readiness.

### Better failure handling

Backend health checks now have an explicit timeout and first validate that a real backend URL is configured.

The iPhone API client now translates common HTTP failures into useful beta-facing messages:
- invalid API key,
- media too large,
- unsupported media,
- rate limiting,
- temporary backend/server failure,
- other HTTP errors with safe server detail when available.

Release-readiness and capability requests also use bounded timeouts.

### Production HTTP boundary

The backend no longer enables wildcard browser CORS by default.

Browser CORS is disabled unless `FINDREST_CORS_ORIGINS` is explicitly configured. When enabled, methods and headers are restricted to the Find the Rest API surface.

Optional production Host-header filtering is available through:
- `FINDREST_TRUSTED_HOSTS`

The beta-readiness self-check now reports both CORS policy and trusted-host filtering as deployment-hardening gates.

The public `/health` response no longer exposes internal cache statistics.

### Validation

- deterministic adversarial benchmark remains 23/23,
- 210 automated tests pass,
- iOS plist and entitlement validation passes,
- no major discovery feature was added in this release-candidate build.

This is the point at which the codebase should move to deployment, signing, provider configuration, TestFlight, and real-world break testing rather than continued feature expansion.
