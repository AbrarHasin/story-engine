# Research: News Lens (003)

**Date**: 2026-10-16 | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

Planning only. No LLM calls, no sign-ups, no API keys were used. Prices and limits come from the sources listed at the end (checked 2026-10-16); third-party figures are marked as such and must be re-checked on the vendor page before money is spent.

## R0. Product name (human picks)

| Name | Meaning | Note |
|---|---|---|
| **Parallax** (recommended) | Seeing one object from several positions; the distance between views is information. | Strong metaphor for "mainstream vs other side, then measure". Common word: trademark and domain unchecked. |
| **Clearsight** | Plain, reader-facing promise of clarity. | Generic; several companies use it. |
| **OnRecord** | What is on the record vs what is said. | Fits journalists and court-record angle; `onrecord` domains likely taken. |
| News Lens (working) | Lens on the news. | Descriptive; many "News Lens" products exist (e.g. The News Lens, Taiwan). Avoid for launch. |

No trademark or domain search was done (would need web lookups the human should run with a registrar).

## R1. ADR-001: reuse the Story Engine repo or start a new one

**Decision (recommended)**: **new repository `news-lens`**, created by copying the pilot's platform layer (`backend/app/core`, `llm`, `payment`, `cache`, `api/v1/auth.py`, alembic setup, Docker local stack, CI, `infra/` SAM skeleton from spec 002) at a tagged commit, with its own constitution v1. Extract a shared package only when a third product needs the same code (rule of three).

| Option | For | Against |
|---|---|---|
| A. Add News Lens inside `story-engine` (new graph + routes + pages) | Zero duplication; one CI; fastest first commit. | Story Engine is live; News Lens adds ingestion workers, legal audit data (6-year retention), many new tables and a different risk profile; the pilot constitution (3-5 bullet sub-agents, per-story cost) does not fit; one deploy breaks both. |
| **B. New repo seeded from the pilot (chosen)** | Clean domain, own constitution, own release cadence and data retention; pilot stays stable; the copied code is small (auth, quota, adapter, cache are a few hundred lines each). | Fixes to shared code must be ported by hand (mitigation: keep a `PLATFORM.md` list of copied files with source commit; port fixes in both). |
| C. Monorepo with a shared `platform` package and two apps | No duplication long term. | Packaging and CI work up front (about 4-6 pd) for two products, before News Lens has proven itself. Revisit at Phase 4. |

Spec 003 stays in `story-engine/specs/` as the planning record; task T001 moves it into the new repo.

## R2. Retrieval

### R2.1 Sources and APIs

| Source | Use | Access and limits (2026-10-16) | MVP |
|---|---|---|---|
| Curated RSS directory (vault `Knowledge/News-Sources/Global-News-RSS-API-Directory.md`) | Background ingestion, recent news, outlet identity | 171 validated RSS rows, 29 state-media labels, 15+ regions; +64 more passing feeds in `hive/research/news-feeds-additions-2026-10-16.json`. Validation 2026-10-16: HTTP 200, parses, newest entry <= 30 d. | Yes |
| GDELT DOC 2.0 API | Keyword search of world news, timeline volume | Free, no key. Article-list mode returns only the last ~3 months of the window; timeline modes reach back to 2017. Community-reported limit: one request every 5 s (HTTP 429 otherwise). | Yes |
| Wikipedia / Wikimedia REST + Action API | Historical background, timelines, the article's reference list as a source map | Free; identify with a User-Agent; content CC BY-SA (attribute, link). | Yes |
| Internet Archive Wayback (CDX + availability API) | Archived copies of old or vanished articles; stable citation links | Free; polite rate. | Yes |
| Google Fact Check Tools API `claims:search` (v1alpha1) | Existing fact-checks (ClaimReview) | Free with an API key; params `query`, `languageCode`, `maxAgeDays`, `reviewPublisherSiteFilter`, `pageSize`, `pageToken`. Quota per Cloud project (check console). | Yes |
| CourtListener REST v4 (Free Law Project) | US court opinions, dockets (RECAP) for legal topics | Free token; since May 2026 5/min, 50/h, 125/day per account (membership raises it). Cache aggressively. | Yes (low volume) |
| NewsAPI.org | Broad keyword search, 5-year archive | Free Developer plan is dev-only (24 h delay, 1 month back, no production use). Business $449/month, 250k requests, $0.0018 overage. | Flag, Phase 4 |
| GNews API | Keyword search | Free 100/day non-commercial; Essential about EUR 40-50/month for 1,000/day (third-party figures). | Flag, Phase 4 |
| Brave Search API (news) | Web + news search fallback | About $5 per 1,000 requests; free tier removed Feb 2026 (third-party reports). | Flag, Phase 4 |
| Guardian Open Platform | Full text of Guardian articles with API terms | Free key, non-commercial tier; commercial needs agreement. | No |

**MVP stance**: free and open sources only. Every connector sits behind one `SearchProvider` interface so paid APIs drop in later without graph changes.

### R2.2 Full-text extraction

- **trafilatura** (Apache-2.0 since v1.8.0; earlier versions GPLv3+) for main-text, metadata, date extraction. GPL-3.0 compatible.
- Fetch only when `robots.txt` allows our User-Agent (`NewsLensBot/0.1 (+https://<domain>/bot)`), honour `noarchive`/`nosnippet` meta and `X-Robots-Tag`, per-domain concurrency 1 and delay >= 2 s, cache by URL.
- Paywalled or blocked: keep headline, RSS lede, link; mark `extraction_basis = metadata_only`.
- Store `content_hash` (SHA-256 of normalised text) and `fetched_at` for every document: the anchor for quote validation (FR-019).

### R2.3 Dedup, clustering, timeline

1. Canonical URL (strip tracking params, resolve `rel=canonical`).
2. Near-duplicate and syndication: MinHash LSH on 5-word shingles (`datasketch`, MIT) at Jaccard >= 0.8 -> one **source family** (wire copies of AP/AFP/Reuters count once).
3. Event clustering: MiniLM-L6 embeddings (already used by the pilot's semantic cache, 384-d, pgvector) of title + lede; agglomerative or HDBSCAN (BSD) clustering inside the topic's result set; cluster date = median published date; label from the most central headline (no LLM).
4. Timeline = clusters ordered by date; for historical topics, Wikipedia section dates and court filing dates add anchor events.

### R2.4 Recency vs historical

`topic_type` from the resolver drives retrieval:

| Type | Example | Retrieval mix | Report freshness |
|---|---|---|---|
| `breaking` | event < 48 h | local index (last 48 h) + GDELT 1 d | 1 h |
| `recent` | weeks-months | local index + GDELT 3 months + Fact Check Tools | 24 h |
| `historical` | Michael Jackson allegations 1993-2019 | Wikipedia article + its references, Wayback copies, CourtListener (e.g. the 2005 People v. Jackson case is California state court: use news archives + Wikipedia references; federal/civil filings via RECAP), Fact Check Tools, GDELT timeline for coverage peaks, local index for the latest developments | 30 d |

Worked example (Michael Jackson): resolver -> entities {Michael Jackson (deceased 2009), Wade Robson, James Safechuck, Jordan Chandler, Gavin Arvizo, Jackson estate}, span 1993-present, type `historical`, living-party flag on accusers and estate. Clusters: 1993 allegation and settlement, 2003 arrest, 2005 trial acquittal on all counts, 2009 death, 2013-2017 Robson/Safechuck suits, 2019 *Leaving Neverland*, later appeals and rulings. Mainstream account = established coverage + court records; other positions = estate and supporters' position (documentary disputed, acquittal), accusers' position; "also circulating" = unsupported fringe claims. This topic is in the red-team set (R6).

## R3. Perspective classification

**Principle**: positions are about **claims and stances**, not about outlets. Tier labels describe sources; perspectives group what is being asserted.

1. **Source tiers** (FR-011) seeded from the vault directory: `state` from its state-media flags (29 rows), `established` for outlets meeting published criteria (named editor, corrections policy, physical address, track record), `factchecker` from the IFCN signatory list (about 170 organisations; the list is maintained at ifcncodeofprinciples.poynter.org), `primary` by document type (court, government, official statement, filing), `independent` default for other named outlets, `social` for user content. Inputs, not authorities: Wikipedia's "Reliable sources/Perennial sources" table (CC BY-SA) and IFCN status. No paid ratings (NewsGuard, Ad Fontes) in MVP. Every assignment has rationale and audit history; tier changes go through review.
2. **Stance detection**: Haiku labels each source family's lede against the resolver's 2-4 key questions (e.g. "Did the alleged abuse happen?") with stance `affirms | disputes | neutral | other` and a short position key; positions = groups of (question, stance) with holders.
3. **Mainstream account** = position with the largest `established` + `primary` support (FR-012). Shown first but its claims are rated like everyone else's.
4. **Other sides** gate (FR-013): identifiable party with standing, or >= 5 % coverage share. Otherwise "Also circulating".
5. **Against false balance**: cards show coverage share and an evidence-support bar (share of the position's claims rated `Verified`/`Mostly true`), ordered by evidence then coverage; no symmetric two-column layout.
6. **Against amplification**: no previews, `nofollow ugc`, no quoting beyond the claim text for `social` and low-support sources; claims from them are shown already rated ("prebunk" framing: rating first, claim second).
7. **Who says what**: each position lists holders with links (article, statement, filing), tier chip, and date.

## R4. Claim extraction and fact-check pipeline

1. **Extract** (Haiku, cap 1,200 output tokens): from the top 2 source families per position (max 8 excerpts of about 700 tokens), JSON list of `{claim, speaker, source_article_id, checkable, living_person_named}`; dedup by embedding cosine >= 0.88; keep max 12 by centrality (how many families repeat it) and risk.
2. **Existing fact-checks first**: `claims:search` with the claim text (and entity names); candidate reviews re-ranked by embedding similarity; accept >= 0.85 and same entities. Map `textualRating` (free text such as "False", "Pants on Fire", "Missing context", "Mostly True") to our scale via a published mapping table (`contracts/rating-scale.md`), Haiku only for unmapped strings (cap 50 tokens). A matched fact-check is evidence of tier `factchecker`, shown first.
3. **Evidence retrieval** (no LLM): per claim, queries built from claim entities + key terms against the local index, Wikipedia, Wayback and the topic's fetched documents; passage split (about 120-word windows), rerank by embedding similarity; top 6 passages from at least 3 source families where available.
4. **Verify** (Haiku default; Sonnet 5.5 for `living_person_named` allegations and claims where Haiku confidence is `low` and coverage is high, max 3 per report): input = claim + numbered passages as quoted data; output JSON `{rating, confidence, reason, evidence:[{passage_id, quote, stance}]}`; cap 300 tokens.
5. **Validate** (code, no LLM): every `passage_id` exists; every `quote` is a verbatim substring of the stored text of that passage's document (after whitespace normalisation); FR-020 independence rule (distinct source families, at least one strong tier); FR-021 living-person hold. Fail -> one retry with the validator message -> `Unproven` ("insufficient verified evidence").
6. **Rating scale**:

| Rating | Definition |
|---|---|
| Verified | Supported by at least two independent strong sources (primary, established or fact-checker); no credible contrary evidence. |
| Mostly true | Supported, but with minor inaccuracies or missing context that does not change the core. |
| Mixed | Credible sources materially conflict, or the claim is partly accurate and partly not. |
| Unproven | Evidence is insufficient, thin, or only from the claimant. Default when unsure. |
| Misleading | Contains accurate elements but presented to give a false impression, or key context omitted. |
| False | Contradicted by at least two independent strong sources, or by a primary record. |
| Not checkable (tag) | Opinion, prediction, value judgement, or unfalsifiable. Not rated. |

Confidence: `high` (3+ independent strong families agree), `medium` (2), `low` (1 or conflicting); shown next to every rating.

7. **Human review**: queue ordered by risk; reviewer can approve, change (new Rating version, actor `human:<id>`) or reject (claim hidden). Held claims show "pending review" to readers.

## R5. Trust and legal (not legal advice; open question 2 asks for a media-law review)

- **Defamation**: a site that writes and publishes its own (AI-generated) assessments is the speaker. US Section 230 protects hosting third-party content, not a platform's own content, and commentators expect AI output published under the site's name to be treated as its own speech; the law is unsettled (2025-2026 suits against AI companies). UK and EU law give fewer defences (UK Defamation Act 2013: truth, honest opinion, public interest). Controls: attribution language for allegations; ratings framed as assessments of published evidence with confidence; FR-020/021 thresholds and human hold for living persons; no rating of private individuals; corrections and replies (FR-023); audit log (FR-022); disclaimers (FR-025). Deceased subjects (Michael Jackson) cannot generally be defamed in the US or UK, but living accusers, family and estate can be affected: the living-party rule applies to them.
- **Right of reply**: named parties submit a reply; accepted replies display beside the claim; the claim goes back to review.
- **Copyright**: show headline, link, and short quotes (<= 300 characters, <= 3 per source per report) for commentary and verification; never full text; Wikipedia content attributed under CC BY-SA. Internal full-text storage for verification is a 90-day window pending legal advice (open question 7).
- **Robots and terms**: honour robots.txt, meta robots and `X-Robots-Tag`; API terms per provider (NewsAPI Developer plan forbids production use; GNews free plan non-commercial; Guardian commercial use needs agreement). Store the `extraction_basis` per article.
- **Takedown**: notice form (DMCA-style fields), acknowledgement, review, action (snippet hidden, link kept), counter-notice, all audited.
- **Audit log**: append-only table + daily hash chain (each day's digest includes the previous one) so tampering is detectable; 6-year retention (covers UK/US limitation windows for most claims; confirm with counsel).

## R6. Evaluation (no LLM calls during planning)

- **Gold set** (Phase 1, task T059): at least 300 claims with known verdicts:
  - 200 sampled from ClaimReview records via Fact Check Tools across at least 8 IFCN publishers (AFP Fact Check, PolitiFact, Full Fact, Snopes, Reuters Fact Check, Lead Stories, Africa Check, Boom), stratified by verdict and topic; verdicts mapped with the R4 table. The verifier must be run with the publisher's own article excluded from evidence (no answer leakage).
  - 100 from public research sets where licences allow evaluation use: AVeriTeC (real-world claims with evidence; check licence), LIAR (PolitiFact statements), FEVER (Wikipedia-based, CC BY-SA). Licences to verify before use.
- **Metrics**: exact agreement and within-one-step agreement on the ordinal scale; macro-F1; `True`-vs-`False` inversion rate; calibration (expected calibration error by confidence level); `Unproven` rate on claims with thin evidence (should be high); citation validity (resolves + quote verbatim, target 100 %); unsupported-sentence rate in narratives; living-person hold recall (target 100 %); cost and latency per report.
- **Red-team topics** (20, scripted): Michael Jackson allegations; vaccine safety claims; a disputed election result; Israel-Palestine casualty figures; a celebrity death hoax; a satire article taken as real; a breaking event with no facts yet; a private individual (must refuse); a minor (must refuse / redact); prompt injection embedded in an article; coordinated low-tier flooding of one claim; non-English-only coverage; a deleted source; a claim where mainstream outlets were wrong and later corrected.
- **Budget**: CI runs the pipeline on recorded fixtures with a mocked LLM ($0). One budgeted live evaluation run at Phase 1 end: 300 claims x about $0.0006 per verification (Haiku) is about $0.20; full red-team reports 20 x $0.006 is about $0.12. Needs the human's explicit spend approval (current floor cap: $0.10 total for real generations).

## R7. Cost per query (modelled, not measured)

Prices per 1M tokens (vault `Projects/Story-Engine/Model-Cost-Analysis.md`, checked 2026-10-16): Claude Haiku 5.5 $0.10 in / $0.50 out; Claude Sonnet 5.5 $2.00 / $10.00. Bedrock prices for these models were **not verified** (aggregators list Haiku 4.5 on Bedrock at about $1 / $5, ten times the Haiku 5.5 API list price), so production cost carries a sensitivity line.

| Stage | Model | Input tok | Output tok | Cost (Haiku) |
|---|---|---|---|---|
| Topic resolver | Haiku | 400 | 150 | $0.00012 |
| Stance / perspective (30 ledes) | Haiku | 4,000 | 700 | $0.00075 |
| Claim extraction (8 excerpts) | Haiku | 6,000 | 900 | $0.00105 |
| Fact-check rating mapping (fallback) | Haiku | 1,000 | 200 | $0.00020 |
| Verification (10 claims) | Haiku | 16,000 | 2,200 | $0.00270 |
| Narrative (mainstream + positions) | Haiku | 5,000 | 1,300 | $0.00115 |
| **Total, cold report, all Haiku** | | **32,400** | **5,450** | **~$0.0060** |
| Premium: 3 high-risk claims verified on Sonnet 5.5 | | | | **~$0.021** |
| At output caps (worst case, all Haiku) | | ~45,000 | ~7,900 | ~$0.0085 |
| Cache hit (report) | none | 0 | 0 | $0 |
| Blended, 40 % report cache hits, 10 % premium | | | | **~$0.0045** |
| Sensitivity: Bedrock at 10x Haiku API price | | | | ~$0.06 cold |

Other per-query costs: search APIs $0 in MVP (GDELT, Wikipedia, Wayback, Fact Check Tools, CourtListener free). With NewsAPI Business, $449/month fixed: $0.045 per report at 10k reports/month, $0.0018 per extra request beyond 250k. Embeddings and clustering run locally on CPU ($0).

Hosting: local Docker $0. AWS Option S (spec 002) is about $12.60/month for the pilot, but News Lens ingestion every 30 min would keep Aurora Serverless v2 awake (no auto-pause at 0 ACU): about 0.5 ACU always on is roughly $45/month at about $0.12 per ACU-hour (us-east-1, verify). Options: batch ingestion every 2-4 h, buffer feeds in S3 and write in bursts, or accept the cost (decision for Phase 3).

## R8. Phases and effort (person-days, 1 developer + agents; +25 % contingency not included)

| Phase | Scope | pd |
|---|---|---|
| P0 Foundations | New repo from pilot (ADR-001), constitution v1, CI, migrations for the data model, source registry import from the vault directory, connectors interface | 5 |
| P1 MVP | Ingestion (2.5), on-demand connectors (3), extraction with robots policy (2), dedup/clustering/timeline (2.5), resolver + perspectives (2.5), claims + ClaimReview matching (3), verifier + validator + rules (4), graph + SSE + API + caches (3), report UI with claim drawer, source labels, methodology page (5), disclaimers + minimal review hold + audit log (2.5), evaluation harness + gold set + red team (4) | 34 |
| P2 Trust ops and journalists | Corrections/reply/takedown (3), review workspace (3), export (1.5), watches + alerts (3), journalist plan + quotas (1), re-verification scheduler (1.5) | 13 |
| P3 Production | AWS Option S reuse: ingestion on EventBridge Scheduler + Lambda, Aurora awake-cost decision, Bedrock adapter (shared with spec 002 T044), legal-review fixes | 8 |
| P4 Scale | Multilingual evidence with translation (5), paid search APIs (2), social-claim tracking (4), embeddable widget / browser extension (5) | 16 |
| **Total** | MVP = P0 + P1 = **39 pd** (about 49 with contingency) | **76** |

## R9. Top risks

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| 1 | Wrong rating about a living person (defamation) | Legal claim, reputational damage | FR-020/021 thresholds, attribution language, human hold, replies, corrections, audit log, media-law review before public launch |
| 2 | Hallucinated or misattributed citations | Trust collapse | Only fetched documents citable; verbatim quote validation; `Unproven` on failure; SC-002 gate in CI on fixtures |
| 3 | False balance or amplifying misinformation; tier list seen as biased | Harm, credibility | Stance-based positions with standing/coverage gate, evidence-weighted layout, no-preview links, published tier criteria with audit and appeal |
| 4 | Retrieval gaps (GDELT 3-month window, CourtListener 125/day, paywalls, bot blocks) make reports thin | Low quality, many `Unproven` | Mix of archive sources, caching, honest `Unproven`, Phase 4 paid APIs |
| 5 | Verification accuracy unmeasured; Bedrock price unverified | Quality or cost surprise | Gold set + red team before launch; cost telemetry per stage; Bedrock sensitivity line; Haiku-first with capped premium escalation |

Also: copyright/ToS disputes (snippet policy, takedown), prompt injection in fetched pages (data delimiting + structural validation), Aurora awake cost in production (R7).

## R10. Pipeline design decisions (summary for plan.md)

- D1 New repo (ADR-001). D2 Free sources only in MVP. D3 Background RSS ingestion + on-demand search per query. D4 Haiku everywhere, Sonnet only for at most 3 high-risk claims per report. D5 Existing fact-checks before own verification. D6 Code-level citation validator, never trust model citations. D7 Two cache levels (report by topic, verdict by claim) with TTLs from FR-031. D8 SSE event contract extends the pilot's (`start`, `stage`, `node_complete` kept for compatibility, new `topic`, `timeline`, `perspective`, `claim`, `rating`, `done`, `error`). D9 Human hold for living-person allegations from day one.

## Sources (fetched or searched 2026-10-16)

- Google Fact Check Tools `claims:search` reference: https://developers.google.com/fact-check/tools/api/reference/rest/v1alpha1/claims/search
- GDELT DOC 2.0 notes: https://blog.gdeltproject.org/doc-2-0-updates-1-5-year-searching-and-updated-mobile-interface/ ; client notes: https://pypi.org/project/gdeltdoc/
- NewsAPI pricing and terms: https://newsapi.org/pricing , https://newsapi.org/terms
- GNews pricing (third-party): https://www.socialcrawl.dev/blog/best-google-news-apis-2026
- Brave Search API pricing: https://api-docs.search.brave.software/pricing ; free-tier change: https://www.implicator.ai/brave-drops-free-search-api-tier-puts-all-developers-on-metered-billing/
- CourtListener API v4 limits: https://wiki.free.law/c/courtlistener/help/api/rest/v4/overview ; https://learn.microsoft.com/en-us/connectors/courtlistener/
- IFCN code and signatories: https://ifcncodeofprinciples.poynter.org/process , https://ifcncodeofprinciples.poynter.org/signatory-benefits
- trafilatura licence: https://github.com/adbar/trafilatura , https://trafilatura.readthedocs.io/
- Section 230 and generative AI: https://www.everycrsreport.com/reports/LSB11097.html ; https://www.nolo.com/legal-encyclopedia/artificial-intelligence-defamation-and-libel-is-anyone-liable.html ; https://minnlawyer.com/2025/11/17/ai-defamation-lawsuits-libel-liability/
- Bedrock Haiku 4.5 price (third-party, for sensitivity only): https://www.bacancytechnology.com/blog/aws-bedrock-pricing
- Model prices: vault `Projects/Story-Engine/Model-Cost-Analysis.md` (citing platform.claude.com/docs/en/about-claude/pricing)
- Source directory: vault `Knowledge/News-Sources/Global-News-RSS-API-Directory.md`; hive `research/news-feeds-validation-2026-10-16.json`, `research/news-feeds-additions-2026-10-16.json`
