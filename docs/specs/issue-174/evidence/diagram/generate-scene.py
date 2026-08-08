"""Generate docs/assets/the-loop-workflow.excalidraw — the TWO-loop workflow.

Regenerated for issue-174: the previous scene (issue-150) drew one loop over a
three-artifact spec chain, which stopped being true when issue-163 added
testing-plan.md/verification and issue-172 split the PDLC in two.

Geometry is computed, not hand-placed, so a regeneration stays consistent.
Conventions match the issue-150 scene exactly: Virgil (fontFamily 1), roughness 1,
lineHeight 1.25, and text metrics measured off that scene (0.458 * fontSize per
character, which reproduces its label offsets).
"""

import json

CHAR_W = 0.458  # * fontSize — measured from the issue-150 scene's label offsets
LINE_H = 1.25

_seed = [1000]


def _next_seed():
    _seed[0] += 7
    return _seed[0]


ELEMENTS = []
_index = [0]


def _base(eid, etype, x, y, w, h, **kw):
    _index[0] += 1
    el = {
        "id": eid,
        "type": etype,
        "x": x,
        "y": y,
        "width": w,
        "height": h,
        "angle": 0,
        "strokeColor": kw.get("stroke", "#1e1e1e"),
        "backgroundColor": kw.get("bg", "transparent"),
        "fillStyle": "solid",
        "strokeWidth": kw.get("strokeWidth", 2),
        "strokeStyle": kw.get("strokeStyle", "solid"),
        "roughness": 1,
        "opacity": 100,
        "groupIds": [],
        "frameId": None,
        "index": f"a{_index[0]}",
        "roundness": {"type": 3} if kw.get("round") else None,
        "seed": _next_seed(),
        "version": 2,
        "versionNonce": _next_seed() * 1237 % 2147483647,
        "isDeleted": False,
        "boundElements": kw.get("bound", []),
        "updated": 1785887330200,
        "link": None,
        "locked": False,
    }
    return el


def text(eid, s, x, y, fs=16, color="#1e1e1e", container=None, align="left", valign="top"):
    lines = s.split("\n")
    w = max(len(ln) for ln in lines) * fs * CHAR_W
    h = len(lines) * fs * LINE_H
    el = _base(eid, "text", x, y, w, h, stroke=color)
    el.update(
        {
            "text": s,
            "originalText": s,
            "fontSize": fs,
            "fontFamily": 1,
            "textAlign": align,
            "verticalAlign": valign,
            "containerId": container,
            "lineHeight": LINE_H,
            "autoResize": True,
        }
    )
    ELEMENTS.append(el)
    return el


def box(eid, label, x, y, w, h, stroke, bg, fs=16, shape="rectangle", round=True,
        caption=None, strokeStyle="solid"):
    """A node with a centred label, and an optional grey phase caption beneath it."""
    lines = label.split("\n")
    tw = max(len(ln) for ln in lines) * fs * CHAR_W
    th = len(lines) * fs * LINE_H
    el = _base(eid, shape, x, y, w, h, stroke=stroke, bg=bg,
               round=(round and shape == "rectangle"), strokeStyle=strokeStyle,
               bound=[{"id": f"{eid}_t", "type": "text"}])
    ELEMENTS.append(el)
    text(f"{eid}_t", label, x + (w - tw) / 2, y + (h - th) / 2, fs=fs,
         container=eid, align="center", valign="middle")
    if caption:
        cw = len(caption) * 14 * CHAR_W
        text(f"{eid}_c", caption, x + (w - cw) / 2, y + h + 10, fs=14, color="#757575")
    return el


def zone(eid, label, x, y, w, h, stroke, bg, label_dx=20):
    el = _base(eid, "rectangle", x, y, w, h, stroke=stroke, bg=bg,
               strokeStyle="dashed", round=True)
    ELEMENTS.append(el)
    text(f"{eid}_l", label, x + label_dx, y + 12, fs=16, color=stroke)


def arrow(eid, x, y, pts, start=None, end=None, label=None, stroke="#1e1e1e",
          strokeStyle="solid", label_fs=14):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    w, h = max(xs) - min(xs), max(ys) - min(ys)
    bound = [{"id": f"{eid}_t", "type": "text"}] if label else []
    el = _base(eid, "arrow", x, y, w, h, stroke=stroke, strokeStyle=strokeStyle,
               bound=bound)
    el.update(
        {
            "points": pts,
            "lastCommittedPoint": None,
            "startBinding": {"elementId": start, "focus": 0, "gap": 4} if start else None,
            "endBinding": {"elementId": end, "focus": 0, "gap": 4} if end else None,
            "startArrowhead": None,
            "endArrowhead": "arrow",
            "elbowed": False,
        }
    )
    ELEMENTS.append(el)
    if label:
        # Centre the label on the arrow's midpoint, on a white-ish gap in the line.
        mx, my = x + (min(xs) + max(xs)) / 2, y + (min(ys) + max(ys)) / 2
        lines = label.split("\n")
        tw = max(len(ln) for ln in lines) * label_fs * CHAR_W
        th = len(lines) * label_fs * LINE_H
        text(f"{eid}_t", label, mx - tw / 2, my - th / 2, fs=label_fs,
             container=eid, align="center", valign="middle")


# ---------------------------------------------------------------- the scene ---

BLUE, BLUE_BG = "#1971c2", "#a5d8ff"
ORANGE, ORANGE_BG = "#f08c00", "#ffd8a8"
PURPLE, PURPLE_BG = "#6741d9", "#d0bfff"
TEAL, TEAL_BG = "#0c8599", "#c3fae8"
GREEN, GREEN_BG = "#2f9e44", "#b2f2bb"
PINK, PINK_BG = "#c2255c", "#eebefa"
RUST = "#e8590c"

ZX, ZW = 40, 1460          # every zone shares one left edge and width, so the two
ROW_H = 90                 # loops line up column-by-column and the skipped steps show

# --- the ticket, above everything -------------------------------------------
box("ticket", "ticket opened\nloop:not-started", 70, 30, 210, 80, BLUE, BLUE_BG,
    shape="ellipse")

# --- zone A: the spec chain --------------------------------------------------
zone("spec_zone",
     "Specified and reviewed — each artifact is iterated with feedback until it is locked, then the next is derived",
     ZX, 160, ZW, 230, BLUE, "#dbe4ff", label_dx=360)

SPEC_Y, SPEC_W = 225, 190
box("brainstorm", "brainstorm.md\n(optional)", 70, SPEC_Y, SPEC_W, ROW_H,
    ORANGE, "#fff3bf", caption="loop:brainstorming")
box("reqs", "requirements.md\nor bugfix.md", 355, SPEC_Y, SPEC_W, ROW_H,
    BLUE, BLUE_BG, caption="loop:requirements-definition")
box("design", "design.md", 640, SPEC_Y, SPEC_W, ROW_H, PURPLE, PURPLE_BG,
    caption="loop:design")
box("plan", "testing-plan.md", 925, SPEC_Y, SPEC_W, ROW_H, TEAL, "#99e9f2",
    caption="loop:test-planning")
box("tasks", "tasks.md", 1210, SPEC_Y, SPEC_W, ROW_H, TEAL, TEAL_BG,
    caption="loop:tasks-breakdown")

AY = SPEC_Y + ROW_H / 2
arrow("t_to_b", 175, 110, [[0, 0], [-10, 115]], "ticket", "brainstorm")
arrow("a_conv", 260, AY, [[0, 0], [95, 0]], "brainstorm", "reqs", "convert")
arrow("a_hr1", 545, AY, [[0, 0], [95, 0]], "reqs", "design", "human\nreview")
arrow("a_der", 830, AY, [[0, 0], [95, 0]], "design", "plan", "derived\nfrom it")
arrow("a_hr2", 1115, AY, [[0, 0], [95, 0]], "plan", "tasks", "human\nreview")

# --- zone B: the outer loop ---------------------------------------------------
zone("exec_zone",
     "pdlc-work-item-loop — the OUTER loop: one per work item, executed autonomously",
     ZX, 450, ZW, 230, GREEN, "#d3f9d8")

EX_Y = 515
box("impl", "implementation", 70, EX_Y, 210, ROW_H, ORANGE, ORANGE_BG,
    caption="loop:implementation")
box("verif", "verification\n(across all PRs)", 375, EX_Y, 190, ROW_H, GREEN, GREEN_BG,
    caption="loop:verification")
box("chain", "self · critic · security review\nevidence · capability-docs · briefing",
    660, EX_Y, 300, ROW_H, PINK, PINK_BG, fs=14, caption="loop:needs-review")
box("complete", "complete", 1055, EX_Y, 180, ROW_H, GREEN, GREEN_BG, fs=18,
    shape="ellipse", caption="loop:complete")
box("learn", "learn", 1330, EX_Y, 120, ROW_H, "#9c36b5", PINK_BG, fs=18)

BY = EX_Y + ROW_H / 2
arrow("a_iv", 280, BY, [[0, 0], [95, 0]], "impl", "verif")
arrow("a_vc", 565, BY, [[0, 0], [95, 0]], "verif", "chain")
arrow("a_cc", 960, BY, [[0, 0], [95, 0]], "chain", "complete", "human\napproval")
arrow("a_cl", 1235, BY, [[0, 0], [95, 0]], "complete", "learn")
# tasks -> implementation, routed through the gap between zone A and zone B
arrow("a_hr3", 1305, 315, [[0, 0], [0, 105], [-1130, 105], [-1130, 200]],
      "tasks", "impl", "human review")

# --- zone C: the inner loop, column-aligned with zone B ------------------------
zone("pr_zone",
     "pdlc-pr-loop — the INNER loop: one per pull request, in its own session, starting at implementation",
     ZX, 760, ZW, 230, RUST, "#ffe8cc", label_dx=300)

IN_Y = 825
box("impl2", "implementation\n(this PR's slice)", 70, IN_Y, 210, ROW_H, ORANGE,
    ORANGE_BG, fs=14)
box("verif2", "verification\n(this component)", 375, IN_Y, 190, ROW_H, GREEN,
    GREEN_BG, fs=14)
box("chain2", "self · critic · security review\nreviewer briefing", 660, IN_Y, 300,
    ROW_H, PINK, PINK_BG, fs=14)
box("prapp", "PR review\n(human)", 1055, IN_Y, 180, ROW_H, BLUE, BLUE_BG)
box("done2", "complete", 1330, IN_Y, 120, ROW_H, GREEN, GREEN_BG, shape="ellipse")

CY = IN_Y + ROW_H / 2
arrow("a_p1", 280, CY, [[0, 0], [95, 0]], "impl2", "verif2")
arrow("a_p2", 565, CY, [[0, 0], [95, 0]], "verif2", "chain2")
arrow("a_p3", 960, CY, [[0, 0], [95, 0]], "chain2", "prapp")
arrow("a_p4", 1235, CY, [[0, 0], [95, 0]], "prapp", "done2", "approved,\nor merged")

# --- the one seam between the loops -------------------------------------------
arrow("a_spawn", 175, 605, [[0, 0], [0, 220]], "impl", "impl2",
      "starts one\nper PR", stroke=RUST, strokeStyle="dashed")
arrow("a_await", 1390, 825, [[0, 0], [0, -125], [-1110, -125], [-1110, -265]],
      "done2", "impl",
      "await-inner-loops — the work item WAITS here\nuntil every inner loop it started reaches complete",
      stroke=RUST, strokeStyle="dashed")

scene = {
    "type": "excalidraw",
    "version": 2,
    "source": "https://github.com/MadaraUchiha-314/the-loop",
    "elements": ELEMENTS,
    "appState": {
        "gridSize": 20,
        "gridStep": 5,
        "gridModeEnabled": False,
        "viewBackgroundColor": "#ffffff",
    },
    "files": {},
}

with open("docs/assets/the-loop-workflow.excalidraw", "w", encoding="utf-8") as fh:
    json.dump(scene, fh, indent=2)
    fh.write("\n")

print(f"wrote {len(ELEMENTS)} elements")
