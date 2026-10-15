#!/usr/bin/env python3
"""Shared drawing kit for the Story Engine architecture diagrams (diagram-as-code).

Same primitives as the Mail System kit, Story Engine palette.

One visual language for every view, so the diagrams read as a set:

  * Flat, presentation style: roughness 0, Helvetica, a fixed type scale.
  * Labelled group conventions: every boundary (provider, account,
    region, host, network) is a labelled group with its label top-left.
  * Components are cards: a category line in the accent colour, a title, and
    short body lines. A status chip on each card says LIVE, PLANNED or DEFERRED.
  * Connectors are orthogonal polylines. Colour = which flow; solid = live,
    dashed = planned or deferred. Numbered callouts are explained in a step panel.
  * Views are Excalidraw frames, so one file holds several views.

Seeded RNG, so an unchanged diagram regenerates byte-identical.
Used by generate.py; run `python docs/architecture/generate.py` (or `make diagrams`).
"""
from __future__ import annotations

import json
import random

FONT = 2  # Helvetica: clean sans-serif, supported by every Excalidraw build

# ------------------------------------------------------------------ palette
INK = "#1F2A37"        # titles, primary lines
BODY = "#414D5C"       # body text
MUTED = "#687078"      # secondary text
LINE = "#AAB7B8"       # card borders
PAPER = "#FFFFFF"

# vendor / zone colours
ANTHROPIC = "#CC785C"      # Anthropic clay
ANTHROPIC_BG = "#FBF3EF"
DOCKER = "#1D63ED"         # Docker blue (Model Runner)
DOCKER_BG = "#EEF3FE"
CLOUDFLARE = "#F38020"
CLOUDFLARE_BG = "#FEF6EE"
POSTGRES = "#336791"       # Postgres / pgvector
REDIS = "#D82C20"
LANGFUSE = "#E11D74"       # Langfuse magenta
SSLCOMMERZ = "#0B8A3A"
APP = "#5A4FCF"            # Story Engine application code
APP_BG = "#F5F4FD"
HOST = "#1B7F8C"
HOST_BG = "#EFF7F8"
HOME = "#7D8998"
HOME_BG = "#F7F8F8"
DEVICE = "#3F8624"
DEVICE_BG = "#F2F8EF"
INTERNET = "#7D8998"
CI = "#24292F"

# flows
FLOW_REQUEST = "#0972D3"    # browser -> API -> graph
FLOW_LLM = "#CC785C"        # calls to a model
FLOW_DATA = "#336791"       # DB / cache writes
FLOW_OBS = "#E11D74"        # traces
FLOW_PAY = "#0B8A3A"        # payments
FLOW_OPS = "#8C4FFF"        # CI / ops

# status
STATUS = {
    "LIVE": "#1D8102",
    "PARTIAL": "#B7791F",
    "PLANNED": "#7D5BD6",
    "DEFERRED": "#687078",
    "CHOSEN": "#1D8102",
    "REJECTED": "#D13212",
    "BLOCKED": "#D13212",
}

# ratings (Well-Architected review)
RATING = {"GOOD": "#1D8102", "PARTIAL": "#B7791F", "GAP": "#D13212"}

def char_w(size: float, upper: bool = False) -> float:
    """Rough Helvetica advance width. Generous, so boxes never clip text."""
    return size * (0.62 if upper else 0.56)


class Diagram:
    def __init__(self, seed: int, source: str) -> None:
        self.rng = random.Random(seed)
        self.source = source
        self.elements: list[dict] = []
        self.frames: list[dict] = []
        self._uid = 0
        self.ox = 0.0
        self.oy = 0.0
        self.frame_id: str | None = None

    # -------------------------------------------------------------- basics
    def nid(self, prefix: str) -> str:
        self._uid += 1
        return "%s-%04d" % (prefix, self._uid)

    def _base(self, kind, x, y, w, h, stroke, bg="transparent", sw=1,
              style="solid", opacity=100, roundness=None, fill="solid"):
        e = {
            "id": self.nid(kind[:4]), "type": kind,
            "x": round(x + self.ox, 2), "y": round(y + self.oy, 2),
            "width": round(w, 2), "height": round(h, 2), "angle": 0,
            "strokeColor": stroke, "backgroundColor": bg, "fillStyle": fill,
            "strokeWidth": sw, "strokeStyle": style, "roughness": 0,
            "opacity": opacity, "groupIds": [], "frameId": self.frame_id,
            "roundness": roundness, "seed": self.rng.randint(1, 2**31),
            "version": 1, "versionNonce": self.rng.randint(1, 2**31),
            "isDeleted": False, "boundElements": [], "updated": 1,
            "link": None, "locked": False,
        }
        self.elements.append(e)
        return e

    def text(self, x, y, s, size=14, color=BODY, align="left", width=None,
             upper=False):
        lines = s.split("\n")
        w = width or max(len(l) for l in lines) * char_w(size, upper) + 4
        h = len(lines) * size * 1.25
        tx = x
        if width is None and align == "center":
            tx = x - w / 2
        e = self._base("text", tx, y, w, h, color)
        e.update({
            "text": s, "originalText": s, "fontSize": size, "fontFamily": FONT,
            "textAlign": align, "verticalAlign": "top", "containerId": None,
            "lineHeight": 1.25, "baseline": int(size * 0.8), "autoResize": True,
        })
        return e

    def rect(self, x, y, w, h, stroke=LINE, bg=PAPER, sw=1, style="solid",
             rounded=True, opacity=100):
        return self._base("rectangle", x, y, w, h, stroke, bg, sw, style,
                          opacity, {"type": 3} if rounded else None)

    def ellipse(self, x, y, w, h, stroke, bg):
        return self._base("ellipse", x, y, w, h, stroke, bg, 1, "solid", 100,
                          {"type": 2})

    def group(self, *els):
        gid = self.nid("grp")
        for e in els:
            e["groupIds"].append(gid)
        return gid

    # -------------------------------------------------------------- frames
    def begin_frame(self, x, y, w, h, name):
        fid = self.nid("frame")
        self.frames.append({"id": fid, "x": x, "y": y, "w": w, "h": h,
                            "name": name})
        self.frame_id = fid
        self.ox, self.oy = x, y
        # a clean white sheet behind the view
        self.rect(0, 0, w, h, stroke="transparent", bg=PAPER, rounded=False)

    def end_frame(self):
        self.frame_id = None
        self.ox = self.oy = 0

    def view_header(self, number, title, subtitle, w):
        self.text(40, 28, "%s  %s" % (number, title), 28, INK)
        self.text(40, 70, subtitle, 14, MUTED)
        ln = self.rect(40, 100, w - 80, 1, stroke=LINE, bg=LINE, rounded=False)
        return ln

    # -------------------------------------------------------------- groups
    def boundary(self, x, y, w, h, label, color, bg=None, style="solid",
                 sw=2, sublabel=None):
        """AWS-style group: coloured border, label top-left in a tab."""
        label = label.upper()
        r = self.rect(x, y, w, h, stroke=color, bg=bg or "transparent", sw=sw,
                      style=style, rounded=False)
        tw = len(label) * 12 * 0.74 + 20  # uppercase Helvetica runs wide
        tab = self.rect(x, y, tw, 24, stroke=color, bg=color, rounded=False)
        t = self.text(x + 10, y + 4, label, 12, PAPER, upper=True)
        parts = [r, tab, t]
        if sublabel:
            parts.append(self.text(x + tw + 10, y + 5, sublabel, 12, color))
        return r

    # -------------------------------------------------------------- cards
    def chip(self, x, y, label, color, size=11):
        w = len(label) * char_w(size, True) + 16
        r = self.rect(x, y, w, 20, stroke=color, bg=color)
        t = self.text(x + 8, y + 3, label, size, PAPER, upper=True)
        self.group(r, t)
        return w

    def card(self, x, y, w, h, category, title, body, accent, status=None,
             dashed=False, title_size=16):
        """A component: accent bar, category, title, body, status chip."""
        els = []
        els.append(self.rect(x, y, w, h, stroke=accent if dashed else LINE,
                             bg=PAPER, sw=1, style="dashed" if dashed else "solid"))
        els.append(self.rect(x, y, 6, h, stroke=accent, bg=accent, rounded=False))
        els.append(self.text(x + 18, y + 12, category.upper(), 11, accent, upper=True))
        els.append(self.text(x + 18, y + 28, title, title_size, INK))
        if body:
            els.append(self.text(x + 18, y + 30 + title_size * 1.35, body, 12.5,
                                 BODY))
        self.group(*els)
        if status:
            cw = len(status) * char_w(11, True) + 16
            self.chip(x + w - cw - 10, y - 10, status, STATUS[status])
        return {"x": x, "y": y, "w": w, "h": h}

    def person(self, x, y, w, h, title, body, accent=INK, status=None):
        """C4 person: a card with a head-and-shoulders glyph."""
        els = [self.rect(x, y, w, h, stroke=LINE, bg=PAPER)]
        els.append(self.ellipse(x + 18, y + 16, 22, 22, accent, accent))
        els.append(self._base("rectangle", x + 12, y + 40, 34, 20, accent,
                              accent, 1, "solid", 100, {"type": 3}))
        els.append(self.text(x + 58, y + 14, "PERSON", 11, accent, upper=True))
        els.append(self.text(x + 58, y + 30, title, 16, INK))
        if body:
            els.append(self.text(x + 58, y + 54, body, 12.5, BODY))
        self.group(*els)
        if status:
            cw = len(status) * char_w(11, True) + 16
            self.chip(x + w - cw - 10, y - 10, status, STATUS[status])
        return {"x": x, "y": y, "w": w, "h": h}

    def badge(self, x, y, label, color):
        """Numbered callout centred on (x, y)."""
        d = 26 if len(label) == 1 else 30
        c = self.ellipse(x - d / 2, y - d / 2, d, d, color, color)
        t = self.text(x - d / 2, y - 8, label, 12, PAPER, align="center",
                      width=d, upper=True)
        self.group(c, t)

    # -------------------------------------------------------------- lines
    def line(self, pts, color, style="solid", sw=2, head="arrow", tail=None,
             label=None, label_at=None, badge=None, badge_at=None):
        """Orthogonal connector through absolute-in-frame points."""
        x0, y0 = pts[0]
        rel = [[round(px - x0, 2), round(py - y0, 2)] for px, py in pts]
        xs = [p[0] for p in rel]
        ys = [p[1] for p in rel]
        a = self._base("arrow", x0, y0, max(xs) - min(xs), max(ys) - min(ys),
                       color, sw=sw, style=style, roundness=None)
        a.update({
            "points": rel, "startBinding": None, "endBinding": None,
            "startArrowhead": tail, "endArrowhead": head, "elbowed": False,
            "lastCommittedPoint": None,
        })
        if label:
            lx, ly = label_at
            self.pill(lx, ly, label, color)
        if badge:
            bx, by = badge_at
            self.badge(bx, by, badge, color)
        return a

    def pill(self, cx, cy, label, color, size=11.5):
        """Connector label on a white background so it never sits on a line."""
        lines = label.split("\n")
        w = max(len(l) for l in lines) * char_w(size) + 12
        h = len(lines) * size * 1.25 + 6
        r = self.rect(cx - w / 2, cy - h / 2, w, h, stroke="transparent",
                      bg=PAPER)
        t = self.text(cx - w / 2, cy - h / 2 + 3, label, size, color,
                      align="center", width=w)
        self.group(r, t)

    # -------------------------------------------------------------- panels
    def panel(self, x, y, w, h, title, accent=INK):
        r = self.rect(x, y, w, h, stroke=LINE, bg="#FAFAFA")
        self.rect(x, y, w, 4, stroke=accent, bg=accent, rounded=False)
        self.text(x + 16, y + 14, title.upper(), 12, accent, upper=True)
        return r

    # -------------------------------------------------------------- emit
    def save(self, path):
        for f in self.frames:
            e = {
                "id": f["id"], "type": "frame", "x": f["x"], "y": f["y"],
                "width": f["w"], "height": f["h"], "angle": 0,
                "strokeColor": "#bbb", "backgroundColor": "transparent",
                "fillStyle": "solid", "strokeWidth": 2, "strokeStyle": "solid",
                "roughness": 0, "opacity": 100, "groupIds": [], "frameId": None,
                "roundness": None, "seed": self.rng.randint(1, 2**31),
                "version": 1, "versionNonce": self.rng.randint(1, 2**31),
                "isDeleted": False, "boundElements": [], "updated": 1,
                "link": None, "locked": False, "name": f["name"],
            }
            self.elements.append(e)
        doc = {
            "type": "excalidraw", "version": 2, "source": self.source,
            "elements": self.elements,
            "appState": {"viewBackgroundColor": "#EEF1F4", "gridSize": None},
            "files": {},
        }
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(doc, fh, indent=2, ensure_ascii=True)
            fh.write("\n")
        return len(self.elements)
