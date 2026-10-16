# Feature Specification: Parallax

**Feature Branch**: `news-lens-plan` (Spec Kit feature `003-parallax`)

**Created**: 2026-10-16

**Status**: Approved for build (Phase P0 started 2026-10-16). Clarified with best judgment, then updated with the human's decisions.

**Human decisions (2026-10-16)**: (1) name **Parallax**; (2) ADR-001 approved, new repo `parallax` seeded from Story Engine; (3) **no human review queue**: every claim is shown with its rating, model confidence and source links under an "Automated assessment, not reviewed by a person" label, with the automatic safeguards kept (only fetched documents citable, verbatim quotes, FR-020 independence rule, attributive wording, corrections / right-of-reply contact link); (4) media-law review deferred (the product is a review report); `docs/legal/source-terms.md` stays because it governs what may be fetched. Defaults accepted: free sources only, no social-media claims in MVP, quotes-only retention (FR-034).

**Input**: User description: "A website where a user asks about a news topic (example: 'Michael Jackson controversy') and gets (1) the mainstream-media account, (2) the controversial / other side(s), and (3) every key claim extracted and given a fact-check rating with evidence and sources, so a reader or journalist sees what is actually established. Story Engine was the pilot."

**Pilot reused**: Story Engine (`specs/001-story-engine-baseline`): LangGraph fan-out/fan-in, provider adapter by role, SSE over fetch, semantic cache (pgvector + MiniLM), quotas and rate limits, JWT login, SSLCommerz plans, Langfuse traces. Production target is AWS Option S serverless with Amazon Bedrock (`specs/002-aws-deployment`, deferred); local Docker first.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Get a sourced report on a topic (Priority: P1) MVP

A reader types a topic ("Michael Jackson controversy", "Did X say Y at the summit?"). Within about a minute the page fills in, live, with: what the topic is and its time span; a timeline of the key events; the mainstream account (what established outlets and primary sources report); the other positions that exist, each attributed to who holds them; and a list of the key claims, each with a rating, a confidence level, short evidence quotes and links to the sources the system actually fetched.

**Why this priority**: it is the product. Without it there is nothing to show readers or journalists.

**Independent Test**: submit a topic against the local stack with a mocked LLM and a recorded source fixture; assert the stream emits stage events, at least one perspective, at least three rated claims, and `done`; assert every citation in the stored report points to a fetched document and every quote is found verbatim in that document's stored text.

**Acceptance Scenarios**:

1. **Given** a topic with recent coverage, **When** the user submits it, **Then** they see within 10 s a resolved topic card (entities, time span, ambiguity choice if any) and progress stages, and within 90 s (p95) the full report.
2. **Given** a historical topic spanning decades (Michael Jackson allegations 1993-2019), **When** the report is built, **Then** the timeline covers the full span using reference and archive sources (encyclopedia, court records, archived articles), not only the last 3 months of news.
3. **Given** a claim that a fact-checker has already reviewed, **When** the report is built, **Then** that published fact-check is shown first, with its publisher, date, original verdict and link, mapped onto the Parallax rating scale.
4. **Given** a claim with thin or conflicting evidence, **When** it is rated, **Then** it is rated `Unproven` (or `Mixed` when credible sources conflict), never forced into `True` or `False`.
5. **Given** a topic that is ambiguous ("Jackson trial"), **When** submitted, **Then** the user is offered the candidate topics before any expensive work starts.

### User Story 2 - See who says what, without false balance (Priority: P1) MVP

The reader sees each position as a card: a one-line summary, who holds it (outlets, people, institutions, court filings), how much of the coverage it has, and how well its key claims hold up. Every source carries a visible label: its tier (primary record, established outlet, state-controlled or state-funded, independent or alternative, fact-checker, social or user content), and a link to the published methodology explaining the label.

**Why this priority**: "the other side" is the differentiator, and it is where the product can do harm (false balance, amplifying misinformation). It must ship with the MVP, not later.

**Independent Test**: build a report from a fixture where 90 % of sources hold position A and one fringe site holds position B with no supporting evidence; assert B is not presented as an equal "other side" card but listed under "Also circulating" with its claim rating, and its link is rendered `rel="nofollow ugc"` without preview.

**Acceptance Scenarios**:

1. **Given** a topic, **When** the report renders, **Then** every source shown has a tier label and the label links to the methodology page and the source's own profile (owner, funding, tier rationale, date assigned).
2. **Given** a state-controlled outlet in the sources, **When** it is cited, **Then** its card shows the state-media label taken from the source registry.
3. **Given** a position held only by anonymous or unverifiable accounts with no evidence, **When** the report renders, **Then** it is shown only under "Also circulating" with the rating of its claims, never as a co-equal position.
4. **Given** positions with very different evidence support, **When** shown, **Then** the layout reflects weight of evidence and coverage share (not a 50/50 split).

### User Story 3 - Trust every rating: method, evidence, history (Priority: P1) MVP

On any claim the reader can open: the exact claim text and who made it; the rating, confidence and a two- or three-sentence reason; the evidence passages (quote, source, date, link, tier); any existing fact-checks; and the rating history (each version, when, why, and which model and prompt produced it). Every rating carries the label "Automated assessment, not reviewed by a person". A methodology page publishes the rating scale, the source tiers and the pipeline.

**Why this priority**: a fact-check product without auditable method is not trusted and is legally exposed.

**Independent Test**: open a claim from a fixture report; assert all fields are present, the history shows version 1 with the model id, prompt version and evidence ids, and the methodology page lists the six ratings with definitions.

**Acceptance Scenarios**:

1. **Given** a rated claim, **When** opened, **Then** each evidence quote shows the URL, publisher, published date, fetched date, and is highlighted in context.
2. **Given** a rating changed by re-verification (or by a newly found fact-check), **When** history is opened, **Then** both versions are shown with reason and actor; the old version is never deleted.
3. **Given** a claim alleging wrongdoing by a living, named person, **When** the report is built, **Then** it is shown at once (no hold) with its rating, model confidence, source links, the "not reviewed" label and attributive wording ("X alleged ..."); `Verified` or `False` appears only with two independent strong sources, otherwise the rating is capped (FR-020, FR-021).

### User Story 4 - Report an error, reply, or request removal (Priority: P2)

Anyone can flag a claim or rating as wrong, a person or organisation named in a claim can submit a reply, and a rights holder can request a takedown. Each submission gets a tracking id and a status. There is no in-app review queue (human decision 2026-10-16): submissions are logged in the audit log, a correction triggers automatic re-verification, and the site operator actions replies and takedowns through an audited admin action. In the MVP every report and claim shows a corrections / right-of-reply contact link.

**Why this priority**: right of reply and a takedown path are required before public launch (defamation and copyright exposure), but the core loop can be demonstrated without them.

**Independent Test**: submit a correction and a takedown through the API; assert both get a tracking code, the audit log records them, the correction schedules a re-verification, and a takedown hides the affected snippet within the configured time.

**Acceptance Scenarios**:

1. **Given** a named person's reply, **When** the operator accepts it (audited admin action), **Then** the reply is shown next to the claim, labelled as a reply, with date.
2. **Given** a valid takedown for a snippet, **When** accepted, **Then** the snippet is replaced by the link only, and the audit log records who, when and why.

### User Story 5 - Journalist workspace: export, alerts (Priority: P2)

A journalist (paid plan) can: export a report or a claim with full citations (Markdown, JSON, and a citation list); watch a topic or claim and get an alert when new coverage, a new fact-check, or a rating change appears.

**Why this priority**: journalists are the paying audience; the reader MVP works without it.

**Independent Test**: as a journalist, export a report and watch one of its claims; force a re-verification that changes the rating; assert the export now contains both versions and the watcher gets an alert.

**Acceptance Scenarios**:

1. **Given** a report, **When** a journalist exports it, **Then** the file contains every rating version with confidence, evidence URLs and the "Automated assessment, not reviewed by a person" label.
2. **Given** a watched topic, **When** a new cluster of coverage appears, **Then** the watcher gets an alert (in-app, and email later) with a link to the refreshed report.

### User Story 6 - Fast, cheap repeat questions (Priority: P2)

Popular topics are answered from cache, and claims already verified are reused across topics, with a re-verification schedule so ratings do not go stale.

**Independent Test**: request the same topic twice; the second request streams the stored report with cost 0 and `cache_hit: true`; a claim seen in another topic reuses its verdict when within its re-verification window.

**Acceptance Scenarios**:

1. **Given** a cached report younger than its freshness window, **When** requested, **Then** it is served from cache with a "last updated" time and a "refresh" action (quota-counted).
2. **Given** a claim verdict past its re-verification date, **When** the claim reappears, **Then** it is re-verified and a new rating version is stored if it changed.

### Edge Cases

- **Breaking news with almost no reliable coverage**: claims default to `Unproven`, the report carries a "developing story" banner, freshness window is short (1 h).
- **Satire and opinion**: satire sources are labelled; opinions, predictions and value judgements are tagged `Not checkable` instead of rated.
- **Private individuals and minors**: topics centred on a private, non-public person, or a minor, are refused with an explanation; names of minors are never displayed.
- **Deceased subjects with living third parties** (the Michael Jackson case: the subject died in 2009; accusers, witnesses and estate are living): living-person rules apply to every named living party.
- **Sources that block bots or are paywalled**: the system uses only what the source permits (robots.txt, terms); a paywalled article contributes headline, lede and link, never full text.
- **A source disappears or changes** after rating: the stored hash and fetched date stay; an archived copy link (Wayback) is added where available.
- **Non-English sources**: MVP is English UI; non-English sources may be used as evidence with machine translation clearly marked, or skipped (decision at clarification: skipped in MVP).
- **LLM output that cites an unknown evidence id or a quote not found in the document**: the claim is re-run once, then rated `Unproven` with reason "insufficient verified evidence"; it never reaches the reader with an invalid citation.
- **Prompt injection inside fetched articles** ("ignore previous instructions"): fetched text is passed as quoted data in a delimited block; verifier output is validated structurally; any rating whose reason quotes no evidence is rejected.
- **Coordinated flooding**: many low-tier sources repeating one claim count as one source family (dedup by syndication and origin), so volume does not create weight.
- **Quota exhausted or a provider down**: same behaviour as the pilot (402 / 429; degraded stages reported in the stream, report still delivered with what is available and marked partial).

## Requirements *(mandatory)*

### Functional Requirements

**Topic and report**

- **FR-001**: Users MUST be able to submit a topic as free text (max 200 characters) and receive a report over SSE (fetch-based POST, same contract style as the pilot).
- **FR-002**: The system MUST resolve the topic to entities, a time span and a topic type (`breaking`, `recent`, `historical`) before retrieval, and MUST ask the user to choose when more than one candidate topic is plausible.
- **FR-003**: A report MUST contain: topic card, event timeline, mainstream account, zero or more other positions, "also circulating" list, key claims with ratings, source list, methodology link, generated-at time, model and prompt versions.
- **FR-004**: Every factual sentence in the mainstream account and position summaries MUST carry at least one citation to stored evidence; sentences without one MUST be removed by validation before publication.

**Retrieval**

- **FR-005**: The system MUST ingest the curated RSS feeds from the source directory (171 validated feeds plus 64 more passing feeds in the hive research file, about 235 today) on a schedule (default every 30 min), storing metadata, lede snippet and embedding, deduplicated by canonical URL and content hash.
- **FR-006**: On a query the system MUST combine: the local article index, GDELT DOC search, Wikipedia (and its references), the Wayback Machine for archived copies, Google Fact Check Tools (ClaimReview), and court records (CourtListener) for legal topics; a paid news search API is optional and behind a feature flag.
- **FR-007**: Full text MUST be extracted only from sources whose robots.txt and terms allow it, with an identifying User-Agent and per-domain rate limits; otherwise only metadata and lede are used.
- **FR-008**: Articles MUST be clustered into events (near-duplicate and syndication detection plus embedding clustering) and ordered into a timeline; syndicated copies MUST count as one source family.
- **FR-009**: Historical topics MUST draw on reference and archive sources across the whole span; recency-only search MUST NOT be the sole source.

**Perspectives and source tiers**

- **FR-010**: Every source (outlet, organisation, record holder) MUST have a registry entry with tier, ownership and funding, state-media flag, country, language, rationale and date assigned; tiers MUST be published.
- **FR-011**: Tiers MUST be: `primary` (court, government, official records, original documents, direct statements), `established` (outlets with named editors, a corrections policy and a track record), `state` (state-controlled or state-funded editorial), `independent` (independent or alternative outlets), `factchecker` (IFCN signatories and equivalents), `social` (user-generated, anonymous, social posts).
- **FR-012**: "Mainstream account" MUST be defined as the account supported by the majority of `established` coverage plus `primary` sources; it MUST NOT be presented as true by definition: its claims are rated like any others.
- **FR-013**: A position MUST be shown as an "other side" only when held by at least one identifiable party with standing (named person or organisation, court filing, `established`/`independent`/`state` outlet) or when its coverage share is at least 5 %; otherwise it goes to "also circulating". Positions MUST be ordered by evidence support, then coverage share.
- **FR-014**: Links to `social` and unrated low-reliability sources MUST render without previews and with `rel="nofollow ugc"`; their content MUST NOT be quoted beyond the claim text.

**Claims and fact-checking**

- **FR-015**: The system MUST extract atomic, checkable claims from the top articles of each position (default max 12 per report), each with the speaker or source that makes it, deduplicated across sources.
- **FR-016**: Non-checkable statements (opinion, prediction, value judgement) MUST be tagged `Not checkable` and not rated.
- **FR-017**: For each claim the system MUST first look for existing fact-checks (ClaimReview); a match MUST be shown with publisher, date, original verdict and link, and mapped to the Parallax scale through a published mapping table.
- **FR-018**: Otherwise the system MUST retrieve evidence and produce a rating on the scale `Verified`, `Mostly true`, `Mixed`, `Unproven`, `Misleading`, `False`, with a confidence (`high`, `medium`, `low`), a 2-3 sentence reason, and 1-5 evidence quotes.
- **FR-019**: Every cited evidence item MUST be a document the system fetched and stored (URL, fetched-at, HTTP status, content hash); every quote MUST appear verbatim in the fetched text (checked during the build, before the full text is discarded; the stored content hash and excerpt keep the proof, FR-034). Ratings failing this check MUST be re-run once and otherwise set to `Unproven`.
- **FR-020**: `Verified` and `False` MUST require at least two independent sources, at least one of tier `primary`, `established` or `factchecker`; otherwise the strongest allowed rating is `Mostly true` / `Misleading`.
- **FR-021**: Claims alleging crimes or misconduct by a living, named person MUST use attribution language ("X alleged that ...") in the claim text, reason and narrative, and are shown without any human hold (human decision 2026-10-16) with their rating, model confidence, source links and the "not reviewed" label (FR-025); `Verified` / `False` on such claims MUST satisfy FR-020, otherwise the rating is capped at `Mostly true` / `Misleading` or set to `Unproven`.

**Trust, legal and audit**

- **FR-022**: Every rating version MUST be stored immutably with actor (model id + prompt version, or `system:<job>` for re-verification), evidence ids, reason and timestamp; the audit log MUST be append-only and retained for at least 6 years.
- **FR-023**: Every report and claim MUST show a corrections / right-of-reply contact link (MVP). From P2 the system MUST provide correction requests, right of reply for named parties, and takedown requests, each with tracking id and status, recorded in the audit log; a correction triggers automatic re-verification; replies and takedowns are actioned by the site operator through an audited admin action (no review queue); accepted replies MUST be shown next to the claim.
- **FR-024**: Displayed source text MUST be limited to short quotes (max 300 characters per quote, max 3 quotes per source per report) plus headline and link; full articles MUST NOT be republished.
- **FR-025**: Every rating MUST carry the visible label "Automated assessment, not reviewed by a person" next to its value and confidence; every report MUST show a disclaimer that ratings are automated assessments of public sources, the date of assessment, and links to the methodology and the corrections / right-of-reply contact.
- **FR-026**: Topics centred on private individuals or minors MUST be refused; names of minors MUST NOT be displayed.

**Journalist features, platform**

- **FR-027**: Paid users MUST be able to export a report or a claim (Markdown, JSON, citation list) including rating versions and evidence URLs.
- **FR-028**: Paid users MUST be able to watch topics and claims and receive in-app alerts on new coverage, new fact-checks or rating changes.
- **FR-029**: *Removed 2026-10-16 (human decision 3: no human review queue). The number is kept so references stay stable.*
- **FR-030**: Auth (JWT), plans, quotas, rate limits and SSLCommerz payments MUST be reused from the pilot; a report counts as one quota unit, a cache hit counts zero, a forced refresh counts one.
- **FR-031**: Reports MUST be cached per resolved topic with a freshness window by topic type (`breaking` 1 h, `recent` 24 h, `historical` 30 d); claim verdicts MUST be cached by claim embedding with a re-verification date by rating (`Unproven`/`Mixed` 7 d, others 90 d, any claim on a `breaking` topic 6 h).
- **FR-032**: Every report MUST record per-stage token usage and cost, search API calls and their cost, and stream them in `done`; LLM calls MUST have hard output caps from settings.
- **FR-033**: The pipeline MUST run on the provider adapter (`anthropic` locally, `bedrock` in production, `local` for zero-cost dev), with no provider SDK imported by graph nodes.
- **FR-034**: Retention MUST be quotes-only: for each fetched document the system persists URL, metadata (title, publisher, author, dates, HTTP status), lede (<= 500 chars), content hash and the cited excerpts; full article text lives only in a transient working cache for the build (TTL at most 24 h) and is never written to the database or a blob store.

### Key Entities

- **Topic**: a resolved subject (title, entities, type, time span, aliases, embedding); has many Reports.
- **Report**: one versioned build for a Topic (sections, status, freshness, cost, model/prompt versions, trace id).
- **Source**: an outlet or record holder in the registry (tier, owner, funding, state flag, country, language, rationale, history of tier changes).
- **Feed**: an ingestion endpoint (RSS, API) of a Source.
- **Article**: a fetched document (canonical URL, title, published/fetched dates, lede, stored text hash, extraction status, licence/robots basis, embedding).
- **EventCluster**: a group of Articles about one event, with timeline date and source families.
- **Perspective**: a position on the Topic (summary, holders, coverage share, evidence support, kind: mainstream / other / also-circulating).
- **Claim**: an atomic statement (text, type checkable/not, speaker, living-person flag, embedding); appears in many Articles via ClaimOccurrence.
- **Evidence**: a quote from a fetched Article (offsets, text, supports/refutes/context).
- **ExistingFactCheck**: a ClaimReview record (publisher, url, date, textual rating, mapped rating).
- **Rating**: an immutable version (value, confidence, reason, evidence ids, actor, prompt version, created at); a Claim has many.
- **Submission** (P2): correction, reply or takedown, with tracking code and status (no review queue).
- **AuditEvent**: append-only log entry for every rating, submission, takedown and tier change.
- **Watch / Alert**: a user's subscription to a Topic or Claim and the alerts it produced.
- Reused from the pilot: **User**, **Plan/Quota**, **Payment**.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: p95 time to full report at most 90 s for a cold topic and at most 3 s for a cached topic; first visible progress within 5 s.
- **SC-002**: 100 % of published citations resolve to a stored, fetched document, and 100 % of published quotes are found verbatim in it (checked automatically on every report).
- **SC-003**: On the gold set (at least 300 claims with known fact-checker verdicts), rating agreement at least 70 % exact on the 6-point scale and at least 90 % within one step, with no `True`-vs-`False` inversions above 2 %.
- **SC-004**: Unsupported-statement (hallucination) rate in report narratives at most 2 % of sentences on the gold topics, measured by citation validation plus a sampled manual spot-check during evaluation.
- **SC-005**: In red-team topics, 100 % of living-person allegation ratings use attributive wording and carry the "not reviewed" label, and zero `Verified` / `False` ratings on them lack two independent strong sources.
- **SC-006**: Modelled LLM cost per cold report at most $0.02 (Haiku tier) and at most $0.05 with premium verification; search API cost $0 in MVP (free sources only).
- **SC-007**: (P2) Corrections and takedowns acknowledged automatically with a tracking code on submission and decided by the operator within 5 business days (operational target).
- **SC-008**: In usability tests, at least 8 of 10 readers can say, for a sample claim, what the rating is, why, and which source supports it, within 60 s.

## Clarifications

### Session 2026-10-16 (answered with best judgment by the planning agent; the human may override)

- Q: Who is the MVP audience? -> A: Public readers first (free tier with quota), journalists as the paid tier (P2 features). Reason: readers validate the core loop; journalist features need exports and alerts.
- Q: Languages? -> A: English UI and English sources in MVP; the source directory's non-English feeds are ingested but not used as evidence until a translation step exists (Phase 4).
- Q: Rating scale? -> A: Six ratings (`Verified`, `Mostly true`, `Mixed`, `Unproven`, `Misleading`, `False`) plus the `Not checkable` tag; confidence in three levels. Existing fact-checks are mapped, never overwritten.
- Q: Who decides source tiers? -> A: A seeded registry from the vault directory (state-media labels already present) plus published criteria; tier changes are reviewed and audited; external lists (Wikipedia's perennial sources list, IFCN signatory list) are inputs, not authorities.
- Q: Human review in MVP? -> A: No (human decision 2026-10-16). Ratings are shown with model confidence and source links under an "Automated assessment, not reviewed by a person" label; the automatic safeguards (FR-019..FR-021, FR-025) replace a review hold.
- Q: Full-text storage? -> A: Quotes-only from day one (human default 2026-10-16): excerpts, URL, metadata and content hash are kept; full text only in a transient build cache (FR-034).
- Q: Reuse the Story Engine repo? -> A: New repository `parallax` seeded from the pilot's platform code (ADR-001, approved by the human 2026-10-16); this spec moves there as `specs/001-parallax`.
- Q: Paid news APIs? -> A: Not in MVP (free and open sources only); a paid API adapter is behind a flag for Phase 4 once there is revenue.

### Session 2026-10-16 (human decisions)

- Q: Product name? -> A: **Parallax** (repo `parallax`, package names, UI title, docs, vault).
- Q: ADR-001? -> A: Approved: new repository seeded from story-engine, not a module.
- Q: Who reviews held claims? -> A: Nobody: no human review queue in MVP; held-claim workflow removed (FR-021, FR-029).
- Q: Legal review budget? -> A: Deferred; the product is a review report. Legal-budget tasks dropped from MVP; `docs/legal/source-terms.md` kept.
- Q: Paid news APIs? -> A: Free sources only (default accepted).
- Q: Social media claims in MVP? -> A: No (default accepted).
- Q: Full-text retention? -> A: Quotes-only (default accepted, FR-034).

### Open questions for the human

1. Pricing of the journalist plan, and whether SSLCommerz stays the only gateway (P2).
2. Trademark and domain checks for "Parallax" (not done).

## Assumptions

- Pilot platform code (auth, quotas, payments, adapter, SSE, semantic cache, infra plan) is reused as-is; its known defects are fixed in the pilot first.
- Free sources are enough for an MVP: curated RSS (about 171 feeds), GDELT, Wikipedia/Wikimedia APIs, Wayback, Google Fact Check Tools (API key, free), CourtListener (free token, 125 requests/day).
- Planning uses modelled token counts only; no LLM calls were made while planning. Real costs are measured in the evaluation phase.
- AWS go-live stays deferred; local Docker is the only deployment target until the human decides.
