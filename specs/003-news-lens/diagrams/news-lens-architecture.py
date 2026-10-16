"""Generates News-Lens-Architecture.excalidraw (diagram-as-code).

News Lens (working name), spec 003-news-lens: topic -> sourced report with the
mainstream account, the other sides and a rating per claim. Planning only;
nothing is built. Local Docker first, AWS Option S (Lambda + Aurora + Bedrock,
spec 002) later. Story Engine is the pilot whose platform code is reused.

Visual language copied from Story-Engine/Diagrams/aws-cloud-architecture.py
(itself from Doctor-Assist): nested boundaries, category-coloured icon tiles,
numbered step badges keyed to "How it works", solid = request/data path,
dashed = background / later / option, amber "!" = not built or not decided.

Usage:  cd Projects/News-Lens/Diagrams && python3 -B news-lens-architecture.py
"""

from __future__ import annotations

import json
import random
from pathlib import Path

OUT = Path(__file__).parent / "News-Lens-Architecture.excalidraw"

SQUID = "#232F3E"
SMILE = "#ED7100"    # compute / pipeline
ENDOR = "#7AA116"    # storage
NEBULA = "#C925D1"   # database
GALAXY = "#8C4FFF"   # edge / networking
COSMOS = "#E7157B"   # integration / workers
MARS = "#DD344C"     # trust, security, legal
ORBIT = "#01A88D"    # LLM
SLATE = "#5A6C86"
CARD_BD = "#D5DBDB"
EXT = "#7D8998"
AMBER = "#B45309"
GREEN = "#15803D"
TEAL = "#00A4A6"

_seed = random.Random(20261016)


def _nonce() -> int:
    return _seed.randint(1, 2**31)


def _base(eid, etype, x, y, w, h, **kw):
    el = {
        "id": eid, "type": etype, "x": x, "y": y, "width": w, "height": h,
        "angle": 0, "strokeColor": SQUID, "backgroundColor": "transparent",
        "fillStyle": "solid", "strokeWidth": 1, "strokeStyle": "solid",
        "roughness": 0, "opacity": 100, "groupIds": [], "frameId": None,
        "roundness": {"type": 3} if etype == "rectangle" else None,
        "seed": _nonce(), "version": 1, "versionNonce": _nonce(),
        "isDeleted": False, "boundElements": [], "updated": 1,
        "link": None, "locked": False,
    }
    el.update(kw)
    return el


def txt(eid, x, y, text, size=12, color=SQUID, align="left", w=None):
    lines = text.split("\n")
    est = int(max(len(ln) for ln in lines) * size * 0.55) + 4
    return [_base(eid, "text", x, y, w if w is not None else est,
                  int(len(lines) * size * 1.25),
                  text=text, originalText=text, fontSize=size, fontFamily=2,
                  textAlign=align, verticalAlign="top", strokeColor=color,
                  lineHeight=1.25, roundness=None)]


def group(eid, x, y, w, h, label, stroke, *, dashed=False, fill="transparent", size=13):
    els = [_base(eid, "rectangle", x, y, w, h, backgroundColor=fill,
                 strokeColor=stroke, strokeWidth=2,
                 strokeStyle="dashed" if dashed else "solid")]
    els += txt(f"{eid}_l", x + 12, y + 10, label, size, stroke)
    return els


def card(eid, x, y, w, glyph, title, lines, cat, *, dashed=False, n=None):
    h = 44 + len(lines) * 14 + 10
    els = [_base(eid, "rectangle", x, y, w, h, backgroundColor="#ffffff",
                 strokeColor=CARD_BD, strokeStyle="dashed" if dashed else "solid")]
    els.append(_base(f"{eid}_i", "rectangle", x + 9, y + 9, 28, 28,
                     backgroundColor=cat, strokeColor=cat))
    els += txt(f"{eid}_g", x + 9, y + 17, glyph, 10, "#ffffff", align="center", w=28)
    els += txt(f"{eid}_t", x + 45, y + 16, title, 11, SQUID, w=w - 53)
    caveat = False
    for i, ln in enumerate(lines):
        if ln.startswith("!"):
            caveat = True
        elif not ln.startswith("  "):
            caveat = False
        els += txt(f"{eid}_l{i}", x + 11, y + 46 + i * 14, ln, 10,
                   AMBER if caveat else SLATE, w=w - 20)
    if n is not None:
        els += step(f"{eid}_s", x + w - 4, y + 4, n)
    return els


def step(eid, cx, cy, n, color=SQUID):
    r = 11
    els = [_base(eid, "ellipse", cx - r, cy - r, 2 * r, 2 * r,
                 backgroundColor=color, strokeColor="#ffffff", strokeWidth=2)]
    els += txt(f"{eid}_n", cx - r, cy - 6, str(n), 11, "#ffffff", align="center", w=2 * r)
    return els


def arrow(eid, x, y, pts, color=SQUID, *, dashed=False, width=2, both=False):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return [_base(eid, "arrow", x, y, max(xs) - min(xs), max(ys) - min(ys),
                  points=[list(p) for p in pts], strokeColor=color, strokeWidth=width,
                  strokeStyle="dashed" if dashed else "solid",
                  startArrowhead="arrow" if both else None, endArrowhead="arrow",
                  startBinding=None, endBinding=None, elbowed=False)]


STEPS = [
    "Ask. A reader types a topic in the SPA. The API (pilot code: JWT, quota, rate limit) "
    "opens a Server-Sent Events stream and starts the report graph.",
    "Resolve and cache. Haiku resolves entities, topic type (breaking / recent / historical) and "
    "time span, refuses private people and minors. A fresh cached report replays at $0.",
    "Retrieve. The background index (RSS, ~235 feeds every 30 min) plus GDELT, Wikipedia, Wayback, "
    "CourtListener and Google Fact Check Tools. Full text only where robots.txt and terms allow.",
    "Organise. Syndicated copies merge into source families (MinHash), articles cluster into a "
    "timeline. Haiku labels stances. Mainstream = majority of established + primary sources; "
    "an 'other side' needs a party with standing or >= 5 % coverage.",
    "Claims. Haiku extracts up to 12 checkable claims with who says them. Existing fact-checks "
    "(ClaimReview) are matched first and mapped onto the scale.",
    "Verify. Evidence passages go to Haiku (Sonnet for at most 3 high-risk claims). Code then checks "
    "every quote is verbatim in a fetched document and that Verified / False have 2+ independent "
    "strong sources. Otherwise: Unproven.",
    "Publish. Haiku narrates with evidence markers; unmarked sentences are dropped. The guard applies "
    "snippet limits, disclaimers and nofollow links, holds living-person allegations for review, and "
    "writes every rating to the hash-chained audit log.",
    "Trust operations. Corrections, replies, takedowns and held claims reach the review queue; "
    "each decision is a new rating version, never an edit.",
]


def build():
    e = []
    e += txt("title", 28, 18, "News Lens (working name) - architecture, spec 003-news-lens", 22, SQUID)
    e += txt("sub", 28, 50,
             "Topic in -> mainstream account, other sides, and a rated, cited verdict per claim. "
             "Planning only: nothing built. Local Docker first; AWS Option S + Bedrock later (spec 002).",
             12, SLATE)

    # ---- actors (outside) -------------------------------------------
    e += group("act", 20, 90, 220, 440, "Users", EXT, dashed=True)
    e += card("u1", 34, 125, 192, "R", "Reader", ["free plan, quota", "asks a topic", "reads report"], EXT)
    e += card("u2", 34, 235, 192, "J", "Journalist", ["paid plan", "export, watches,", "alerts"], EXT)
    e += card("u3", 34, 345, 192, "Rv", "Reviewer", ["reviewer role", "approves held", "ratings"], EXT)
    e += card("u4", 34, 455 - 10, 192, "NP", "Named party", ["reply, correction,", "takedown"], EXT)

    # ---- system boundary ----------------------------------------------
    SX, SY, SW, SH = 270, 90, 1290, 820
    e += group("sys", SX, SY, SW, SH,
               "News Lens stack (local: docker compose  |  later: AWS Option S Lambda + Aurora + S3)", SQUID,
               fill="#FCFCFD")

    # edge row
    e += card("spa", 300, 130, 230, "UI", "SPA (React + Vite)",
              ["report, claim drawer,", "source + tier labels,", "methodology, review"], GALAXY, n=1)
    e += card("api", 560, 130, 260, "API", "API (FastAPI)",
              ["reports SSE, claims, sources,", "submissions, review, watches", "auth / quota / SSLCommerz: pilot"], GALAXY)
    e += card("trust", 850, 130, 300, "T", "Trust services",
              ["review queue (risk-ordered),", "corrections / replies / takedowns,", "rating history, disclaimers"], MARS, n=8)
    e += card("cache", 1180, 130, 350, "C", "Caches",
              ["report: topic embedding, 1 h / 24 h / 30 d", "verdict: claim embedding, re-verify 7 / 90 d",
               "HTTP per connector, ETag aware"], ENDOR)
    e += arrow("a_spa_api", 530, 175, [(0, 0), (30, 0)], SQUID, both=True)
    e += arrow("a_api_trust", 820, 175, [(0, 0), (30, 0)], SQUID, both=True)

    # pipeline group
    PX, PY, PW, PH = 290, 270, 1250, 330
    e += group("pipe", PX, PY, PW, PH, "Report graph (LangGraph, provider adapter by role; Haiku 5.5 unless noted)", SMILE)
    e += arrow("a_api_pipe", 690, 222, [(0, 0), (0, 48)], SQUID)
    W, G = 166, 12
    rowA = [
        ("n1", "TP", "Resolve topic", ["Haiku, cap 200", "entities, type, span", "refuse private/minor"], ORBIT, 2),
        ("n2", "C", "Cache lookup", ["report cache hit", "-> replay, $0"], ENDOR, None),
        ("n3", "R", "Retrieve", ["index + GDELT, Wiki,", "Wayback, Court-", "Listener; seed", "fact-checks"], COSMOS, 3),
        ("n4", "X", "Extract text", ["trafilatura", "robots / terms", "hash, 90 d blob"], SMILE, None),
        ("n5", "CL", "Dedup + cluster", ["MinHash families", "event clusters", "timeline"], SMILE, 4),
        ("n6", "ST", "Stance", ["Haiku, cap 1,000", "positions, gate:", "standing or 5 %"], ORBIT, None),
        ("n7", "CX", "Extract claims", ["Haiku, cap 1,200", "max 12, speaker,", "living-person flag"], ORBIT, 5),
    ]
    rowB = [
        ("n8", "FC", "Match fact-checks", ["ClaimReview first", "map to scale"], MARS, None),
        ("n9", "EV", "Gather evidence", ["passages, rerank", "3+ families"], SMILE, None),
        ("n10", "V", "Verify (fan-out)", ["Haiku cap 300", "Sonnet <= 3 high-", "risk claims"], ORBIT, 6),
        ("n11", "OK", "Validate (code)", ["quote verbatim", "2+ strong for", "Verified/False", "else Unproven"], MARS, None),
        ("n12", "N", "Narrate", ["Haiku, cap 1,600", "[e:id] markers", "drop unmarked"], ORBIT, 7),
        ("n13", "G", "Guard + publish", ["snippets <= 300 ch", "nofollow, disclaim.", "hold living-person", "audit events"], MARS, None),
    ]
    for i, (eid, glyph, title, lines, cat, n) in enumerate(rowA):
        x = PX + 14 + i * (W + G)
        e += card(eid, x, PY + 40, W, glyph, title, lines, cat, n=n)
        if i < len(rowA) - 1:
            e += arrow(f"{eid}_a", x + W, PY + 70, [(0, 0), (G, 0)], SQUID, width=1)
    e += arrow("a_wrap", PX + 14 + 6 * (W + G) + W // 2, PY + 158,
               [(0, 0), (0, 30), (-(6 * (W + G)) + 40, 30), (-(6 * (W + G)) + 40, 52)], SQUID, width=1)
    for i, (eid, glyph, title, lines, cat, n) in enumerate(rowB):
        x = PX + 14 + i * (W + G) + 40
        e += card(eid, x, PY + 210, W, glyph, title, lines, cat, n=n)
        if i < len(rowB) - 1:
            e += arrow(f"{eid}_a", x + W, PY + 240, [(0, 0), (G, 0)], SQUID, width=1)
    # validate retry loop
    vx = PX + 14 + 4 * (W + G) + 40
    e += arrow("a_retry", vx + 40, PY + 210, [(0, 0), (0, -14), (-(W + G) + 10, -14), (-(W + G) + 10, 0)], AMBER, dashed=True, width=1)
    e += txt("retry_t", vx - 120, PY + 180, "1 retry", 10, AMBER)
    # SSE back to the API (and on to the SPA)
    e += arrow("a_sse", 720, PY, [(0, 0), (0, -48)], GALAXY)
    e += txt("sse_t", 732, PY - 42, "SSE events: start, topic, stage, timeline, perspective,\nclaim, rating, section, done | error", 10, GALAXY)

    # data row
    DY = 630
    e += group("data", 290, DY, 1250, 180, "Data and workers", NEBULA)
    e += txt("reuse", 304, 830,
             "Reused from the Story Engine pilot: JWT auth, quotas + rate limits, SSLCommerz plans, provider adapter "
             "(anthropic | local | bedrock),\nsemantic cache pattern (MiniLM + pgvector), SSE over fetch, Langfuse callback, "
             "local Docker scripts, AWS Option S template (spec 002).", 11, GREEN)
    e += card("pg", 304, DY + 36, 250, "DB", "PostgreSQL 16 + pgvector",
              ["sources, articles, clusters, topics,", "reports, claims, ratings (immutable),", "evidence, fact-checks, watches"], NEBULA)
    e += card("audit", 568, DY + 36, 220, "A", "Audit log",
              ["append-only, hash chain,", "daily digest, 6-year", "retention"], MARS)
    e += card("blob", 802, DY + 36, 200, "S", "Text blobs",
              ["disk local / S3 prod", "90 d, then quotes only"], ENDOR)
    e += card("redis", 1016, DY + 36, 150, "R", "Redis",
              ["rate limits,", "fetch politeness,", "checkpoints"], NEBULA)
    e += card("ing", 1180, DY + 36, 170, "W", "Ingest worker",
              ["RSS every 30 min", "ETag, feed health", "! prod: keeps Aurora", "  awake (~$45/mo)"], COSMOS, dashed=True)
    e += card("rev", 1364, DY + 36, 162, "W", "Re-verify worker",
              ["daily, bounded", "spend; new rating", "versions"], COSMOS, dashed=True)
    e += arrow("a_pipe_data", 700, PY + PH, [(0, 0), (0, 30)], SQUID)

    # ---- external (outside) -------------------------------------------
    XX = 1590
    e += group("ext", XX, 90, 300, 820, "External services", EXT, dashed=True)
    ext = [
        ("x1", "RSS", "Curated RSS feeds", ["~235 validated, 29+ state", "media labels (vault dir.)"]),
        ("x2", "G", "GDELT DOC 2.0", ["free; article list ~3 mo,", "1 request / 5 s"]),
        ("x3", "W", "Wikipedia + Wayback", ["history, references,", "archived copies"]),
        ("x4", "FC", "Google Fact Check Tools", ["ClaimReview, free key", "IFCN publishers"]),
        ("x5", "CL", "CourtListener v4", ["court records,", "125 requests / day"]),
        ("x6", "$", "Paid news APIs (later)", ["! NewsAPI $449/mo,", "  GNews ~EUR 50/mo: P4"]),
        ("x7", "AI", "LLM provider", ["Anthropic API (local)", "Amazon Bedrock (prod)", "! Bedrock price unverified"]),
        ("x8", "LF", "Langfuse (local)", ["trace per report", "off in prod (spec 002)"]),
    ]
    yy = 125
    for eid, glyph, title, lines in ext:
        dashed = eid in ("x6", "x8")
        cat = ORBIT if eid == "x7" else EXT
        e += card(eid, XX + 14, yy, 272, glyph, title, lines, cat, dashed=dashed)
        yy += 44 + len(lines) * 14 + 10 + 12
    e += arrow("a_ret", PX + PW, PY + 70, [(0, 0), (XX + 14 - PX - PW, -120)], COSMOS)
    e += arrow("a_llm", PX + PW, PY + 245, [(0, 0), (XX + 14 - PX - PW, 270)], ORBIT)
    e += arrow("a_ing", 1350, DY + 60, [(0, 0), (XX + 14 - 1350, -540)], COSMOS, dashed=True, width=1)

    # actors -> system
    e += arrow("a_u1", 226, 160, [(0, 0), (74, 0)], SQUID)
    e += arrow("a_u3", 226, 380, [(0, 0), (50, 0), (50, -200), (74, -200)], MARS, dashed=True, width=1)

    # ---- How it works --------------------------------------------------
    HY = 940
    e += group("how", 20, HY, 1100, 520, "How it works", SQUID)
    for i, s in enumerate(STEPS):
        y = HY + 40 + i * 58
        e += step(f"hs{i}", 44, y + 10, i + 1)
        # wrap at ~150 chars
        words, lines, cur = s.split(), [], ""
        for w_ in words:
            if len(cur) + len(w_) + 1 > 150:
                lines.append(cur)
                cur = w_
            else:
                cur = (cur + " " + w_).strip()
        lines.append(cur)
        e += txt(f"ht{i}", 66, y, "\n".join(lines), 11, SQUID, w=1040)

    # ---- rating scale + guards ----------------------------------------
    RX = 1140
    e += group("scale", RX, HY, 750, 250, "Rating scale (published methodology)", MARS)
    scale = [
        ("Verified", GREEN, "2+ independent strong sources, no credible contrary evidence"),
        ("Mostly true", GREEN, "supported, minor inaccuracy or missing context"),
        ("Mixed", AMBER, "credible sources conflict, or partly accurate"),
        ("Unproven", SLATE, "thin evidence - the default when unsure"),
        ("Misleading", MARS, "accurate parts framed to mislead, key context omitted"),
        ("False", MARS, "contradicted by 2+ strong sources or a primary record"),
        ("Not checkable", EXT, "opinion, prediction: tagged, not rated"),
    ]
    for i, (name, col, d) in enumerate(scale):
        y = HY + 40 + i * 28
        e.append(_base(f"sc{i}", "rectangle", RX + 16, y, 110, 20, backgroundColor=col, strokeColor=col))
        e += txt(f"sc{i}_n", RX + 16, y + 4, name, 10, "#ffffff", align="center", w=110)
        e += txt(f"sc{i}_d", RX + 138, y + 4, d, 11, SQUID)

    e += group("cost", RX, HY + 270, 750, 250, "Cost, effort, open points", SQUID)
    cost = [
        "LLM per cold report (modelled): ~$0.006 all Haiku 5.5; ~$0.021 with 3 Sonnet 5.5 verifications;",
        "  $0 on a cache hit; ~32k input / 5.5k output tokens. Search APIs $0 in MVP (free sources only).",
        "Effort: P0 foundations 5 pd + P1 MVP 34 pd = 39 pd; P2 trust ops 13, P3 production 8, P4 scale 16.",
        "Repo: new 'news-lens' seeded from Story Engine platform code (ADR-001), own constitution.",
        "! Not measured: rating accuracy, latency, real cost. Gold set (300 claims) + red team first.",
        "! Human: name, media-law review, reviewers, paid API budget, ADR-001, plan pricing.",
        "! Legal: living-person allegations held for review; snippets only; takedown + reply flows.",
    ]
    for i, ln in enumerate(cost):
        col = AMBER if ln.startswith("!") else SQUID
        e += txt(f"co{i}", RX + 16, HY + 310 + i * 26, ln, 11, col, w=720)

    e += txt("foot", 28, HY + 540,
             "Generated 2026-10-16 from Projects/News-Lens/Diagrams/news-lens-architecture.py "
             "(pattern: Story-Engine aws-cloud-architecture.py). Do not hand-edit the .excalidraw.",
             11, SLATE)
    return e


def main():
    scene = {"type": "excalidraw", "version": 2,
             "source": "Projects/News-Lens/Diagrams/news-lens-architecture.py",
             "elements": build(),
             "appState": {"gridSize": None, "viewBackgroundColor": "#FAFAFA"}, "files": {}}
    OUT.write_text(json.dumps(scene, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(scene['elements'])} elements)")


if __name__ == "__main__":
    main()
