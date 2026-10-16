# Specification Quality Checklist: Parallax (003)

**Purpose**: Validate specification completeness and quality before planning
**Created**: 2026-10-16
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] CHK001 User stories are prioritised (P1 x3 MVP, P2 x3) and each has an independent test
- [x] CHK002 Focused on user value (readers, journalists) and harms (false balance, defamation)
- [x] CHK003 Written so a non-technical stakeholder can follow the stories; technology names appear only in FRs that reuse pilot decisions (SSE, adapter) and in Assumptions
- [x] CHK004 All mandatory sections completed (scenarios, requirements, success criteria, assumptions)

## Requirement Completeness

- [x] CHK005 No `[NEEDS CLARIFICATION]` markers remain; ambiguities resolved in Clarifications, residual decisions listed as open questions for the human
- [x] CHK006 Requirements are testable (each FR maps to at least one task or test in tasks.md, see analysis.md coverage table)
- [x] CHK007 Success criteria are measurable (latency, citation validity 100 %, agreement %, hallucination %, cost, SLA)
- [x] CHK008 Success criteria are largely technology-agnostic (SC-006 names model tiers because cost is a constitution principle)
- [x] CHK009 Acceptance scenarios defined for every story
- [x] CHK010 Edge cases identified (breaking news, satire, private persons, minors, deceased with living parties, paywalls, injection, flooding, deleted sources, non-English)
- [x] CHK011 Scope bounded: English MVP, free sources, no social-media ingestion, AWS deferred
- [x] CHK012 Dependencies and assumptions identified (pilot platform code, free APIs, no live LLM during planning)

## Feature Readiness

- [x] CHK013 Every FR has acceptance coverage through a user story or a validation rule
- [x] CHK014 User scenarios cover the primary flows (report, perspectives, trust, submissions, journalist, cache)
- [x] CHK015 Feature meets measurable outcomes defined in Success Criteria (gates in tasks Phase 9)
- [x] CHK016 No implementation details leak into user stories

## Notes

- The human answered the open questions on 2026-10-16 (name, ADR-001, no review queue, legal review deferred, free sources, no social claims, quotes-only retention); pricing and trademark checks remain and block nothing in Phase 0.
