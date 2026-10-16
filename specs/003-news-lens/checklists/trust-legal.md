# Trust, Legal and Safety Checklist: News Lens (003)

**Purpose**: Release gate for public launch; every item must be checked with evidence (test id, doc link or reviewer sign-off)
**Created**: 2026-10-16
**Feature**: [spec.md](../spec.md) | [research.md R5](../research.md)

## Evidence integrity

- [ ] CHK001 Every published citation resolves to a stored fetched document with hash and fetched-at (FR-019, SC-002) - test T034
- [ ] CHK002 Every published quote is verbatim in the stored text (FR-019) - test T034
- [ ] CHK003 `Verified` / `False` satisfy the independence rule (FR-020) - test T035
- [ ] CHK004 Narrative sentences without a valid evidence marker are dropped (FR-004) - test T038
- [ ] CHK005 Prompt-injection fixtures do not change ratings or leak instructions (edge case) - test T061

## Fairness and harm

- [ ] CHK006 Tier criteria and every source's rationale are public (FR-010) - page T044
- [ ] CHK007 "Other side" gate and evidence-weighted ordering hold on the false-balance fixture (FR-013, US2) - test T042
- [ ] CHK008 Social / low-support links render without preview and `nofollow ugc` (FR-014) - test T043
- [ ] CHK009 Private-individual and minor topics are refused; no minor names displayed (FR-026) - test T028
- [ ] CHK010 Living-person allegations held for review; zero model-only `False`/`Verified` published in red team (FR-021, SC-005) - test T036, T061

## Legal

- [ ] CHK011 Media-law review completed for the launch jurisdictions (open question 2) - HUMAN
- [ ] CHK012 Displayed quotes <= 300 chars, <= 3 per source per report (FR-024) - test T037
- [ ] CHK013 robots.txt / meta robots / X-Robots-Tag honoured; `extraction_basis` stored (FR-007) - test T021
- [ ] CHK014 API terms reviewed per connector (NewsAPI dev plan not used in production; GNews free not commercial) (R5) - doc T005
- [ ] CHK015 Disclaimer and methodology links on every report (FR-025) - test T047
- [ ] CHK016 Correction, right of reply, takedown flows live with tracking codes (FR-023) - tests T050-T052
- [ ] CHK017 Takedown hides the snippet and keeps the link, audited (US4) - test T052
- [ ] CHK018 Wikipedia content attributed under CC BY-SA (R5) - test T047

## Accountability

- [ ] CHK019 Ratings immutable; history visible (FR-022, US3) - test T045
- [ ] CHK020 Audit log append-only with hash chain; UPDATE/DELETE rejected by the DB (FR-022) - test T015
- [ ] CHK021 Reviewer decisions carry actor, note and timestamp (FR-029) - test T056
- [ ] CHK022 Named reviewers available and review SLA agreed (open question 3, SC-007) - HUMAN

## Notes

- Not legal advice; CHK011 and CHK022 need the human.
