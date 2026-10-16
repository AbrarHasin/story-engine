# Rating scale and ClaimReview mapping (published methodology, v0.1)

Served by `GET /api/v1/methodology`. Changing anything here bumps `methodology_version` and is an audit event.

## Ratings

| Value | Label | Definition | Minimum evidence |
|---|---|---|---|
| `verified` | Verified | Supported by independent strong sources; no credible contrary evidence. | >= 2 source families, >= 1 of tier primary / established / factchecker (FR-020) |
| `mostly_true` | Mostly true | Supported; minor inaccuracy or missing context that does not change the core. | >= 1 strong source |
| `mixed` | Mixed | Credible sources materially conflict, or partly accurate and partly not. | conflicting strong sources |
| `unproven` | Unproven | Evidence insufficient, thin, or only from the claimant. **Default when unsure.** | none required |
| `misleading` | Misleading | Accurate elements framed to give a false impression, or key context omitted. | >= 1 strong source showing the omission |
| `false` | False | Contradicted by independent strong sources or by a primary record. | >= 2 source families, >= 1 strong (FR-020) |
| tag `not_checkable` | Not checkable | Opinion, prediction, value judgement, unfalsifiable. | not rated |

Confidence: `high` = 3+ independent strong families agree; `medium` = 2; `low` = 1 or conflicting.

Living-person allegations: model ratings `verified`, `misleading`, `false` are held for human review (FR-021); wording stays attributive ("X alleged ...").

## ClaimReview `textualRating` mapping

Matching is case-insensitive on the normalised string; unmatched strings go to a capped Haiku mapper whose output is stored and reviewed into this table.

| Publisher wording (examples) | Mapped |
|---|---|
| True, Correct, Accurate, Verified | `verified` |
| Mostly True, Largely accurate, Mostly correct | `mostly_true` |
| Half True, Mixture, Partly true, Partly false, Mixed | `mixed` |
| Unproven, Unverified, Unsupported, No evidence, Insufficient evidence, Research in progress | `unproven` |
| Misleading, Missing context, Out of context, Exaggerated, Distorts the facts, Cherry-picks | `misleading` |
| Mostly False | `misleading` (with note "publisher: mostly false") |
| False, Incorrect, Fake, Fabricated, Pants on Fire, Hoax, Altered, Wrong | `false` |
| Satire, Opinion, Labeled satire | tag `not_checkable` |

The publisher's own wording and link are always shown next to the mapped value; News Lens never overwrites an existing fact-check, it only places it on this scale.
