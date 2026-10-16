# Data Model: Parallax (003)

PostgreSQL 16 + pgvector. UUID primary keys, `timestamptz` everywhere (fixes the pilot's naive timestamps). Embeddings `vector(384)` (MiniLM-L6, as the pilot). Reused unchanged from the pilot: `users`, `payments`, quota columns (`plan`, `stories_this_month` renamed `reports_this_period`, `quota_period_start`), `rate_limit_window`. New column `users.role` (`reader` | `journalist` | `admin`).

## Entity relationships

```text
Source 1-* Feed            Source 1-* Article          Source 1-* SourceTierChange
Article *-1 SourceFamily   Article *-* EventCluster    (cluster_articles)
Topic 1-* Report           Report *-* Article          (report_articles, with role: cited | considered)
Report 1-* Perspective     Perspective *-* Source      (perspective_holders, with article_id)
Claim *-* Report           (report_claims, with order, perspective_id)
Claim 1-* ClaimOccurrence  ClaimOccurrence *-1 Article
Claim 1-* Rating           Rating *-* Evidence         (rating_evidence)
Evidence *-1 Article       Claim *-* ExistingFactCheck (claim_factchecks, with similarity)
Claim/Report 1-* Submission  (P2; no review tasks)
User 1-* Watch 1-* Alert   AuditEvent (append-only, references any entity by type + id)
```

## Tables

### sources
| Column | Type | Notes |
|---|---|---|
| id | uuid | |
| name | text | "Reuters", "CGTN", "U.S. District Court C.D. Cal." |
| domain | text unique null | canonical registrable domain |
| tier | enum `primary, established, state, independent, factchecker, social` | FR-011 |
| state_media | bool | from the vault directory flag |
| owner, funding | text | published on the source profile |
| country, language | text | ISO codes |
| ifcn_signatory | bool | factchecker evidence |
| rationale | text | why this tier |
| tier_assigned_at | timestamptz | |
| robots_policy | jsonb | cached robots result, checked_at |
| allow_fulltext | bool | from robots + terms review |
| created_at, updated_at | timestamptz | |

Tier changes write `source_tier_changes(id, source_id, old_tier, new_tier, reason, actor, created_at)` and an AuditEvent.

### feeds
`id, source_id, url unique, kind (rss | api), language, poll_minutes (default 30), etag, last_modified, last_ok_at, consecutive_failures, healthy bool`.

### articles
| Column | Type | Notes |
|---|---|---|
| id | uuid | |
| source_id | uuid fk | |
| family_id | uuid fk null | syndication family (MinHash) |
| url, canonical_url | text | canonical unique |
| title, lede | text | lede <= 500 chars |
| author | text null | |
| published_at, fetched_at | timestamptz | |
| http_status | int | of the fetch that produced `content_hash` |
| content_hash | char(64) null | SHA-256 of normalised text |
| text_cache_key | text null | transient Redis key, TTL 24 h; full text is never persisted (FR-034) |
| extraction_basis | enum `fulltext_allowed, metadata_only, api_terms, open_licence` | FR-007, R5 |
| archive_url | text null | Wayback copy |
| language | text | |
| embedding | vector(384) | title + lede |
| minhash | bytea | for dedup |
| origin | enum `rss, gdelt, wikipedia, wayback, courtlistener, factcheck, newsapi, gnews, other` | |

Indexes: `canonical_url` unique, `published_at`, HNSW on `embedding`, GIN `to_tsvector(title || lede)`.

### event_clusters / cluster_articles
`event_clusters(id, topic_id, label, event_date, date_precision (day | month | year), centroid vector(384), family_count)`; `cluster_articles(cluster_id, article_id)`.

### topics
`id, title, query_text, entities jsonb [{name, kind, living bool, public_figure bool}], topic_type (breaking | recent | historical), span_start date, span_end date null, key_questions jsonb, embedding vector(384), created_at`.

### reports
| Column | Type | Notes |
|---|---|---|
| id | uuid | |
| topic_id | uuid fk | |
| user_id | uuid fk | requester (ownership for exports) |
| version | int | per topic |
| status | enum `running, completed, partial, failed` | |
| sections | jsonb | mainstream, positions, also_circulating, with evidence markers |
| fresh_until | timestamptz | from topic type (FR-031) |
| cache_source_report_id | uuid null | when served from cache |
| model_versions | jsonb | role -> model id |
| prompt_versions | jsonb | node -> prompt hash |
| tokens_in, tokens_out | int | |
| llm_cost_usd, search_cost_usd | numeric(10,6) | FR-032 |
| stage_costs | jsonb | per node |
| langgraph_run_id, trace_url | text | |
| created_at, completed_at | timestamptz | |

`report_articles(report_id, article_id, role)`; `report_claims(report_id, claim_id, position_order, perspective_id null)`.

### perspectives / perspective_holders
`perspectives(id, report_id, kind (mainstream | other | also_circulating), key_question, stance, summary, coverage_share numeric(5,4), evidence_support numeric(5,4), order)`; `perspective_holders(perspective_id, source_id null, person_name null, article_id, role (outlet | person | institution | filing))`.

### claims / claim_occurrences
| Column | Type | Notes |
|---|---|---|
| id | uuid | |
| text | text | normalised atomic claim |
| checkable | bool | false -> `Not checkable` tag |
| living_person_named | bool | FR-021 |
| allegation | bool | crime / misconduct allegation |
| entities | jsonb | |
| embedding | vector(384) | verdict cache key |
| current_rating_id | uuid null | latest published Rating |
| reverify_at | timestamptz | FR-031 |
| hidden | bool | taken down (operator action, P2) |

`claim_occurrences(id, claim_id, article_id, speaker, quote, char_start, char_end)`.

### existing_factchecks / claim_factchecks
`existing_factchecks(id, publisher_name, publisher_site, url unique, title, claim_text, claimant, claim_date, review_date, textual_rating, language, mapped_rating, fetched_at)`; `claim_factchecks(claim_id, factcheck_id, similarity)`.

### evidence
`id, article_id, quote text (<= 300 chars; the stored excerpt, no full passage kept, FR-034), char_start, char_end, stance (supports | refutes | context), quote_verified bool, verified_against_hash char(64), created_at`.

### ratings (immutable content; never deleted)

All content columns are write-once. Only `status` may change, and only through a DB trigger that allows `published -> superseded` and writes an AuditEvent in the same transaction. A changed value, confidence, reason or evidence is always a new version.
| Column | Type | Notes |
|---|---|---|
| id | uuid | |
| claim_id | uuid fk | |
| version | int | per claim |
| value | enum `verified, mostly_true, mixed, unproven, misleading, false` | |
| confidence | enum `high, medium, low` | |
| reason | text | 2-3 sentences |
| basis | enum `existing_factcheck, model` | |
| actor | text | `model:claude-haiku-5-5@prompt:<hash>` or `system:reverify` |
| status | enum `published, superseded` | shown with the "not reviewed" label (FR-025) |
| validator_report | jsonb | citation, quote, independence checks |
| created_at | timestamptz | |

`rating_evidence(rating_id, evidence_id, order)`.

### submissions (P2)
`submissions(id, kind (correction | reply | takedown | tier_appeal), target_type, target_id, submitter_email, submitter_name, is_named_party bool, body, attachments jsonb, status (received | accepted | rejected | actioned), tracking_code, created_at)`.
No `review_tasks` table (human decision 2026-10-16). The operator actions submissions with an audited admin action.

### audit_events (append-only)
`id bigserial, at timestamptz, actor, action (rating.created, rating.published, rating.superseded, submission.actioned, takedown.actioned, source.tier_changed, report.published, submission.received ...), target_type, target_id, payload jsonb, prev_hash char(64), hash char(64)`. `hash = sha256(prev_hash || canonical_json(row))`; a DB rule forbids UPDATE and DELETE; daily digest exported to the blob store. Retention >= 6 years.

### watches / alerts
`watches(id, user_id, target_type (topic | claim), target_id, created_at)`; `alerts(id, watch_id, kind (new_coverage | new_factcheck | rating_changed), payload, read_at null, created_at)`.

## State transitions

- **Rating**: created as `published` (no hold); `published` -> `superseded` on re-verification or a newly matched fact-check. Status transitions go through the trigger above; any change of content inserts a new version and updates `claims.current_rating_id`.
- **Report**: `running` -> `completed` | `partial` (some connectors degraded) | `failed`.
- **Submission** (P2): `received` -> `accepted` -> `actioned`, or `rejected` (operator admin action, audited).

## Validation rules (enforced in code and tests)

- A Rating with value `verified` or `false` needs >= 2 evidence rows from distinct `family_id`s, at least one from tier `primary | established | factchecker` (FR-020).
- Every `rating_evidence` row needs `evidence.quote_verified = true` and `verified_against_hash = articles.content_hash` (FR-019).
- `claims.living_person_named and allegation` -> claim text, reason and narrative use attributive wording; `verified` / `false` also need the FR-020 rule; no hold (FR-021).
- Displayed quotes <= 300 chars, <= 3 per source per report (FR-024).

## Migration plan

`0001_platform` (copied pilot tables, timestamptz, users.role), `0002_sources_feeds_articles`, `0003_topics_reports_clusters`, `0004_claims_ratings_evidence_factchecks`, `0005_trust_submissions_audit`, `0006_watches_alerts`. Seed: `import_directory.py` loads sources/feeds from the vault directory and the hive research JSON (235 feeds, tiers, state flags).
