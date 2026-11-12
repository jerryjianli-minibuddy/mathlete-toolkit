#!/usr/bin/env python3
"""Builds the Key Move Math website into _site/.

  python3 build.py            use data/live.json for which lessons are public
  python3 build.py --check    ask YouTube which lessons are public now, update data/live.json

A lesson shows its video only once YouTube says it is public, so lessons
scheduled for later appear by themselves on their release day (the GitHub
workflow rebuilds every hour). To add a lesson, add a row to data/lessons.json
and a cover to assets/covers/<slug>.webp, <slug>-lg.webp and <slug>.jpg.
"""
import hashlib, html, json, os, re, shutil, sys, urllib.request, urllib.error
from datetime import date

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "_site")
SITE = "https://keymovemath.com"
YT = "https://www.youtube.com/@keymovemath"
YT_SUB = YT + "?sub_confirmation=1"
# Header socials beside YouTube (Nov 11, Jian: "also add our instagram and tiktok logo next to youtube")
IG = "https://www.instagram.com/keymovemath/"
TT = "https://www.tiktok.com/@keymovemath"
IG_ICON = ('<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2">'
           '<rect x="3" y="3" width="18" height="18" rx="5"/><circle cx="12" cy="12" r="4.2"/>'
           '<circle cx="17.4" cy="6.6" r="1.2" fill="currentColor" stroke="none"/></svg>')
TT_ICON = ('<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" fill="currentColor">'
           '<path d="M14.2 2.5h3.1c.3 2.3 1.8 4 4.2 4.2v3.2c-1.6 0-3-.5-4.2-1.3v6.6a6.3 6.3 0 1 1-6.3-6.3c.3 0 .6 0 '
           '.9.1v3.3a3 3 0 1 0 2.3 2.9z"/></svg>')
NAME = "Key Move Math"
UPLOADED = "2026-11-09"

CONTESTS = {
    "kangaroo": dict(name="Math Kangaroo", slug="math-kangaroo-prep", short="Kangaroo",
                     blurb="Picture puzzles, logic and counting, with no calculator."),
    "noetic": dict(name="Noetic Math Contest", slug="noetic-math-contest-prep", short="Noetic",
                   blurb="Word problems that reward a clean method over long arithmetic."),
    "mathcounts": dict(name="MATHCOUNTS", slug="mathcounts-prep", short="MATHCOUNTS",
                       blurb="Fast, exact answers: counting, rates, number theory and geometry."),
    # AMC split three ways (Nov 11, Jian: "People taking AMC 10 shouldn't be learning AMC 12 material").
    "amc8": dict(name="AMC 8", slug="amc-8-prep", short="AMC 8", soon=True,
                 blurb="Middle school, 25 questions in 40 minutes. Lessons are on the way."),
    "amc10": dict(name="AMC 10", slug="amc-10-prep", short="AMC 10", soon=True,
                  blurb="High school algebra, geometry and counting, no precalculus. Lessons are on the way."),
    "amc12": dict(name="AMC 12", slug="amc-12-prep", short="AMC 12", soon=True,
                  blurb="Everything on AMC 10, plus trig, logarithms and complex numbers. Lessons are on the way."),
    "olympiad": dict(name="Math Olympiad", slug="math-olympiad-prep", short="Olympiad", soon=True,
                     blurb="Short answer, deep thinking. Lessons are on the way."),
}
GRADES = [(str(n), n == 5) for n in range(1, 13)]  # one row and one colour per grade (Jian, Nov 10: "Don't group grades")
# Nov 12, Jian: Noetic only up to Grade 5; Kangaroo up to the Grades 5-6 level ("kangaroo is supposed to be 5 to 6").
MAX_GRADE = {"kangaroo": 6, "noetic": 5}


def offered(k, g):
    return int(g) <= MAX_GRADE.get(k, 12)

# Skill list layout (Nov 11, Jian: "something like ixl.com ... just the look and organization").
# Lessons are grouped into lettered topics and numbered A.1, A.2 ... Groups join lesson "family" values.
TOPICS = [
    ("Number sense", ["Number sense"]),
    ("Number theory and cycles", ["Number theory", "Cycles and mod"]),
    ("Patterns", ["Patterns"]),
    ("Bar models and word problems", ["Bar models", "Algebra", "Division word problems"]),
    ("Algebra readiness", ["Algebra readiness"]),
    ("Rates and averages", ["Rates", "Statistics"]),
    ("Counting", ["Counting"]),
    ("Geometry", ["Geometry: area", "Geometry: counting", "Geometry: circles"]),
    ("Logic and reading the problem", ["Logic", "Problem reading"]),
]
GRADE_COLORS = ["teal", "pink", "navy", "yellow", "red", "teal", "pink"]

e = html.escape


# Cache stamp for site.css and site.js, so phones load the new file the moment a change goes live (Nov 10).
def _asset_v():
    h = hashlib.sha1()
    for f in ("assets/css/site.css", "assets/js/site.js"):
        with open(os.path.join(ROOT, f), "rb") as fh:
            h.update(fh.read())
    return h.hexdigest()[:8]


ASSET_V = _asset_v()


# Lesson fields the search box on lessons/ looks through (Nov 10).
SEARCH_FIELDS = ("tool", "hook", "problem", "topic", "family", "also_called", "search", "move", "trap")


def norm(s):
    """Lower case, punctuation to spaces. assets/js/site.js normalizes a typed search the same way."""
    return re.sub(r"[^a-z0-9#]+", " ", str(s).lower()).strip()


def mmss(s):
    return f"{s // 60}:{s % 60:02d}"


def iso_dur(s):
    return f"PT{s // 60}M{s % 60}S"


# ---------- data ----------

def is_public(vid, known):
    """True when YouTube will play this video for anyone (public or unlisted)."""
    url = "https://www.youtube.com/oembed?format=json&url=https://www.youtube.com/watch?v=" + vid
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "keymovemath-site"}), timeout=20) as r:
            return r.status == 200
    except urllib.error.HTTPError as err:
        return known and err.code not in (401, 403, 404)  # YouTube hiccup: keep what we knew
    except Exception:
        return known


def load():
    lessons = json.load(open(os.path.join(ROOT, "data/lessons.json")))
    live_path = os.path.join(ROOT, "data/live.json")
    saved = json.load(open(live_path)) if os.path.exists(live_path) else {}
    live = set(saved.get("live", []))
    shorts = set(saved.get("shorts", []))
    if "--check" in sys.argv:
        found = set()
        for l in lessons:
            url = ("https://www.youtube.com/oembed?format=json&url=https://www.youtube.com/watch?v="
                   + l["video_id"])
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "keymovemath-site"}), timeout=20) as r:
                    if r.status == 200:
                        found.add(l["video_id"])
            except urllib.error.HTTPError as err:
                if err.code not in (401, 403, 404) and l["video_id"] in live:
                    found.add(l["video_id"])  # YouTube hiccup: keep what we knew
            except Exception:
                if l["video_id"] in live:
                    found.add(l["video_id"])
        live = found
        ids = [l["video_id"] for l in lessons if l["video_id"] in live]
        # Shorts go public an hour after their lesson; a lesson page links its Short only once it plays (Nov 10).
        shorts = {l["short_id"] for l in lessons if l.get("short_id") and is_public(l["short_id"], l["short_id"] in shorts)}
        sids = [l["short_id"] for l in lessons if l.get("short_id") in shorts]
        # Nov 12: an upcoming tool's t/N opens its video only once YouTube plays it for anyone; until then "coming soon".
        up_prev = set(saved.get("upcoming", []))
        upcoming = [t["video_id"] for t in load_upcoming()
                    if t.get("video_id") and is_public(t["video_id"], t["video_id"] in up_prev)]
        json.dump({"live": ids, "shorts": sids, "upcoming": upcoming}, open(live_path, "w"), indent=1)
        print(f"live: {len(ids)} of {len(lessons)}, shorts: {len(sids)}")
    for l in lessons:
        l["live"] = l["video_id"] in live
        l["short_live"] = l["live"] and l.get("short_id") in shorts
        l["contests"] = [c for c in l["contests"] if c in CONTESTS]
    return lessons


# Nov 11: Jian raised every 10-test pack to $24.99; singles stay $3.99 (10 singles = $39.90).
PACK_PRICE, SINGLE_PRICE, PACK_SAVE = "$24.99", "$3.99", "$14.91"


def load_shop():
    """Payhip checkout (Nov 10). Buy buttons show only once the store can take payments: on --check the
    pack page is read, and Payhip's notice that no PayPal or Stripe account is connected keeps them as Coming soon."""
    p = os.path.join(ROOT, "data/shop.json")
    shop = json.load(open(p))
    if "--check" in sys.argv:
        try:
            req = urllib.request.Request(shop["pack"], headers={"User-Agent": "Mozilla/5.0 keymovemath-site"})
            with urllib.request.urlopen(req, timeout=20) as r:
                page = r.read().decode("utf-8", "replace")
            # Only Payhip's own notice turns buttons off; a bot-check page (no price on it) changes nothing.
            # Jian switched checkout on Nov 11 ("Make the payment work on the website. Payhip has been set up").
            if "unable to receive payments" in page:
                ok = False
            elif r.status == 200 and PACK_PRICE in page:
                ok = True
            else:
                ok = shop["live"]
            if ok != shop["live"]:
                shop["live"] = ok
                json.dump(shop, open(p, "w"), indent=1)
            print("checkout live:", ok)
        except Exception as err:
            print("checkout check skipped:", err)
    return shop


# ---------- pieces ----------

def mark(size=34, cls="mark"):
    """Key Move Math mark: teal padlock with its shackle sprung open, yellow key in the keyhole, pink sparks."""
    N = "#0E1A32"
    return (f'<svg class="{cls}" width="{size}" height="{size}" viewBox="-1.08 -1.37 2.5 2.5" aria-hidden="true">'
            f'<g stroke="{N}" stroke-width="0.06" stroke-linejoin="round" stroke-linecap="round">'
            # shackle: half ring, left leg down into the body, right leg lifted out
            f'<path d="M-0.78 0.1V-0.68A0.56 0.56 0 0 1 0.34 -0.68V-0.48H0.11V-0.68A0.33 0.33 0 0 0 -0.55 -0.68V0.1Z" fill="#DCE6F5"/>'
            f'<rect x="-1.03" y="-0.16" width="1.62" height="1.16" rx="0.2" fill="#2BA59A"/>'
            f'</g>'
            # keyhole
            f'<circle cx="-0.22" cy="0.34" r="0.15" fill="{N}"/>'
            f'<path d="M-0.29 0.36H-0.15L-0.11 0.7H-0.33Z" fill="{N}"/>'
            # key: shaft into the keyhole from the right, two teeth, round bow with a hole
            f'<path d="M-0.22 0.24H0.6642A0.36 0.36 0 1 1 0.6642 0.44H0.465V0.5848H0.335V0.44H0.225V0.68H0.095V0.44H-0.22Z'
            f'M1.15 0.34A0.14 0.14 0 1 0 0.87 0.34A0.14 0.14 0 1 0 1.15 0.34Z" fill="#FFD23F" fill-rule="evenodd"'
            f' stroke="{N}" stroke-width="0.06" stroke-linejoin="round"/>'
            f'<path d="M1.2294 0.2201A0.25 0.25 0 0 0 1.0027 0.0901" fill="none" stroke="#fff" stroke-width="0.05" stroke-linecap="round"/>'
            # unlock sparks
            f'<path d="M0.621 -0.358L0.898 -0.4M0.539 -0.528L0.744 -0.719M0.375 -0.622L0.436 -0.895"'
            f' stroke="#E0457B" stroke-width="0.07" stroke-linecap="round"/></svg>')


YT_ICON = ('<svg width="20" height="14" viewBox="0 0 20 14" aria-hidden="true"><rect width="20" height="14" rx="4" fill="#FF0033"/>'
           '<path d="M8 4l5 3-5 3z" fill="#fff"/></svg>')
PLAY = ('<svg class="play" viewBox="0 0 68 48" aria-hidden="true"><path d="M66.5 7.7a8.5 8.5 0 0 0-6-6C55.2.3 34 .3 34 .3s-21.2 0-26.5 1.4a8.5 8.5 0 0 0-6 6C.1 13 .1 24 .1 24s0 11 1.4 16.3a8.5 8.5 0 0 0 6 6C12.8 47.7 34 47.7 34 47.7s21.2 0 26.5-1.4a8.5 8.5 0 0 0 6-6C67.9 35 67.9 24 67.9 24s0-11-1.4-16.3z" fill="#FF0033"/>'
        '<path d="M27 34l18-10-18-10z" fill="#fff"/></svg>')


def head(title, desc, path, root, image=None, noindex=False, extra=""):
    url = SITE + "/" + path
    img = SITE + "/" + (image or "assets/img/og-default.jpg")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
<link rel="canonical" href="{e(url)}">
{'<meta name="robots" content="noindex">' if noindex else ''}
<meta property="og:type" content="website">
<meta property="og:site_name" content="{NAME}">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:url" content="{e(url)}">
<meta property="og:image" content="{e(img)}">
<meta property="og:image:width" content="{1280 if image else 1200}">
<meta property="og:image:height" content="{720 if image else 630}">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#0E1A32">
<link rel="icon" href="{root}assets/img/favicon.svg" type="image/svg+xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800;900&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{root}assets/css/site.css?v={ASSET_V}">
{extra}
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
"""


def nav(root, active=""):
    """Header plus the browse bar (Jian, Nov 10: navigation at the top). Grades, Contests, Tests and Lessons open
    dropdown menus (Nov 11, IXL-style organization; assets/js/site.js). Without JS each trigger is a plain link."""
    def cur(keys):
        return ' aria-current="page"' if active in keys else ""

    def dd(key, label, href, keys, inner, cls=""):
        return (f'<div class="dd" data-dd><a class="cat dd-btn" href="{root}{href}" aria-haspopup="true" aria-expanded="false" '
                f'aria-controls="dd-{key}"{cur(keys)}>{label}<span class="caret" aria-hidden="true"></span></a>'
                f'<div class="dd-menu {cls}" id="dd-{key}">{inner}</div></div>')

    grades = "".join(
        f'<a class="dd-i" href="{root}grade-{g}/"><span class="gl-badge gc-{g}">{g}</span>Grade {g}</a>' if live
        else f'<span class="dd-i dd-off"><span class="gl-badge gc-{g}">{g}</span>Grade {g}<small>soon</small></span>'
        for g, live in GRADES)
    contests = "".join(
        f'<a class="dd-i" href="{root}{C["slug"]}/">{e(C["name"])}{"<small>soon</small>" if C.get("soon") else ""}</a>'
        for C in CONTESTS.values())
    contests += f'<a class="dd-i dd-more" href="{root}contests/">Parents&rsquo; guide to contests</a>'
    tests = ""
    for t in TEST_SETS:
        tests += f'<p class="dd-h">{t["label"]}, {grades_label(t["grades"])}</p>'
        tests += (f'<a class="dd-i" href="{free_href(root, t["contest"], t["grades"][0])}">Diagnostic test</a>'
                  if t["diag"] else '<span class="dd-i dd-off">Diagnostic test<small>soon</small></span>')
        tests += (f'<a class="dd-i" href="{root}mock-tests/{t.get("anchor", "")}">Practice tests</a>' if t["practice"]
                  else '<span class="dd-i dd-off">Practice tests<small>soon</small></span>')
    tests += f'<a class="dd-i dd-more" href="{root}teachers/">For teachers and clubs</a>'
    topics = "".join(
        f'<a class="dd-i" href="{root}grade-5/#topic-{chr(97 + i)}"><span class="dd-letter">{chr(65 + i)}</span>{e(name)}</a>'
        for i, (name, _) in enumerate(TOPICS))
    lessons = (f'<a class="dd-i" href="{root}lessons/">All video lessons</a>'
               f'<a class="dd-i" href="{root}key-moves/">Cheat sheet (print it)</a>'
               f'<a class="dd-i" href="{root}study-plan/">4-week contest plan</a>'
               f'<p class="dd-h">Grade 5 topics</p>{topics}')
    return f"""<header class="top">
 <div class="wrap top-in">
  <a class="brand" href="{root}" aria-label="{NAME} home">{mark(34)}<span><b>KEY MOVE</b> <i>MATH</i></span></a>
  <div class="socials">
   <a class="btn btn-yt btn-sub" href="{YT_SUB}" rel="noopener">{YT_ICON}<span>Subscribe</span></a>
  </div>
 </div>
 <nav class="catbar" aria-label="Browse">
  <div class="wrap cat-in">
   <a class="cat cat-free" href="{root}free/"{cur(("free",))}>Free test</a>
   {dd("grades", "Grades", "#grades-h", ("grade-5",), grades, "dd-grades")}
   {dd("contests", "Contests", "#contests-h", tuple(C["slug"] for C in CONTESTS.values()) + ("contests",), contests)}
   {dd("tests", "Tests", "mock-tests/", ("tests",), tests)}
   {dd("lessons", "Lessons", "lessons/", ("lessons",), lessons)}
   <a class="cat" href="{root}teachers/"{cur(("teachers",))}>Teachers</a>
   <a class="cat" href="{root}about/"{cur(("about",))}>About</a>
  </div>
 </nav>
</header>
<main id="main">
"""


def foot(root, cta=True):
    """cta: the phone-only bar pinned to the bottom of the screen with the free test button (Nov 11).
    Left off on /free, where the page itself is the sign-up."""
    yr = date.today().year
    bar = ""  # Nov 12, Jian: "free diagnostic" was on the site too many times. The pinned phone bar is gone.
    contest_links = "".join(
        f'<li><a href="{root}{c["slug"]}/">{e(c["name"])}{" (soon)" if c.get("soon") else ""}</a></li>' for c in CONTESTS.values())
    return f"""</main>
<footer class="foot">
 <div class="wrap foot-grid">
  <div>
   <a class="brand brand-foot" href="{root}">{mark(30)}<span><b>KEY MOVE</b> <i>MATH</i></span></a>
   <p>Competition math, one key at a time.</p>
   <p class="foot-mail">Stuck on a problem? <a href="mailto:{CONTACT}">{CONTACT}</a></p>
   <a class="btn btn-yt" href="{YT_SUB}" rel="noopener">{YT_ICON}<span>Subscribe on YouTube</span></a>
  </div>
  <div>
   <h3>Learn</h3>
   <ul><li><a href="{root}lessons/">All lessons</a></li><li><a href="{root}grade-5/">Grade 5</a></li>
   <li><a href="{root}key-moves/">Key moves cheat sheet</a></li><li><a href="{root}study-plan/">4-week contest plan</a></li>
   <li><a href="{root}mock-tests/">Mock tests</a></li><li><a href="{root}free/">Diagnostic test</a></li><li><a href="{root}teachers/">For teachers and clubs</a></li><li><a href="{root}math-corner/">Math Corner</a></li></ul>
  </div>
  <div>
   <h3>By contest</h3>
   <ul>{contest_links}</ul>
  </div>
 </div>
 <div class="wrap fine">
  <p>{NAME} is an independent practice channel. It is not affiliated with or endorsed by Math Kangaroo, Noetic Learning, MATHCOUNTS, the MAA (AMC) or any math olympiad. Contest names are used only to describe what each lesson helps with. Every problem in our videos and tests is our own.</p>
  <p>&copy; {yr} {NAME}</p>
 </div>
</footer>
{bar}<script src="{root}assets/js/site.js?v={ASSET_V}" defer></script>
</body>
</html>
"""



def grade_title(g):
    return f"Grades {g.replace('-', ' to ')}" if "-" in g else f"Grade {g}"


def grades_label(gs):
    """[5] -> Grade 5, [5, 6] -> Grades 5 and 6, [6, 7, 8] -> Grades 6 to 8."""
    gs = list(gs)
    if len(gs) == 1:
        return f"Grade {gs[0]}"
    return f"Grades {gs[0]} and {gs[1]}" if len(gs) == 2 else f"Grades {gs[0]} to {gs[-1]}"


def topic_groups(lessons):
    """[(letter, name, [lessons by tool number])]; a family not in TOPICS gets its own group at the end."""
    known = {f for _, fams in TOPICS for f in fams}
    groups = [(name, fams) for name, fams in TOPICS]
    groups += [(f, [f]) for f in sorted({l["family"] for l in lessons} - known)]
    out = []
    for name, fams in groups:
        items = sorted((l for l in lessons if l["family"] in fams), key=lambda l: l["tool_num"])
        if items:
            out.append((chr(ord("A") + len(out)), name, items))
    return out


def skill_list(lessons, root):
    """Lettered topic blocks with numbered skills, in newspaper columns on wide screens."""
    blocks = []
    for i, (letter, name, items) in enumerate(topic_groups(lessons)):
        lis = "".join(
            f'<li class="{"" if l["live"] else "sk-soon"}"><a href="{root}lessons/{l["slug"]}/">'
            f'<span class="sk-code">{letter}.{n}</span><span class="sk-name">{e(l["tool"])}</span>'
            f'{"<span class=sk-play aria-label=Video></span>" if l["live"] else "<span class=sk-tag>soon</span>"}</a></li>'
            for n, l in enumerate(items, 1))
        blocks.append(f'<section class="sk-group sk-{GRADE_COLORS[i % len(GRADE_COLORS)]}" id="topic-{letter.lower()}">'
                      f'<h2><span class="sk-letter">{letter}</span>{e(name)}</h2><ol class="sk-list">{lis}</ol></section>')
    return f'<div class="skills">{"".join(blocks)}</div>'


def grade_picks(sub, g, n=6):
    """Six key moves that mark this grade out: the ones its tests use well above the other grades, then the most used."""
    bg = GRADE_TOOLS.get("by_grade", {})
    others = [set(v) for k, v in bg.items() if k != str(g) and dict(GRADES).get(k)]
    common = {t for t in set().union(*others) if all(t in o for o in others)} if others else set()
    first = [l for l in sub if int(l["tool_num"]) not in common]
    return (first + [l for l in sub if l not in first])[:n]


def grade_list(lessons, root):
    """One row per grade: a coloured badge, the grade, a few of its skills and a link to all of them."""
    rows = []
    for i, (g, live) in enumerate(GRADES):
        badge = f'<span class="gl-badge gc-{g}">{e(g)}</span>'
        sub = grade_lessons(lessons, g) if live else []
        if sub:
            picks = grade_picks(sub, g)
            inc = '<span class="gl-sep">|</span>'.join(f'<a href="{root}lessons/{l["slug"]}/">{e(l["tool"])}</a>' for l in picks)
            rows.append(f'<li class="gl-row">{badge}<div class="gl-body"><h3><a href="{root}grade-{g}/">{grade_title(g)}</a></h3>'
                        f'<p class="gl-inc"><span class="gl-lab">Includes:</span> {inc}</p>'
                        f'<a class="gl-all" href="{root}grade-{g}/">See all {len(sub)} key moves &rarr;</a></div></li>')
        else:
            rows.append(f'<li class="gl-row gl-off">{badge}<div class="gl-body"><h3>{grade_title(g)}</h3>'
                        f'<p class="gl-inc">Coming soon</p></div></li>')
    return f'<ol class="gradelist">{"".join(rows)}</ol>'

def chips(l, root):
    out = []
    for c in l["contests"]:
        C = CONTESTS[c]
        out.append(f'<a class="chip chip-{c}" href="{root}{C["slug"]}/">{e(C["short"])}</a>')
    return "".join(out)


def card(l, root, h="h3", search=False):
    href = f'{root}lessons/{l["slug"]}/'
    data = " ".join(l["contests"])
    hay = ""
    if search:
        words = " ".join(str(l.get(k) or "") for k in SEARCH_FIELDS)
        hay = f' data-search="{e(norm(words))} tool #{l["tool_num"]}"'

    if l["live"]:
        badge = ''
        cls = "card"
    else:
        badge = '<span class="soon">Coming soon</span>'
        cls = "card is-soon"
    return f"""<article class="{cls}" data-contests="{data}" data-family="{e(l['family'])}"{hay}>
 <a class="thumb" href="{href}" tabindex="-1" aria-hidden="true"><img src="{root}assets/covers/{l['slug']}.webp" alt="" width="640" height="360" loading="lazy">{badge}</a>
 <div class="card-body">
  <p class="tool-num">Tool #{l['tool_num']} &middot; {e(l['family'])}</p>
  <{h}><a href="{href}">{e(l['tool'])}</a></{h}>
  <p class="hook">{e(l['hook'])}</p>
 </div>
</article>"""


def grid(lessons, root, h="h3", search=False, gid=""):
    gid = f' id="{gid}"' if gid else ""
    return f'<div class="grid"{gid}>' + "\n".join(card(l, root, h, search) for l in lessons) + "</div>"


def search_form(root, cls="", label="Find a lesson"):
    """Small search box that sends to lessons/?q=... (works without JS: it is a plain GET form)."""
    return f"""<form class="qform {cls}" role="search" action="{root}lessons/" method="get">
   <label for="q-{cls or 'x'}">{label}</label>
   <div class="qrow"><input type="search" id="q-{cls or 'x'}" name="q" placeholder="Try: digits, area, speed" autocomplete="off" enterkeyhint="search">
   <button class="btn btn-primary" type="submit">Search</button></div>
  </form>"""


def test_cta(root, compact=False, contest=None, grade=None):
    """Free-test band at the foot of list pages. compact is kept for old calls; the band has no picture now."""
    # Nov 12, Jian: too many "free diagnostic" mentions. One quiet line instead of a band.
    return (f'<div class="wrap"><p class="quiet-cta">Not sure where to start? '
            f'<a href="{free_href(root, contest, grade)}">Try the diagnostic test</a>.</p></div>')


# ---------- sample pages and parent FAQ (Nov 11) ----------

# Real pages from the PDFs (mock-tests/preview/), small for phones and full size on tap.
SAMPLES = {
    "diagnostic": ("diagnostic-page1-sm.webp", "diagnostic-page1.webp", "Noetic-style diagnostic, page 1",
                   "A QR code beside every problem opens its lesson."),
    "practice": ("sample-test-page1.webp", "sample-test-page1-lg.webp", "Noetic-style practice test, page 1",
                 "Every test in the pack has the same format."),
    "key": ("sample-answer-key.webp", "sample-answer-key-lg.webp", "Answer key",
            "The working and the tool for every answer (Noetic-style Practice Test 3)."),
}


def samples(root, keys=("diagnostic", "practice", "key")):
    figs = []
    for k in keys:
        sm, lg, title, text = SAMPLES[k]
        figs.append(f'<figure class="sample"><a href="{root}assets/img/{lg}" aria-label="{e(title)}, full size">'
                    f'<img src="{root}assets/img/{sm}" srcset="{root}assets/img/{sm} 560w, {root}assets/img/{lg} 1105w" '
                    f'sizes="(min-width: 960px) 340px, 78vw" width="560" height="725" loading="lazy" alt="{e(title)} of a Key Move Math test"></a>'
                    f'<figcaption><b>{e(title)}</b> {e(text)}</figcaption></figure>')
    return f'<div class="samples">{"".join(figs)}</div>'


SHOP = {"live": False}  # set in main() from data/shop.json

# Every test says which contest it is for (Nov 11, Jian: "tests for noetic are marked for noetic, kangaroo for
# kangaroo"), with the not-affiliated line next to it. Links and Drive/Payhip ids stay the same.
TEST_NOTE = ('"Noetic-style" tests are written in the style of the Noetic Learning Math Contest, and "Kangaroo-style" '
             'tests in the style of Math Kangaroo. Key Move Math is not affiliated with or endorsed by Noetic Learning '
             'or Math Kangaroo. Every problem is our own.')


def faqs():
    live = SHOP.get("live")
    return {
        "free": ("Is the test really free?",
                 "Yes. Download the PDF right away. No sign-up and no payment."),
        "who": ("Which grades?",
                "Pick your contest and grade on the test page. New grades are added as they are ready."),
        "misses": ("What do we do with the misses?",
                   "Scan the QR beside the problem to open its lesson. Try the problem again the next day."),
        "original": ("Are the problems copied from real contests?",
                     "No. Every problem is our own. We match real contest difficulty but never copy."),
        "share": ("Can I share the test?",
                  "Yes, with your family or your class."),
        "lessons": ("Do the video lessons cost anything?",
                    "No. Every lesson is free on YouTube, one named tool in about four minutes."),
        "pack": ("What is in the practice pack?",
                 "Ten tests in the diagnostic's format, each with a worked answer key. One PDF for one family or classroom."),
        "when": (("How do I buy the practice tests?",
                  "$3.99 for one test or $24.99 for a pack of 10. The PDF downloads right after checkout.")
                 if live else
                 ("When can I buy the practice tests?",
                  "Checkout opens soon: $3.99 for one test or $24.99 for a pack of 10. Start with the diagnostic meanwhile.")),
        "independent": ("Is Key Move Math run by a contest organizer?",
                        "No. It is an independent practice channel, not affiliated with or endorsed by any contest organizer."),
    }


def faq(keys, h="h2", title="Questions parents ask"):
    """FAQ as <details> (no JS needed). Returns (html, FAQPage JSON-LD script)."""
    F = faqs()
    items = "".join(f'<details class="qa"><summary>{e(F[k][0])}</summary><p>{e(F[k][1])}</p></details>' for k in keys)
    ld = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": F[k][0], "acceptedAnswer": {"@type": "Answer", "text": F[k][1]}} for k in keys]}
    return (f'<div class="faq"><{h}>{title}</{h}>{items}</div>',
            f'<script type="application/ld+json">{json.dumps(ld)}</script>')


def write(path, text):
    full = os.path.join(OUT, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w") as f:
        f.write(text)


# ---------- pages ----------

# Contest countdown on the home page (Nov 12, Jian: "Live competition count down on home page is a great feature!").
# Dates read on 2026-11-12 from each contest's own site. A window means the school, center or chapter picks the day.
# (start, end, label); end = start for a single day.
COUNTDOWN = [
    dict(key="amc8", name="AMC 8", grade="8", note="Window: your school picks the day",
         src="maa.org/AMC", events=[("2027-01-21", "2027-01-27", "Jan 21 to 27, 2027")]),
    dict(key="mathcounts", name="MATHCOUNTS Chapter", grade="7", note="Window: your chapter sets the day",
         src="mathcounts.org critical dates", events=[("2027-02-01", "2027-02-28", "Feb 1 to 28, 2027")]),
    dict(key="kangaroo", name="Math Kangaroo", grade="5", note="One set date",
         src="mathkangaroo.org 2027 flyer", events=[("2027-03-18", "2027-03-18", "Thu, Mar 18, 2027")]),
    dict(key="noetic", name="Noetic", grade="5", note="Window: your school or center picks the day",
         src="noetic-learning.com/mathcontest", events=[("2026-11-12", "2026-11-25", "Fall: Nov 12 to 25, 2026"),
                                                        ("2027-04-01", "2027-04-15", "Spring: Apr 1 to 15, 2027")]),
    dict(key="olympiad", name="MOEMS", grade="5", note="Window: your school picks the day",
         src="moems.org about the program", events=[
             ("2026-11-09", "2026-11-30", "Contest 1: Nov 9 to 30, 2026"), ("2026-12-07", "2026-12-28", "Contest 2: Dec 7 to 28, 2026"),
             ("2027-01-04", "2027-01-25", "Contest 3: Jan 4 to 25, 2027"), ("2027-02-01", "2027-02-22", "Contest 4: Feb 1 to 22, 2027"),
             ("2027-03-01", "2027-03-29", "Contest 5: Mar 1 to 29, 2027")]),
]


_MC_PATH = os.path.join(ROOT, "data/math_corner.json")
MC = sorted(json.load(open(_MC_PATH))["posts"] if os.path.exists(_MC_PATH) else [],
            key=lambda n: (n["date"], n["kind"] == "news"), reverse=True)
LIVE_SLUGS = {}  # set in main(): live lesson slug -> tool name, for Math Corner "related lesson" links


def mc_date(d):
    import datetime
    x = datetime.date.fromisoformat(d)
    return f'{x.strftime("%b")} {x.day}, {x.year}'


def mc_pic(n, card=False):
    """(path, width, height, alt) of a post's picture (Nov 12, Jian 'Do that': a picture on every post). Photos are
    free-license ones with a credit line; the rest is our own art. A missing file falls back to math-corner.svg."""
    img = n.get("img") or ""
    w, h = n.get("img_w", 640), n.get("img_h", 360)
    if not img or not os.path.exists(os.path.join(ROOT, "assets/img/mc", img)):
        return "assets/img/mc/math-corner.svg", 640, 360, "Math Corner"
    if card and img.endswith(".webp"):
        cimg = img[:-5] + "-card.webp"
        if os.path.exists(os.path.join(ROOT, "assets/img/mc", cimg)):
            return "assets/img/mc/" + cimg, 480, 270, n.get("img_alt", "")
    return "assets/img/mc/" + img, w, h, n.get("img_alt", "")


def mc_card(n, root, cls="nw-card"):
    """One Math Corner card. The headline opens our post page; a news card also links straight to the original article
    (Nov 12, Jian: news should take people to the original article)."""
    href = f'{root}math-corner/{n["slug"]}/'
    foot_ = f'<p class="nw-links"><a href="{href}" aria-hidden="true" tabindex="-1">See why it works &rarr;</a></p>'
    src, w, h, alt = mc_pic(n, card=True)
    tag = f'<span class="nw-tag nw-{e(n["tag"].lower())}">{e(n["tag"])}</span>'
    src_name = f'<span class="nw-src">{e(n["source"])}</span>' if n["kind"] == "news" else ""
    if n["kind"] == "news":
        foot_ = (f'<p class="nw-links"><a class="nw-out" href="{e(n["url"])}" rel="noopener" target="_blank">'
                 f'Read the article<span class="sr-only"> (opens {e(n["source"])})</span> &#8599;</a></p>')
    return (f'<li class="{cls}"><a class="nw-pic{' nw-art' if src.endswith('.svg') else ''}" href="{href}" tabindex="-1" aria-hidden="true">'
            f'<img src="{root}{src}" alt="{e(alt)}" width="{w}" height="{h}" loading="lazy" decoding="async"></a>{tag}'
            f'<div class="nw-body"><p class="nw-meta"><time datetime="{n["date"]}">{mc_date(n["date"])}</time>{src_name}</p>'
            f'<h3><a href="{href}">{e(n["title"])}</a></h3><p class="nw-sum">{e(n["summary"])}</p>{foot_}</div></li>')


def mc_strip(root):
    """Math Corner strip under the countdown on the home page (Nov 12, Jian: news near the top so the site feels
    updated; then "mix in some interesting math facts... call it math corner"). Newest 2 news posts from the last ~2
    months plus the newest 2 fact posts; data/math_corner.json holds them all."""
    import datetime
    cut = (datetime.date.today() - datetime.timedelta(days=62)).isoformat()
    news = [n for n in MC if n["kind"] == "news" and n["date"] >= cut][:2]
    facts = [n for n in MC if n["kind"] == "fact"][:4 - len(news)]
    pick = sorted(news + facts, key=lambda n: n["kind"] != "news")
    if len(pick) < 3:
        pick = MC[:3]
    if not pick:
        return ""
    cards = "".join(mc_card(n, root) for n in pick)
    return f"""<section class="nw" aria-labelledby="nw-h">
 <div class="wrap">
  <div class="nw-top"><h2 id="nw-h">Math Corner</h2><span class="nw-swipe" aria-hidden="true">Swipe for more &rarr;</span><a href="{root}math-corner/">See all<span class="sr-only"> math news and facts</span> &rarr;</a></div>
  <div class="nw-scroll"><ul class="nw-list">{cards}</ul></div>
 </div>
</section>
"""


def page_math_corner():
    """/math-corner/: blog index of every post, and one page per post (Nov 12). /news/ redirects here."""
    import datetime
    root = "../"
    body = head(f"Math Corner: Math News and Cool Math Facts for Kids | {NAME}",
                "Math news and cool math facts for kids and parents: prize winners, new discoveries, olympiad results, number tricks and short proofs to show your friends.",
                "math-corner/", root)
    body += nav(root, "math-corner")
    facts = "".join(mc_card(n, root) for n in MC if n["kind"] == "fact")
    groups, order = {}, []
    for n in MC:
        if n["kind"] != "news":
            continue
        k = n["date"][:7]
        if k not in groups:
            groups[k] = []
            order.append(k)
        groups[k].append(n)
    news = ""
    for k in order:
        label = datetime.date.fromisoformat(k + "-01").strftime("%B %Y")
        news += f'<h3 class="nw-month">{label}</h3><ul class="nw-all">{"".join(mc_card(n, root) for n in groups[k])}</ul>'
    body += f"""<section class="page-head"><div class="wrap">
  <h1>Math Corner</h1>
  <p class="lead">Math news and facts you can show off to your friends, in plain words for kids and parents.</p>
  <p class="cg-jump"><a href="#facts-h">Cool math facts</a><a href="#news-h">Math news</a></p>
</div></section>
<section class="sec sec-tight"><div class="wrap nw-page">
 <h2 id="facts-h">Cool math facts</h2>
 <ul class="nw-all">{facts}</ul>
 <h2 id="news-h" class="nw-h2">Math news</h2>
 {news}
 <p class="glance-note">News summaries are our own, and each links to the article we read. Not affiliated with any of the sources.</p>
</div></section>
"""
    body += foot(root)
    write("math-corner/index.html", body)
    for n in MC:
        page_mc_post(n)
    write("news/index.html", '<!doctype html><meta charset="utf-8"><meta name="robots" content="noindex">'
          f'<link rel="canonical" href="{SITE}/math-corner/"><meta http-equiv="refresh" content="0; url=/math-corner/">'
          '<a href="/math-corner/">Math Corner</a>')


def page_mc_post(n):
    root = "../../"
    path = f'math-corner/{n["slug"]}/'
    ld = {"@context": "https://schema.org", "@type": "BlogPosting", "headline": n["title"], "description": n["desc"],
          "datePublished": n["date"], "mainEntityOfPage": SITE + "/" + path,
          "author": {"@type": "Organization", "name": NAME, "url": SITE + "/"},
          "publisher": {"@type": "Organization", "name": NAME, "logo": {"@type": "ImageObject", "url": SITE + "/assets/img/logo-512.png"}}}
    if n["kind"] == "news":
        ld["isBasedOn"] = n["url"]
    psrc, pw, ph, palt = mc_pic(n)
    ld["image"] = SITE + "/" + psrc
    credit = ""
    if n.get("img_credit"):
        lic = (f'<a href="{e(n["img_license_url"])}" rel="noopener license" target="_blank">{e(n["img_license"])}</a>'
               if n.get("img_license_url") else e(n.get("img_license", "")))
        credit = (f'<figcaption>Image: {e(n["img_credit"])}, {lic}, via '
                  f'<a href="{e(n["img_page"])}" rel="noopener" target="_blank">Wikimedia Commons</a></figcaption>')
    fig = (f'<figure class="mc-fig{" mc-photo" if credit else ""}"><img src="{root}{psrc}" alt="{e(palt)}" width="{pw}" height="{ph}" '
           f'fetchpriority="high" decoding="async">{credit}</figure>')
    body = head(f'{n["title"]} | Math Corner | {NAME}', n["desc"], path, root,
                extra=f'<script type="application/ld+json">{json.dumps(ld)}</script>')
    body += nav(root, "math-corner")
    paras = "".join(f"<p>{e(x)}</p>" for x in n["body"])
    formula = f'<p class="mc-formula">{e(n["formula"])}</p>' if n.get("formula") else ""
    if n["kind"] == "news":
        src = (f'<p class="mc-src">Source: <a href="{e(n["url"])}" rel="noopener" target="_blank">Read the original article at '
               f'{e(n["source"])} &#8599;</a></p>')
    else:
        src = ""
    rel = ""
    if n.get("lesson") in LIVE_SLUGS:
        rel = (f'<p class="mc-rel">Related key move: <a href="{root}lessons/{n["lesson"]}/">'
               f'{e(LIVE_SLUGS[n["lesson"]])} video lesson</a></p>')
    more = "".join(f'<li><a href="{root}math-corner/{m["slug"]}/">{e(m["title"])}</a></li>'
                   for m in [m for m in MC if m["slug"] != n["slug"]][:4])
    body += f"""<article class="sec sec-tight"><div class="wrap mc-post">
 <p class="mc-crumb"><a href="{root}math-corner/">Math Corner</a></p>
 <p class="nw-meta"><span class="nw-tag nw-{e(n["tag"].lower())}">{e(n["tag"])}</span><time datetime="{n["date"]}">{mc_date(n["date"])}</time></p>
 <h1>{e(n["title"])}</h1>
 <p class="lead">{e(n["summary"])}</p>
 {fig}{formula}{paras}{src}{rel}
 <div class="mc-more"><h2>More from Math Corner</h2><ul>{more}</ul></div>
</div></article>
"""
    body += foot(root)
    write(path + "index.html", body)


# Black Friday sale (Nov 12, Jian approved: 25% off every Payhip test, Nov 27 to Dec 1, 2026 PT). The banner is in the
# page but hidden; a small script shows it only inside the window, so it appears and disappears on its own.
# "code" is the Payhip coupon; with no code the banner is not built at all.
SALE = dict(code="BLACKFRIDAY25", start="2026-11-27T00:00:00-08:00", end="2026-12-01T23:59:59-08:00",
            when="Nov 27 to Dec 1", off="25% off")


def sale_banner(root, cls=""):
    if not SALE["code"]:
        return ""
    return (f'<div class="sale{cls}" data-sale-start="{SALE["start"]}" data-sale-end="{SALE["end"]}" hidden>'
            f'<p><b>Black Friday:</b> {SALE["off"]} every practice test, {SALE["when"]}. '
            f'Use code <code>{e(SALE["code"])}</code> at checkout.</p>'
            f'<a href="{root}mock-tests/">Shop tests &rarr;</a></div>'
            '<script>(function(){var b=document.currentScript.previousElementSibling,n=Date.now();'
            'if((n>=Date.parse(b.dataset.saleStart)&&n<=Date.parse(b.dataset.saleEnd))||/[?&]salepreview/.test(location.search))b.hidden=false;})();</script>')


def countdown(root):
    """Contest countdown strip at the very top of the home page (Nov 12, Jian: "put it on the top... more visual and
    striking"). The soonest contest gets big ticking day/hour/min/sec tiles; the rest are small cards. Only the soonest
    one links to its diagnostic (Nov 12, Jian: too many "free" mentions). assets/js/site.js re-sorts and ticks live; the build only fills the order and dates."""
    import datetime
    today = datetime.date.today().isoformat()
    items = []
    for c in COUNTDOWN:
        nxt = next((ev for ev in c["events"] if ev[1] >= today), None)
        if not nxt:
            continue
        items.append(("0" if nxt[0] <= today else nxt[0], c, nxt))
    if not items:
        return ""
    items.sort(key=lambda r: r[0])

    def data(c):
        return (f'data-events=\'{e(json.dumps(c["events"]))}\' data-name="{e(c["name"])}" data-note="{e(c["note"])}" '
                f'data-href="{free_href(root, c["key"], c["grade"])}"')
    _, c0, ev0 = items[0]
    open0 = ev0[0] <= today
    tiles = "".join(f'<div class="cdx-u"><b data-u="{u}">--</b><small>{lab}</small></div>'
                    for u, lab in (("d", "days"), ("h", "hours"), ("m", "min"), ("s", "sec")))
    feat = f"""<div class="cdx-feat{' cdx-open' if open0 else ''}" data-cd-feat {data(c0)}>
   <div class="cdx-info">
    <p class="cdx-badge" data-f="badge">{"Open now" if open0 else "Next up"}</p>
    <h3 class="cdx-name" data-f="name">{e(c0["name"])}</h3>
    <p class="cdx-when"><span data-f="when">{e(ev0[2])}</span><small data-f="note">{e(c0["note"])}</small></p>
   </div>
   <div class="cdx-clock" role="timer" aria-live="off">
    <p class="cdx-cap" data-f="cap">{"window closes in" if open0 else "starts in"}</p>
    <div class="cdx-units">{tiles}</div>
   </div>
   <a class="cdx-btn" data-f="href" href="{free_href(root, c0["key"], c0["grade"])}">Take the diagnostic &rarr;</a>
  </div>"""
    cards = "".join(
        f'<li class="cdx-card{" cdx-open" if ev[0] <= today else ""}" {data(c)}><b class="cdx-cn" data-f="name">{e(c["name"])}</b>'
        f'<span class="cdx-cw" data-f="when">{e(ev[2])}</span>'
        f'<span class="cdx-cl" data-f="left">{"Open now" if ev[0] <= today else "Coming up"}</span></li>'
        for _, c, ev in items[1:])
    return f"""<section class="cdx" aria-labelledby="cdx-h" data-countdown>
 <div class="wrap">
  {sale_banner(root)}
  <div class="cdx-top"><h2 id="cdx-h">Contest countdown</h2><span class="cdx-live">Live</span></div>
  {feat}
  <ol class="cdx-list">{cards}</ol>
  <p class="cdx-src">Dates from each contest's official site. Not affiliated with any contest.</p>
 </div>
</section>
"""



def page_home(lessons):
    root = ""
    live = [l for l in lessons if l["live"]]
    feat = live[-1] if live else lessons[0]
    n_live = len(live)
    first = sorted(lessons, key=lambda l: (not l["live"], l["tool_num"]))[:6]
    cards = []
    for k, C in CONTESTS.items():
        n = sum(1 for l in lessons if k in l["contests"] and l["live"])
        total = sum(1 for l in lessons if k in l["contests"])
        if C.get("soon"):
            meta = "Coming soon"
        else:
            meta = f"{total} lessons" if n == total else f"{n} live, {total - n} on the way"
        cards.append(f'<a class="contest c-{k}{" is-soon" if C.get("soon") else ""}" href="{C["slug"]}/"><h3>{e(C["name"])}</h3><span>{meta}</span></a>')
    ld = {"@context": "https://schema.org", "@type": "Organization", "name": NAME, "url": SITE + "/",
          "logo": SITE + "/assets/img/logo-512.png", "sameAs": [YT]}
    site_ld = {"@context": "https://schema.org", "@type": "WebSite", "name": NAME, "url": SITE + "/",
               "potentialAction": {"@type": "SearchAction", "target": SITE + "/lessons/?q={search_term_string}",
                                   "query-input": "required name=search_term_string"}}
    faq_html, faq_ld = faq(("who", "misses", "original", "when", "independent"))
    body = head(f"{NAME}: Free Diagnostic Test and Contest Math Video Lessons",
                "Free contest math diagnostic test. Pick your grade: answer key included, and a QR code beside every problem opens a short video lesson on its key move.",
                "", root, extra=f'<script type="application/ld+json">{json.dumps(ld)}</script><script type="application/ld+json">{json.dumps(site_ld)}</script>' + faq_ld)
    body += nav(root)
    body += countdown(root)
    body += mc_strip(root)
    body += f"""<section class="hero">
 <div class="wrap hero-in">
  <div class="hero-copy">
   <p class="eyebrow eyebrow-y">Contest math</p>
   <h1>Free diagnostic test. <span>A video for every miss.</span></h1>
   <p class="lead">Find the key moves your child still needs.</p>
   <div class="hero-cta">
    <a class="btn btn-primary btn-lg btn-wide" href="{root}free/">Get the test</a>
    <a class="hero-alt" href="lessons/{feat['slug']}/">or watch a lesson first &rarr;</a>
   </div>
   <ul class="hero-trust"><li>PDF</li><li>Answer key</li><li>No sign-up</li></ul>
  </div>
  <div class="hero-media">
   {embed(feat, root, eager=True)}
   <p class="now">{'New' if feat['live'] else 'First up'}: <a href="lessons/{feat['slug']}/">Tool #{feat['tool_num']}, {e(feat['tool'])}</a></p>
  </div>
 </div>
</section>

<section class="trust" aria-label="About our tests">
 <ul class="wrap trust-in">
  <li class="t-orig">Original problems</li>
  <li class="t-check">Worked answer keys</li>
  <li class="t-qr">A lesson for every problem</li>
  <li class="t-yt">Lessons on YouTube</li>
 </ul>
</section>

<section class="sec sec-grades" aria-labelledby="grades-h">
 <div class="wrap">
  <div class="sec-head"><h2 id="grades-h">Pick a grade</h2><a class="more" href="lessons/">All lessons &rarr;</a></div>
  {grade_list(lessons, root)}
  {search_form(root, "home-q", "Find a key move")}
 </div>
</section>

<section class="how" aria-labelledby="how-h">
 <div class="wrap">
  <h2 id="how-h" class="center">How it works</h2>
  <ol class="steps">
   <li><span class="n n1">1</span><h3>Take the diagnostic</h3><p>Pick your contest and grade. Check with the answer key.</p></li>
   <li><span class="n n2">2</span><h3>Watch the key move</h3><p>Scan the QR beside each miss.</p><a class="go" href="lessons/">See all {len(lessons)} lessons &rarr;</a></li>
   <li><span class="n n3">3</span><h3>Practice with the pack</h3><p>Ten Noetic-style Grade 5 tests with worked answer keys.</p><a class="go" href="mock-tests/">See the practice tests &rarr;</a></li>
  </ol>
  <div class="freebies">
   <a class="freebie" href="key-moves/"><b>Key moves cheat sheet</b><span>Every rule and trap on one printable page</span></a>
   <a class="freebie" href="study-plan/"><b>4-week contest plan</b><span>15 to 20 minutes a day, with a miss log</span></a>
   <a class="freebie" href="teachers/"><b>For teachers and clubs</b><span>Run contest practice with a whole class or team</span></a>
  </div>
 </div>
</section>

<section class="sec sec-alt" aria-labelledby="inside-h">
 <div class="wrap">
  <h2 id="inside-h">See inside</h2>
  {samples(root)}
 </div>
</section>


<section class="sec sec-alt">
 <div class="wrap">
  <div class="sec-head"><h2 id="contests-h">Pick your contest</h2><a class="go" href="contests/">Parents' guide to contests &rarr;</a></div>
  <div class="contests contests-short">{''.join(cards)}</div>
 </div>
</section>
<section class="sec" aria-label="Questions parents ask">
 <div class="wrap">{faq_html}</div>
</section>
"""
    body += foot(root)
    write("index.html", body)


def embed(l, root, eager=False):
    if not l["live"]:
        return (f'<div class="player is-soon"><img src="{root}assets/covers/{l["slug"]}-lg.webp" alt="{e(l["tool"])} lesson cover" width="1280" height="720"'
                f'{"" if eager else " loading=lazy"}><span class="soon big">Coming soon</span></div>')
    return (f'<button class="player" data-id="{l["video_id"]}" aria-label="Play: {e(l["tool"])}">'
            f'<img src="{root}assets/covers/{l["slug"]}-lg.webp" alt="{e(l["tool"])} lesson cover" width="1280" height="720"'
            f'{"" if eager else " loading=lazy"}>{PLAY}</button>')


def filter_box(lessons, contests=True, placeholder="Try: digits, area, speed"):
    """Search box, contest buttons, topic menu and live-only switch over a .grid of cards (assets/js/site.js).
    Without JS every lesson shows and the search box is a plain GET form."""
    fams = sorted({l["family"] for l in lessons})
    fam_opts = "".join(f'<option value="{e(f)}">{e(f)}</option>' for f in fams)
    contest_row = ""
    if contests:
        contest_btns = "".join(
            f'<button class="f" data-contest="{k}" aria-pressed="false">{e(C["short"])}</button>'
            for k, C in CONTESTS.items() if not C.get("soon"))
        contest_row = (f'<div class="f-row"><span class="f-label">Grade</span><button class="f" aria-pressed="true" disabled>Grade 5</button><span class="f-note">More grades coming</span></div>\n'
                       f'   <div class="f-row"><span class="f-label">Contest</span><button class="f" data-contest="" aria-pressed="true">All</button>{contest_btns}</div>\n')
    return f"""  <div class="filters" role="group" aria-label="Find and filter lessons">
   <form class="f-row f-search" role="search" action="./" method="get">
    <label class="f-label" for="q">Search</label>
    <input type="search" id="q" name="q" placeholder="{placeholder}" autocomplete="off" enterkeyhint="search" aria-controls="lesson-grid">
    <button class="f f-go" type="submit">Search</button>
   </form>
   {contest_row}   <div class="f-row"><label class="f-label" for="fam">Topic</label><select id="fam"><option value="">All topics</option>{fam_opts}</select>
   <label class="f-check"><input type="checkbox" id="liveonly"> Live only</label></div>
  </div>
  <p class="count" id="count" aria-live="polite">{len(lessons)} lessons</p>
  <div class="empty f-empty" hidden>
   <h2>No lessons match.</h2>
   <p>Try fewer words, or a different {"contest or " if contests else ""}topic.</p>
   <button class="btn btn-primary" type="button" data-clear>Clear filters</button>
  </div>
"""


def page_lessons(lessons):
    root = "../"
    n_live = sum(l["live"] for l in lessons)
    body = head(f"All Lessons | {NAME}",
                "Every Key Move Math lesson in one place. Filter by contest (Math Kangaroo, Noetic, MATHCOUNTS) or topic. Free competition math videos.",
                "lessons/", root)
    body += nav(root, "lessons")
    body += f"""<section class="page-head">
 <div class="wrap">
  <h1>All lessons</h1>
  <p class="lead">One tool per video. {f"{n_live} live now, with 2 new lessons a day and more grades on the way." if n_live < len(lessons) else f"All {len(lessons)} tools are live, with more grades on the way."}</p>
 </div>
</section>
<section class="sec sec-tight">
 <div class="wrap">
{filter_box(lessons)}  {grid(lessons, root, "h2", search=True, gid="lesson-grid")}
 </div>
</section>
"""
    body += test_cta(root, compact=True) + foot(root)
    write("lessons/index.html", body)


def page_lesson(l, lessons):
    root = "../../"
    i = lessons.index(l)
    prev = lessons[i - 1] if i > 0 else None
    nxt = lessons[i + 1] if i + 1 < len(lessons) else None
    contests_txt = ", ".join(CONTESTS[c]["name"] for c in l["contests"])
    desc = (f"{l['hook']}. Learn the {l['tool']} tool for {l['search'].lower() or 'contest math'}: the trap, the rule, "
            f"and problems from easy to hard. Free Grade 5 competition math lesson.")
    ld = ""
    if l["live"]:
        ld = json.dumps({"@context": "https://schema.org", "@type": "VideoObject", "name": l["youtube_title"],
                         "description": desc, "thumbnailUrl": [f"{SITE}/assets/covers/{l['slug']}.jpg"],
                         "uploadDate": UPLOADED,
                         "embedUrl": f"https://www.youtube.com/embed/{l['video_id']}",
                         "contentUrl": f"https://www.youtube.com/watch?v={l['video_id']}",
                         "educationalLevel": "Grade 5", "learningResourceType": "Video lesson"})
        ld = f'<script type="application/ld+json">{ld}</script>'
    crumb_name = f"Tool #{l['tool_num']}: {l['tool']}"
    crumbs_ld = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": "Home", "item": SITE + "/"},
        {"@type": "ListItem", "position": 2, "name": "Lessons", "item": SITE + "/lessons/"},
        {"@type": "ListItem", "position": 3, "name": crumb_name, "item": f"{SITE}/lessons/{l['slug']}/"}]}
    ld += f'<script type="application/ld+json">{json.dumps(crumbs_ld)}</script>'
    body = head(f"{l['tool']}: {l['hook']} | Grade 5 | {NAME}", desc, f"lessons/{l['slug']}/", root,
                image=f"assets/covers/{l['slug']}.jpg", noindex=not l["live"], extra=ld)
    body += nav(root, "lessons")
    status = (f'<a class="btn btn-yt" href="https://www.youtube.com/watch?v={l["video_id"]}" rel="noopener">{YT_ICON}<span>Watch on YouTube</span></a>'
              if l["live"] else '<p class="soon-note">This lesson goes live soon. New lessons come out every day at 7 AM and 4 PM Pacific.</p>')
    if l.get("short_live"):
        status += (f'<a class="btn btn-ghost-d" href="https://www.youtube.com/shorts/{l["short_id"]}" rel="noopener">'
                   f'1-minute Short</a>')
    if nxt:
        next_up = (f'<p class="next-up">Got this one? Next key: <a href="../{nxt["slug"]}/">Tool #{nxt["tool_num"]}, '
                   f'{e(nxt["tool"])} &rarr;</a></p>')
    else:
        next_up = f'<p class="next-up">That was the last tool in this set. <a href="{root}lessons/">Pick another lesson &rarr;</a></p>'
    also = f'<p class="also">Also called: {e(l["also_called"])}</p>' if l["also_called"] else ""
    pn = '<nav class="pn" aria-label="More lessons">'
    if prev:
        pn += f'<a class="pn-prev" href="../{prev["slug"]}/"><small>&larr; Tool #{prev["tool_num"]}</small>{e(prev["tool"])}</a>'
    else:
        pn += "<span></span>"
    if nxt:
        pn += f'<a class="pn-next" href="../{nxt["slug"]}/"><small>Tool #{nxt["tool_num"]} &rarr;</small>{e(nxt["tool"])}</a>'
    pn += "</nav>"
    body += f"""<article class="lesson">
 <div class="wrap">
  <nav class="crumbs" aria-label="Breadcrumb"><ol>
   <li><a href="{root}">Home</a></li>
   <li><a href="{root}lessons/">Lessons</a></li>
   <li><span aria-current="page">{e(crumb_name)}</span></li>
  </ol></nav>
  <div class="lesson-grid">
   <div class="lesson-main">
    {embed(l, root, eager=True)}
    <div class="lesson-actions">{status}</div>
    {next_up}
   </div>
   <aside class="lesson-side">
    <p class="tool-num">Tool #{l['tool_num']} &middot; Grade 5 &middot; {e(l['family'])}</p>
    <h1>{e(l['tool'])}</h1>
    <p class="lesson-hook">{e(l['hook'])}</p>
    <div class="chips">{chips(l, root)}</div>
    <dl class="facts">
     <div class="fact f-prob"><dt>The problem</dt><dd>{e(l['problem'])}</dd></div>
     <div class="fact f-trap"><dt>The trap</dt><dd>{e(l['trap'])}</dd></div>
     <div class="fact f-tool"><dt>The tool</dt><dd>{e(l['rule'])}</dd></div>
    </dl>
    {also}
   </aside>
  </div>
  <aside class="test-box">
   <div>
    <p class="eyebrow">Diagnostic test</p>
    <h2>Which keys does your child still need?</h2>
    <p>Every miss links to its lesson.</p>
   </div>
   <a class="btn btn-primary btn-lg" href="{root}free/">Get the test</a>
  </aside>
  {pn}
 </div>
</article>
"""
    body += foot(root)
    write(f"lessons/{l['slug']}/index.html", body)


# ---------- grade x contest pickers (Nov 11, Jian: "after we click on a grade, we should be able to choose which
# contests. same with contest: if we click contest first, then we will choose the grade") ----------
# Which tests exist for each contest and grade. live=False shows as coming soon.
# diag = a free diagnostic is downloadable now (its PDF is in DIAG_FILES); practice = paid practice tests are on sale.
# Nov 11, Jian: "the diagnostic test is not specific to the contest... we need to change that" -- each contest
# and grade gets its own diagnostic, and a pick without one says Coming soon (never the Noetic test as a stand-in).
TEST_SETS = [
    dict(key="noetic-5", contest="noetic", grades=[5], label="Noetic-style", diag=True, practice=True, store=None, anchor=""),
    dict(key="kangaroo-5-6", contest="kangaroo", grades=[5, 6], label="Kangaroo-style", diag=True, practice=False),
    # Nov 11: Jian shared these three (anyone with the link, viewer).
    dict(key="moems-4-6", contest="olympiad", grades=[4, 5, 6], label="MOEMS-style", diag=True, practice=True, store="moems", anchor="#moems"),
    dict(key="amc8-6-8", contest="amc8", grades=[6, 7, 8], label="AMC 8-style", diag=True, practice=False),
    dict(key="mathcounts-6-8", contest="mathcounts", grades=[6, 7, 8], label="MATHCOUNTS-style", diag=True, practice=False),
]
# Drive id of each diagnostic PDF (must be shared as anyone with the link).
DIAG_FILES = {"noetic-5": "1PReaxlTwr3zcN-xdEyVcYWJtY8c8Tc2p", "kangaroo-5-6": "1ggmbBeozrqJopzf2vQNeLZS5msb5WJ4W",
              "moems-4-6": "1KDVtXFGi7G55y8vQWjZlL2nxNMfDa5L7", "amc8-6-8": "1JnvSg9DMUwY6cukqIYqlf8cWYDRfJy_i",
              "mathcounts-6-8": "1BlwY33l8g6RpS8qLU9rNscYm1cphoDwl"}


def test_live(t):
    return t["diag"] or t["practice"]


def diag_url(t):
    """Direct download of a free diagnostic (Nov 11, Jian: "People can just download. I don't need form. No need for password")."""
    return f"https://drive.google.com/uc?export=download&id={DIAG_FILES[t['key']]}"


def free_href(root, k=None, g=None):
    q = "&".join(x for x in (f"contest={k}" if k else "", f"grade={g}" if g else "") if x)
    return f"{root}free/" + (f"?{q}" if q else "")


# Which key moves each grade (and each grade and contest) really needs (Nov 12, Jian: "Why they have all have 40 key
# moves?"). Built from the tools tagged on the real past tests in the Past Test Database; see "source" in the file.
_GT_PATH = os.path.join(ROOT, "data/grade_tools.json")
GRADE_TOOLS = json.load(open(_GT_PATH)) if os.path.exists(_GT_PATH) else {}


def grade_lessons(lessons, g, k=None):
    """The lessons for a grade (or a grade and contest), most-used first, only those with a video out."""
    nums = (GRADE_TOOLS.get("by_combo", {}).get(f"{g}|{k}") if k else GRADE_TOOLS.get("by_grade", {}).get(str(g)))
    if nums is None and GRADE_TOOLS:
        return []  # no real tests logged for this grade and contest
    if nums is None:
        return [l for l in lessons if str(l["grade"]) == str(g) and (k is None or k in l["contests"]) and l["live"]]
    by = {int(l["tool_num"]): l for l in lessons}
    return [by[n] for n in nums if n in by and by[n]["live"]]


def combo_lessons(lessons, g, k):
    return grade_lessons(lessons, g, k) if offered(k, g) else []


def combo_tests(g, k):
    return [t for t in TEST_SETS if t["contest"] == k and int(g) in t["grades"]]


def combo_live(lessons, g, k):
    """A grade and contest pair gets its own page once it has a lesson or a live test."""
    return offered(k, g) and bool(dict(GRADES).get(str(g))) and bool(combo_lessons(lessons, g, k)) or any(test_live(t) for t in combo_tests(g, k))


def contest_picker(lessons, g, root, current=None):
    on = lambda x: ' pk-on" aria-current="page' if x == current else ""
    items = [f'<a class="pk{on(None)}" href="{root}grade-{g}/">All contests</a>'] if dict(GRADES).get(str(g)) else []
    for k, C in CONTESTS.items():
        if not offered(k, g):
            continue
        if combo_live(lessons, g, k):
            items.append(f'<a class="pk{on(k)}" href="{root}grade-{g}/{k}/">{e(C["name"])}</a>')
        else:
            items.append(f'<span class="pk pk-off">{e(C["name"])}<small>soon</small></span>')
    return (f'<div class="picker"><p class="pk-h">Pick a contest</p>'
            f'<div class="pk-row">{"".join(items)}</div></div>')


def grade_picker(lessons, k, root, current=None):
    items = []
    for g, _ in GRADES:
        if not offered(k, g):
            continue
        badge = f'<span class="gl-badge gc-{g}">{g}</span>'
        if combo_live(lessons, g, k):
            cur = ' pk-on" aria-current="page' if str(g) == str(current) else ""
            items.append(f'<a class="pk pk-g{cur}" href="{root}grade-{g}/{k}/">{badge}Grade {g}</a>')
        else:
            items.append(f'<span class="pk pk-g pk-off">{badge}Grade {g}<small>soon</small></span>')
    return (f'<div class="picker"><p class="pk-h">Pick a grade</p>'
            f'<div class="pk-row pk-grades">{"".join(items)}</div></div>')


def test_blocks(root, tests, g=None):
    """One box per test set: its free diagnostic and practice tests, or Coming soon. g preselects the grade on /free."""
    blocks = []
    for t in tests:
        who = grades_label(t["grades"])
        if test_live(t):
            btns = (f'<a class="btn btn-primary" href="{diag_url(t)}" rel="noopener">Download free test</a>'
                    if t["diag"] else "")
            btns += (f'<a class="btn btn-ghost-d" href="{root}mock-tests/{t.get("anchor", "")}">Practice tests</a>' if t["practice"] and SHOP.get("live")
                     else '<span class="btn btn-ghost-d btn-off">Practice tests soon</span>')
            blocks.append(f'<div class="combo-tests"><div><p class="eyebrow">Tests</p><h2>{t["label"]} tests, {who}</h2>'
                          f'<p>Printable, with a worked answer key.</p></div>'
                          f'<div class="combo-btns">{btns}</div></div>')
        else:
            blocks.append(f'<div class="combo-tests combo-soon"><div><p class="eyebrow">Tests</p>'
                          f'<h2>{t["label"]} tests, {who}</h2><p>Coming soon.</p></div></div>')
    return blocks


def page_combo(lessons, g, k):
    """grade-N/<contest>/: the lessons and tests for one grade and one contest, with both pickers on top."""
    root = "../../"
    C = CONTESTS[k]
    sub = combo_lessons(lessons, g, k)
    tests = combo_tests(g, k)
    slug = f"grade-{g}/{k}"
    blocks = test_blocks(root, tests, g)
    if sub:
        n_live = sum(l["live"] for l in sub)
        inner = (f'<div class="sk-top"><p class="sk-count"><b>{len(sub)}</b> key moves in {len(topic_groups(sub))} topics'
                 f'{f", {n_live} with a video now" if 0 < n_live < len(sub) else ""}.</p></div>'
                 f'<nav class="sk-jump" aria-label="Topics">' + "".join(
                     f'<a href="#topic-{L.lower()}"><b>{L}</b> {e(n)}</a>' for L, n, _ in topic_groups(sub)) + '</nav>'
                 + skill_list(sub, root))
    else:
        inner = ('<div class="empty"><h2>Lessons are on the way</h2>'
                 f'<p>We are building this set now.</p><a class="btn btn-primary" href="{root}lessons/">See all lessons</a></div>')
    body = head(f"Grade {g} {C['name']} Prep: Lessons and Tests | {NAME}",
                f"Grade {g} {C['name']} prep: free video lessons on the key moves that come up most, plus practice tests.",
                f"{slug}/", root)
    body += nav(root, f"grade-{g}")
    body += f"""<section class="page-head">
 <div class="wrap ph-badge">
  <span class="gl-badge gc-{g} gl-big">{g}</span><div>
  <h1>Grade {g} <span class="ph-sep">&middot;</span> {e(C['name'])}</h1>
  <p class="lead">Lessons and tests for {e(C['name'])}, Grade {g}. Independent practice, not affiliated with {e(C['name'])}.</p>
  </div>
 </div>
 {f'<div class="wrap">{playlist_links(g, k)}</div>' if playlist_links(g, k) else ""}
 <div class="wrap pickers">{contest_picker(lessons, g, root, k)}{grade_picker(lessons, k, root, g)}</div>
</section>
<section class="sec sec-tight"><div class="wrap">{"".join(blocks)}{glance(k)}{inner}</div></section>
"""
    body += foot(root)
    write(f"{slug}/index.html", body)


# Contest format at a glance (Nov 11 overnight, toward "insanely useful for parents"). Source: the Contests tab of the
# Past Test Database, which Jian's tests were logged against. Dates are left out on purpose: they move every year.
CONTEST_FACTS = {
    "kangaroo": dict(who="Grades 1 to 6, one test for each pair of grades (1-2, 3-4, 5-6)",
                     rows=[("Questions", "24 for grades 1 to 4, 30 for grades 5 and 6. Multiple choice, 5 options."),
                           ("Time", "75 minutes"),
                           ("Scoring", "3, 4 and 5-point sections. The later problems are harder and worth more.")],
                     q=30, mins=75, pace_label="Pace, grades 5 and 6"),
    "noetic": dict(who="Grades 2 to 5, one test for each grade",
                   rows=[("Questions", "20 short-answer problems"),
                         ("Time", "50 minutes online, no calculator"),
                         ("When", "Fall and Spring"),
                         ("Difficulty", "Problems 1 to 6 easy, 7 to 14 medium, 15 to 20 hard")],
                   q=20, mins=50),
    "mathcounts": dict(who="Grades 6 to 8",
                       rows=[("Sprint round", "30 problems in 40 minutes, no calculator"),
                             ("Target round", "8 problems, given in pairs"),
                             ("Team round", "10 problems"),
                             ("Countdown", "A fast head-to-head round")],
                       q=30, mins=40, pace_label="Sprint round pace"),
    "amc8": dict(who="Grade 8 and below",
                 rows=[("Questions", "25 multiple choice, 5 options"),
                       ("Time", "40 minutes, no calculator"),
                       ("Scoring", "One point for each correct answer"),
                       ("When", "Once a year, in January"),
                       ("Difficulty", "It climbs: the last few problems are the hardest")],
                 q=25, mins=40),
    "amc10": dict(who="Grade 10 and below",
                  rows=[("Questions", "25 multiple choice"),
                        ("Time", "75 minutes"),
                        ("Scoring", "A blank earns partial credit, so guessing can cost points")],
                  q=25, mins=75),
    "amc12": dict(who="Grade 12 and below",
                  rows=[("Questions", "25 multiple choice"),
                        ("Time", "75 minutes"),
                        ("Scoring", "A blank earns partial credit, so guessing can cost points")],
                  q=25, mins=75),
    "olympiad": dict(who="MOEMS: Division E for grades 4 to 6, Division M for grades 6 to 8",
                     rows=[("Contests", "5 a year, from November to March"),
                           ("Questions", "5 short-answer problems in each contest"),
                           ("Time", "30 minutes for each contest, no calculator")]),
}


def pace(q, mins):
    s = round(mins * 60 / q)
    m, r = divmod(s, 60)
    return (f"{m} min {r} s" if m and r else f"{m} min" if m else f"{r} s") + " a problem"


def glance(k):
    """The 'at a glance' card for a contest: who takes it, the format, and the pace to practice at."""
    F = CONTEST_FACTS.get(k)
    if not F:
        return ""
    rows = [("Who", F["who"])] + F["rows"]
    if F.get("q"):
        rows.append((F.get("pace_label", "Pace"), f'About {pace(F["q"], F["mins"])}. Practice with a timer at this speed.'))
    dl = "".join(f'<div><dt>{e(a)}</dt><dd>{e(b)}</dd></div>' for a, b in rows)
    return (f'<section class="glance" aria-labelledby="glance-{k}"><h2 id="glance-{k}">{e(CONTESTS[k]["name"])} at a glance</h2>'
            f'<dl>{dl}</dl><p class="glance-note">Formats can change. Check the contest\'s own site before test day.</p></section>')


def page_group(slug, title, h1, lead, lessons, desc, soon=False, active=None, badge=None, picker="", tests=True, extra="", pl=""):
    root = "../"
    n_live = sum(l["live"] for l in lessons)
    top = (f'<div class="sk-top"><p class="sk-count"><b>{len(lessons)}</b> key moves in {len(topic_groups(lessons))} topics'
           f'{f", {n_live} with a video now" if 0 < n_live < len(lessons) else ""}.</p>'
           f'<div class="sk-links">'
           + (f'<a class="btn btn-ghost-d" href="{root}mock-tests/">Practice tests</a>'
              if tests is True or any(t["practice"] and t["contest"] == tests for t in TEST_SETS) else "")
           + f'<a class="btn btn-ghost-d" href="{root}lessons/">Watch as videos</a></div></div>'
           f'<nav class="sk-jump" aria-label="Topics">' + "".join(
               f'<a href="#topic-{L.lower()}"><b>{L}</b> {e(n)}</a>' for L, n, _ in topic_groups(lessons)) + '</nav>')
    body = head(title, desc, f"{slug}/", root)
    body += nav(root, active or slug)
    if lessons:
        inner = top + skill_list(lessons, root)
    else:
        inner = f"""<div class="empty">
  <h2>Lessons are on the way</h2>
  <p>We are building this set now. Meanwhile, the key moves that are out already help on most contests.</p>
  <a class="btn btn-primary" href="{root}lessons/">See all lessons</a>
 </div>"""
    body += f"""<section class="page-head">
 <div class="wrap{" ph-badge" if badge else ""}">
  {f'<span class="gl-badge gc-{e(badge)} gl-big">{e(badge)}</span>' if badge else ""}<div>
  <h1>{h1}</h1>
  <p class="lead">{lead}</p>
  </div>
 </div>
 {f'<div class="wrap">{pl}</div>' if pl else ""}
 {f'<div class="wrap pickers">{picker}</div>' if picker else ""}
</section>
<section class="sec sec-tight"><div class="wrap">{extra}{glance(tests) if isinstance(tests, str) else ""}{inner}</div></section>
"""
    has_box = isinstance(tests, str) and any(t["diag"] and t["contest"] == tests for t in TEST_SETS)
    body += ("" if has_box else test_cta(root, contest=tests if isinstance(tests, str) else None)) + foot(root)
    write(f"{slug}/index.html", body)


_PL_PATH = os.path.join(ROOT, "data/playlists.json")
PLAYLISTS = [p for p in (json.load(open(_PL_PATH))["playlists"] if os.path.exists(_PL_PATH) else []) if p.get("public")]


def playlist_links(grade=None, contest=None):
    """'Watch the playlist' buttons for a grade, a contest, or both (Nov 12). Only public playlists show.
    Grade + contest: that contest's playlist for the grade, else the grade's all-contests one."""
    g = int(grade) if grade else None
    if g and contest:
        pls = [p for p in PLAYLISTS if p["contest"] == contest and g in p["grades"]] or \
              [p for p in PLAYLISTS if p["contest"] is None and g in p["grades"]]
    elif g:
        pls = [p for p in PLAYLISTS if g in p["grades"]]
    else:
        pls = [p for p in PLAYLISTS if p["contest"] == contest]
    if not pls:
        return ""
    # Nov 12, Jian: "all contests close to each other together, like noetic grade 4, noetic grade 5".
    # Grouped by contest (site order), lowest grade first; the all-contests playlist goes last.
    order = list(CONTESTS)
    pls = sorted(pls, key=lambda p: (p["contest"] is None, order.index(p["contest"]) if p["contest"] in order else 99,
                                     min(p["grades"])))
    return '<div class="pl-row">' + "".join(
        f'<a class="pl-btn" href="https://www.youtube.com/playlist?list={e(p["id"])}" rel="noopener">'
        f'<span class="pl-ic" aria-hidden="true"><svg viewBox="0 0 24 24" width="18" height="18"><path d="M8 5v14l11-7z" fill="#fff"/></svg></span>'
        f'<span class="pl-tx"><b>Watch the playlist</b><small>{e(p["title"])}. Save it on YouTube.</small></span></a>'
        for p in pls) + '</div>'


YES = '<span class="yes" role="img" aria-label="Yes"></span>'


def moems_section(root, shop):
    """MOEMS-style Grades 4 to 6 practice tests (Payhip, Nov 11): pack and singles, same layout as the Noetic block."""
    m, live = shop.get("moems"), shop["live"]
    if not m:
        return ""
    # Nov 12: all 10 seasons and the pack are live on Payhip again.
    pack = ""
    if m.get("pack"):
        pack_btn = (f'<a class="btn btn-primary btn-lg" href="{e(m["pack"])}">Buy all 10 for {PACK_PRICE}</a>' if live
                    else '<span class="btn btn-disabled btn-lg" aria-disabled="true">Coming soon</span>')
        pack = f"""<div class="plan plan-pack">
    <p class="ribbon">Best value</p>
    <p class="eyebrow">All 10 tests</p>
    <h2>MOEMS-style Practice Pack</h2>
    <p class="price"><b>{PACK_PRICE}</b> <s>$39.90</s> <span class="save">Save {PACK_SAVE}</span></p>
    <ul class="facts-row"><li>Grades 4 to 6</li><li>10 tests</li></ul>
    {pack_btn}
   </div>"""
    singles = "\n".join(
        f'    <li><span><b>MOEMS-style Practice Test {n}</b><small>Full season: 25 problems, answer key</small></span><em>{SINGLE_PRICE}</em>'
        + (f'<a class="btn btn-buy" href="{e(u)}">Buy</a>' if live else '<span class="soon-tag">Coming soon</span>') + '</li>'
        for n, u in enumerate(m["tests"], 1))
    return f"""<section class="sec sec-alt" id="moems">
 <div class="wrap">
  <p class="eyebrow">MOEMS-style &middot; Grades 4 to 6</p>
  <h2>MOEMS-style practice tests</h2>
  <p class="lead">Each test is a full season: 5 contests of 5 problems, 30 minutes per contest, written answers, no calculator. Worked answer key.</p>
  <div class="plans{"" if pack else " plans-2"}">
   <div class="plan plan-free">
    <p class="eyebrow">Start here</p>
    <h2>MOEMS-style diagnostic</h2>
    <p class="price"><b>Free</b></p>
    <ul class="facts-row"><li>PDF</li><li>Answer key</li><li>Share with your class</li></ul>
    <a class="btn btn-primary btn-lg" href="{free_href(root, "olympiad", 5)}">Get the diagnostic</a>
   </div>
   <div class="plan">
    <p class="eyebrow eyebrow-n">One test</p>
    <h2>MOEMS-style test</h2>
    <p class="price"><b>{SINGLE_PRICE}</b> each</p>
    <ul class="facts-row"><li>Grades 4 to 6</li><li>PDF</li><li>25 problems</li></ul>
    <a class="btn btn-ghost-d btn-lg" href="#moems-singles">Choose a test</a>
   </div>
   {pack}
  </div>
  <details class="qa singles-box" id="moems-singles"{" open" if live else ""}>
   <summary>MOEMS-style tests, {SINGLE_PRICE} each</summary>
   <ul class="singles">
{singles}
   </ul>
  </details>
  <p class="test-note">"MOEMS-style" tests are written in the style of the Math Olympiads for Elementary and Middle Schools. Key Move Math is not affiliated with or endorsed by MOEMS. Every problem is our own.</p>
 </div>
</section>"""


def page_tests(lessons, shop):
    """Mock tests as a pricing page (Nov 11): free vs single vs pack, what every test holds, sample pages, FAQ.
    Buy buttons link to Payhip only when shop["live"]; until then they say Coming soon and the free test is the action."""
    root = "../"
    live = shop["live"]
    faq_html, _ = faq(("pack", "when", "misses", "original", "independent"))
    if live:
        pack_btn = f'<a class="btn btn-primary btn-lg" href="{e(shop["pack"])}">Buy all 10 for {PACK_PRICE}</a>'
        single_btn = '<a class="btn btn-ghost-d btn-lg" href="#singles">Choose a test</a>'
    else:
        pack_btn = '<span class="btn btn-disabled btn-lg" aria-disabled="true">Coming soon</span>'
        single_btn = '<span class="btn btn-disabled btn-lg" aria-disabled="true">Coming soon</span>'
    soon_note = "" if live else f'<p class="small">Checkout opens soon. <a href="{root}free/">Start with the free test</a>.</p>'
    singles = "\n".join(
        f'    <li><span><b>Noetic-style Grade 5 Practice Test {n}</b><small>20 problems, 50 minutes, answer key</small></span><em>$3.99</em>'
        + (f'<a class="btn btn-buy" href="{e(u)}">Buy</a>' if live else '<span class="soon-tag">Coming soon</span>') + '</li>'
        for n, u in enumerate(shop["tests"], 1))
    body = head(f"Practice Tests: Noetic-style and MOEMS-style | {NAME}",
                "Noetic-style Grade 5 and MOEMS-style Grades 4 to 6 practice tests from $3.99, each with a worked answer key. Start with the free diagnostic test.",
                "mock-tests/", root)
    body += nav(root, "tests")
    body += f"""<section class="page-head">
 <div class="wrap">
  <p class="eyebrow">Practice tests</p>
  <h1>Practice tests</h1>
  <p class="lead">Real contest length, with a worked answer key.</p>
  <p class="pt-jump"><a href="#noetic">Noetic-style, Grade 5</a><a href="#moems">MOEMS-style, Grades 4 to 6</a></p>
  {sale_banner(root, " sale-page")}
 </div>
</section>
<section class="sec sec-tight" id="noetic">
 <div class="wrap">
  <p class="eyebrow">Noetic-style &middot; Grade 5</p>
  <h2>Noetic-style Grade 5 practice tests</h2>
  <div class="plans">
   <div class="plan plan-free">
    <p class="eyebrow">Start here</p>
    <h2>Noetic-style diagnostic</h2>
    <p class="price"><b>Free</b></p>
    <ul class="facts-row"><li>PDF</li><li>Answer key</li><li>Share with your class</li></ul>
    <a class="btn btn-primary btn-lg" href="{root}free/">Get the diagnostic</a>
   </div>
   <div class="plan">
    <p class="eyebrow eyebrow-n">One test</p>
    <h2>Noetic-style Grade 5 test</h2>
    <p class="price"><b>$3.99</b> each</p>
    <ul class="facts-row"><li>Noetic-style</li><li>Grade 5</li><li>PDF</li><li>50 min</li></ul>
    {single_btn}
   </div>
   <div class="plan plan-pack">
    <p class="ribbon">Best value</p>
    <p class="eyebrow">All 10 tests</p>
    <h2>Noetic-style Grade 5 Practice Pack</h2>
    <p class="price"><b>{PACK_PRICE}</b> <s>$39.90</s> <span class="save">Save {PACK_SAVE}</span></p>
    <ul class="facts-row"><li>Noetic-style</li><li>Grade 5</li><li>10 tests</li><li>60 pages</li></ul>
    {pack_btn}
   </div>
  </div>
  {soon_note}
  <p class="test-note">{TEST_NOTE}</p>
  <div class="next-tests"><b>Kangaroo-style tests, Grades 5 and 6</b><span>Coming soon</span></div>
 </div>
</section>
{moems_section(root, shop)}
<section class="sec sec-alt">
 <div class="wrap">
  <h2>Compare</h2>
  <div class="cmp-wrap">
   <table class="cmp">
    <thead><tr><th scope="col"><span class="vh">Feature</span></th><th scope="col">Diagnostic</th><th scope="col">One test</th><th scope="col" class="cmp-best">Pack</th></tr></thead>
    <tbody>
     <tr><th scope="row">Problems</th><td>20</td><td>20</td><td class="cmp-best">200</td></tr>
     <tr><th scope="row">Easy to hard, 50 min</th><td>{YES}</td><td>{YES}</td><td class="cmp-best">{YES}</td></tr>
     <tr><th scope="row">Worked answer key</th><td>{YES}</td><td>{YES}</td><td class="cmp-best">{YES}</td></tr>
     <tr><th scope="row">Lesson QR on every problem</th><td>{YES}</td><td>{YES}</td><td class="cmp-best">{YES}</td></tr>
     <tr><th scope="row">Contest style</th><td>Noetic</td><td>Noetic</td><td class="cmp-best">Noetic</td></tr>
     <tr><th scope="row">Grade</th><td>5</td><td>5</td><td class="cmp-best">5</td></tr>
     <tr><th scope="row">Price</th><td>Free</td><td>$3.99</td><td class="cmp-best">{PACK_PRICE}</td></tr>
    </tbody>
   </table>
  </div>
  {samples(root, ("practice", "key", "diagnostic"))}
 </div>
</section>
<section class="sec">
 <div class="wrap">
  <details class="qa singles-box" id="singles"{" open" if live else ""}>
   <summary>All 10 Noetic-style single tests, $3.99 each</summary>
   <ul class="singles">
{singles}
   </ul>
  </details>
  {faq_html}
 </div>
</section>
"""
    body += foot(root)
    write("mock-tests/index.html", body)


# Free diagnostic tests (Nov 11). Jian, later that day: "People can just download. I don't need form. No need for
# password. Free diagnostic sits next to paid additional practice tests". Each pick on /free shows its PDF download
# beside that contest's paid practice tests, or a short Coming soon line where none are on sale yet.


def store_of(t):
    """Payhip links for a test set: data/shop.json top level is Noetic G5, other sets sit under their own key."""
    return SHOP[t["store"]] if t.get("store") else SHOP


def free_result(root, t):
    """One result panel on /free: the free download next to the paid practice tests for that test set."""
    if t["practice"] and SHOP.get("live"):
        paid = (f'<p>Printable practice tests, each with a worked answer key.</p>'
                f'<div class="fres-btns">'
                + (f'<a class="btn btn-primary" href="{e(store_of(t)["pack"])}" rel="noopener">Get the 10-test pack, {PACK_PRICE}</a>'
                   if store_of(t).get("pack") else "")
                + f'<a class="btn {"btn-ghost-d" if store_of(t).get("pack") else "btn-primary"}" href="{root}mock-tests/{t.get("anchor", "")}">Buy one test, {SINGLE_PRICE}</a></div>')
    else:
        paid = '<p>Practice tests coming soon.</p>'
    return f"""<div class="fres" data-key="{t['key']}">
   <div class="fres-card fres-free"><h2>{t['label']} diagnostic, {grades_label(t['grades'])}</h2>
    <p>Printable PDF with the answer key.</p>
    <div class="fres-btns"><a class="btn btn-primary btn-lg" href="{diag_url(t)}" rel="noopener">Download PDF</a></div></div>
   <div class="fres-card fres-paid"><p class="eyebrow">Practice tests</p><h2>{t['label']} practice tests</h2>{paid}</div>
  </div>"""


def page_free():
    """keymovemath.com/free: one free-test page for every contest and grade. Pick a contest and a grade; a pick with
    a ready diagnostic downloads that test after the form, every other pick says Coming soon (assets/js/site.js).
    ?contest=noetic&grade=5 preselects, so grade and contest pages link straight to their own test."""
    root = "../"
    faq_html, _ = faq(("misses", "share", "original"), title="Questions")
    ready = {}  # contest -> {grade: [test key, label, who]}
    for t in TEST_SETS:
        if t["diag"]:
            who = grades_label(t["grades"])
            for g in t["grades"]:
                ready.setdefault(t["contest"], {})[str(g)] = [t["key"], f'{t["label"]} test, {who}']
    cbtn = "".join(f'<button type="button" class="pk" data-contest="{k}" data-max="{MAX_GRADE.get(k, 12)}">{e(C["name"])}</button>'
                   for k, C in CONTESTS.items())
    tiles = "".join(f'<button type="button" class="gp" data-grade="{g}"><b>Grade {g}</b><span>Coming soon</span></button>'
                    for g in range(1, 13))
    picker = f"""<div class="fpick" data-fpick data-ready='{e(json.dumps(ready))}'>
   <p class="pk-h pk-h-d">Contest</p>
   <div class="pk-row pk-row-d">{cbtn}</div>
   <p class="pk-h pk-h-d">Grade</p>
   <div class="gpick" role="group" aria-label="Pick a grade">{tiles}</div>
   <p class="fpick-msg" aria-live="polite">Pick a contest and a grade.</p>
  </div>"""
    body = head(f"Free Diagnostic Test | {NAME}",
                "Free contest math diagnostic test. Pick your contest and grade and download the PDF, answer key included. No sign-up.",
                "free/", root)
    body += nav(root, "free")
    body += f"""<section class="hero hero-free">
 <div class="wrap">
  <h1>Free diagnostic test</h1>
  <p class="lead">Pick your contest and grade, then download. No sign-up.</p>
  {picker}
  <div class="fres-list">{"".join(free_result(root, t) for t in TEST_SETS if t["diag"])}</div>
  <p class="teacher-note"><b>Teachers:</b> copy it for your class. <a href="{root}teachers/">See our page for teachers and clubs</a>.</p>
  <p class="test-note test-note-d">Every problem is our own. Not affiliated with any contest.</p>
 </div>
</section>
<section class="sec">
 <div class="wrap">
  <ul class="ticks ticks-3">
   <li>Contest-style problems, easy to hard</li>
   <li>Answer key on the last page</li>
   <li>For home or the classroom</li>
  </ul>
  {samples(root, ("diagnostic", "key"))}
 </div>
</section>
<section class="sec sec-alt">
 <div class="wrap">{faq_html}</div>
</section>
"""
    body += foot(root, cta=False)
    write("free/index.html", body)


CONTACT = "keymovemath@gmail.com"  # Nov 11, Jian: "They can email me at keymovemath@gmail.com if they get stuck"


def icon(kind):
    """Small line icons for the About page (our own drawings)."""
    d = {
        "find": '<circle cx="10.5" cy="10.5" r="6.5"/><path d="M15.5 15.5 21 21"/>',
        "key": '<circle cx="7.5" cy="12" r="4.5"/><path d="M12 12h10M18 12v4M21 12v3"/>',
        "unlock": '<rect x="4" y="11" width="16" height="10" rx="2.5"/><path d="M8 11V7.5a4 4 0 0 1 7.6-1.7"/><circle cx="12" cy="16" r="1.4"/>',
        "own": '<path d="M5 4h10l4 4v12H5z"/><path d="M15 4v4h4M8.5 13h7M8.5 16.5h5"/>',
        "check": '<rect x="3.5" y="3.5" width="17" height="17" rx="4"/><path d="m8 12.5 3 3 5.5-6.5"/>',
        "curve": '<path d="M3 20h18"/><path d="M4 17c5 0 7-1.5 9-5s3.5-6 7-7"/>',
        "qr": '<rect x="3.5" y="3.5" width="7" height="7" rx="1"/><rect x="13.5" y="3.5" width="7" height="7" rx="1"/><rect x="3.5" y="13.5" width="7" height="7" rx="1"/><path d="M14 14h3v3h-3zM18 18h2.5v2.5H18z"/>',
        "mail": '<rect x="3" y="5" width="18" height="14" rx="2.5"/><path d="m4 7 8 6 8-6"/>',
    }[kind]
    return (f'<svg class="ic" viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" '
            f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{d}</svg>')


def contact_card(root):
    return f"""<div class="contact-card">
  <span class="cc-ic">{icon("mail")}</span>
  <div><h2>Stuck on a problem? Ask us.</h2>
  <p>Email a question from a lesson or a test, or anything else you need help with. We read every message.</p></div>
  <a class="btn btn-primary btn-lg" href="mailto:{CONTACT}">{CONTACT}</a>
</div>"""


def page_about(lessons):
    root = "../"
    body = head(f"About | {NAME}",
                "Key Move Math teaches competition math as a set of named tools, with free video lessons and mock tests for grades 1 to 12.",
                "about/", root)
    body += nav(root, "about")
    live = [l for l in lessons if l["live"]]
    stats = [(str(len(lessons)), "key moves so far"), (str(len(live)), "video lessons out now"),
             ("10", "Noetic-style practice tests"), ("1 to 12", "grades on the way")]
    stat_html = "".join(f'<li><b>{e(n)}</b><span>{e(t)}</span></li>' for n, t in stats)
    steps = [("find", "Spot the clue", "Every contest problem has clue words. We teach kids to see them first."),
             ("key", "Pick the key move", "Each move has a short name, like Glue It or Find the Cycle, so it sticks."),
             ("unlock", "Unlock the answer", "Use the move, skip the trap, and get it right without long arithmetic.")]
    step_html = "".join(f'<li class="ab-step ab-step-{i}"><span class="ab-ic">{icon(k)}</span><small>Step {i}</small>'
                        f'<h3>{e(t)}</h3><p>{e(x)}</p></li>' for i, (k, t, x) in enumerate(steps, 1))
    lesson_parts = ["A contest-style problem in the first five seconds", "Why it looks hard, and what most kids try first",
                    "The key move, named on every slide", "Problems from easy to hardest, slower on the tough ones",
                    "A last problem to try alone"]
    parts_html = "".join(f'<li><span>{i}</span>{e(t)}</li>' for i, t in enumerate(lesson_parts, 1))
    show = live[0] if live else lessons[0]
    covers = "".join(
        f'<a class="ab-cover" href="{root}lessons/{l["slug"]}/"><img src="{root}assets/covers/{l["slug"]}.webp" '
        f'alt="{e(l["tool"])} lesson cover" loading="lazy" width="640" height="360"><span>{e(l["tool"])}</span></a>'
        for l in live[:6])
    made = [("own", "Every problem is our own", "None is copied from a past contest."),
            ("check", "A worked answer key", "Every test ends with the working for each answer."),
            ("curve", "Matched to real tests", "Same difficulty curve as the real contest: easy first, hardest last."),
            ("qr", "A lesson for every miss", "The answer key names the tool, and a QR code opens its lesson.")]
    made_html = "".join(f'<li><span class="ab-ic">{icon(k)}</span><h3>{e(t)}</h3><p>{e(x)}</p></li>' for k, t, x in made)
    body += f"""<section class="hero ab-hero">
 <div class="wrap ab-hero-in">
  <div class="ab-mark">{mark(150, "mark ab-logo")}</div>
  <div>
   <p class="eyebrow">About us</p>
   <h1>Every contest problem <span>has a key move.</span></h1>
   <p class="lead">Contest math is not about being a genius. It is about knowing the right tool and spotting the trap. We teach one tool at a time.</p>
  </div>
 </div>
 <div class="wrap"><ul class="ab-stats">{stat_html}</ul></div>
</section>
<section class="sec">
 <div class="wrap">
  <h2 class="center">How the key move works</h2>
  <ol class="ab-steps">{step_html}</ol>
 </div>
</section>
<section class="sec sec-alt">
 <div class="wrap ab-lesson">
  <div>
   <h2>What one lesson looks like</h2>
   <ol class="ab-tl">{parts_html}</ol>
   <p><a class="btn btn-ghost-d" href="{root}lessons/">See all lessons</a></p>
  </div>
  <a class="ab-show" href="{root}lessons/{show['slug']}/"><img src="{root}assets/covers/{show['slug']}-lg.webp" alt="{e(show['tool'])} lesson cover" width="1280" height="720" loading="lazy"><span>Watch: {e(show['tool'])}</span></a>
 </div>
</section>
<section class="sec">
 <div class="wrap">
  <h2 class="center">A few of our key moves</h2>
  <div class="ab-covers">{covers}</div>
 </div>
</section>
<section class="sec sec-alt">
 <div class="wrap ab-made">
  <div>
   <h2>How we make every test</h2>
   <ul class="ab-cards">{made_html}</ul>
   <p><a class="btn btn-primary" href="{root}free/">See for yourself: try the diagnostic</a></p>
  </div>
  <img class="ab-sheet" src="{root}assets/img/sample-test-page1.webp" alt="Page 1 of a Key Move Math practice test" width="560" height="725" loading="lazy">
 </div>
</section>
<section class="sec">
 <div class="wrap">
  {contact_card(root)}
  <p class="note ab-note">{NAME} is an independent practice channel. It is not affiliated with or endorsed by Math Kangaroo, Noetic Learning, MATHCOUNTS, the MAA (AMC) or any math olympiad.</p>
  <p class="center"><a class="btn btn-yt" href="{YT_SUB}" rel="noopener">{YT_ICON}<span>Subscribe on YouTube</span></a></p>
 </div>
</section>
"""
    body += foot(root)
    write("about/index.html", body)


def page_cheatsheet(lessons):
    """/key-moves/: every key move on one printable page: the tool, its rule and the trap to avoid.
    Built for the fridge or the pencil case (Nov 11 overnight)."""
    root = "../"
    blocks = []
    for i, (letter, name, items) in enumerate(topic_groups(lessons)):
        rows = "".join(
            f'<li><a href="{root}lessons/{l["slug"]}/"><b>{e(l["tool"])}</b></a>'
            f'<span class="cs-rule">{e(l["rule"])}</span><span class="cs-trap">Trap: {e(l["trap"])}</span></li>'
            for l in items)
        blocks.append(f'<section class="cs-group sk-{GRADE_COLORS[i % len(GRADE_COLORS)]}"><h2><span class="sk-letter">{letter}</span>{e(name)}</h2><ol>{rows}</ol></section>')
    body = head(f"Key Moves Cheat Sheet: Every Competition Math Tool on One Page | {NAME}",
                "Every competition math key move on one printable page: the tool, the rule and the trap to avoid. Free.",
                "key-moves/", root)
    body += nav(root, "lessons")
    body += f"""<section class="page-head">
 <div class="wrap">
  <h1>Key moves cheat sheet</h1>
  <p class="lead">Every tool on one page: the rule, and the trap to avoid. Print it and keep it by the practice tests.</p>
  <p class="cs-actions"><button type="button" class="btn btn-primary" data-print>Print it</button>
  <a class="btn btn-ghost-d" href="{root}lessons/">Watch the lessons</a></p>
 </div>
</section>
<section class="sec sec-tight"><div class="wrap cs">
 <p class="cs-print-head">{NAME} &middot; Key moves cheat sheet &middot; keymovemath.com/key-moves</p>
 {"".join(blocks)}
</div></section>
"""
    body += foot(root)
    write("key-moves/index.html", body)


def page_plan():
    """/study-plan/: a 4-week plan a parent can run in 15 to 20 minutes a day, plus a printable miss log
    (Nov 11 overnight, toward "insanely useful for parents and kids")."""
    root = "../"
    weeks = [
        ("Week 1", "Find the gaps",
         f'Take the <a href="{root}free/">diagnostic test</a> with a timer. Mark every miss, then watch the lesson for one miss a day.'),
        ("Week 2", "One key move a day",
         f'Watch one <a href="{root}lessons/">lesson</a>. Try each problem on pause. Then your child says the rule back in one sentence.'),
        ("Week 3", "Mix and time",
         f'Do one timed <a href="{root}mock-tests/">practice test</a>. The next day, redo every miss without looking at the key.'),
        ("Week 4", "Test-day pace",
         f'One more timed test at the contest\'s pace. Read the traps on the <a href="{root}key-moves/">cheat sheet</a>. Rest the day before.'),
    ]
    tips = ["Before any working, ask: what is the question asking?",
            "Praise the method, not just the answer.",
            "Stuck for 3 minutes? Skip it, and come back at the end.",
            "Every miss goes in the miss log. Redo it a week later."]
    wk = "".join(f'<li><span class="pl-wk">{a}</span><h3>{b}</h3><p>{c}</p></li>' for a, b, c in weeks)
    tp = "".join(f"<li>{e(t)}</li>" for t in tips)
    rows = "".join("<tr><td></td><td></td><td></td><td></td><td></td></tr>" for _ in range(10))
    body = head(f"4-Week Math Contest Study Plan for Parents | {NAME}",
                "A free 4-week plan to get ready for a math contest in 15 to 20 minutes a day, with a printable miss log.",
                "study-plan/", root)
    body += nav(root, "plan")
    body += f"""<section class="page-head">
 <div class="wrap">
  <h1>4-week contest plan</h1>
  <p class="lead">15 to 20 minutes a day. It works for any contest.</p>
  <p class="cs-actions"><button type="button" class="btn btn-primary" data-print>Print the plan and miss log</button></p>
 </div>
</section>
<section class="sec sec-tight"><div class="wrap">
 <p class="cs-print-head">{NAME} &middot; 4-week contest plan &middot; keymovemath.com/study-plan</p>
 <ol class="wk-plan">{wk}</ol>
 <div class="pl-two">
  <section class="pl-tips"><h2>Four habits that help</h2><ul>{tp}</ul></section>
  <section class="pl-log"><h2>Miss log</h2>
   <table><thead><tr><th>Date</th><th>Problem</th><th>Trap</th><th>Key move</th><th>Redo</th></tr></thead><tbody>{rows}</tbody></table>
  </section>
 </div>
</div></section>
"""
    body += foot(root)
    write("study-plan/index.html", body)


# /contests/ parents' guide (Nov 12, Jian: "more informative, like what the contests are for, difficulty, path to
# college, why we take those"). Facts checked Nov 12, 2026 on each contest's own site: maa.org (AMC page and
# maa-invitational-competitions), mathcounts.org (competition series, critical dates), mathkangaroo.org (logistics,
# FAQ, about), noetic-learning.com/mathcontest (home, FAQ, procedures), moems.org (home, about, contests).
# Difficulty is our own 1 to 5 view and the page says so.
GUIDE = [
    dict(k="kangaroo", name="Math Kangaroo", grades="Grades 1 to 12", ours="Our lessons: grades 1 to 6", diff=2,
         dl="Easy start, hard finish",
         what="An international contest of picture puzzles, logic and counting. A friendly first contest.",
         rows=[("Run by", "Math Kangaroo USA, a nonprofit. An international committee writes the questions."),
               ("Test day", "24 questions (grades 1 to 4) or 30 (grade 5 and up) in 75 minutes. Multiple choice, no calculator, no penalty for a wrong answer."),
               ("When", "Once a year, the third Thursday in March. Next: March 18, 2027."),
               ("How to enter", "Sign up yourself and test at a registered center."),
               ("Why take it", "Low pressure and open to any child who reads on their own. Every child gets a certificate."),
               ("Where it leads", "It stands alone. The top 20 in the country and top 3 in each state are recognized.")]),
    dict(k="noetic", name="Noetic Math Contest", grades="Grades 2 to 8", ours="Our lessons: grades 2 to 5", diff=2,
         dl="Gentle to medium",
         what="A school contest, twice a year, with word problems that reward a clean method.",
         rows=[("Run by", "Noetic Learning."),
               ("Test day", "20 problems with number answers, no calculator. The online version gives 50 minutes."),
               ("When", "Fall (Nov 12 to 25, 2026) and spring (Apr 1 to 15, 2027)."),
               ("How to enter", "Through a school team, or the At-Home edition, which gives an unofficial score."),
               ("Why take it", "Two tries a year, so you can see growth. The top half nationally get a ribbon, the top 10% a medal."),
               ("Where it leads", "It stands alone. A good step toward MOEMS and MATHCOUNTS.")]),
    dict(k="olympiad", name="MOEMS (Math Olympiad)", grades="Grades 4 to 8", ours="Our tests: grades 4 to 6", diff=3,
         dl="Few problems, deep thinking",
         what="Five short contests, one a month, that teach out-of-the-box problem solving.",
         rows=[("Run by", "MOEMS, a nonprofit running since 1979."),
               ("Test day", "5 problems in 30 minutes. Division E is grades 4 to 6, Division M grades 6 to 8."),
               ("When", "One contest a month, November to March."),
               ("How to enter", "Through a school or homeschool team of up to 35 students."),
               ("Why take it", "A whole season builds steady habits. Patches for the top half, pins for the top 10%."),
               ("Where it leads", "It stands alone. Strong practice for MATHCOUNTS and the AMC 8.")]),
    dict(k="mathcounts", name="MATHCOUNTS", grades="Grades 6 to 8", ours="Our lessons: grades 6 to 8", diff=4,
         dl="Speed and accuracy, harder at each level",
         what="The big middle school contest, with individual rounds, a team round and a fast head-to-head finale.",
         rows=[("Run by", "The MATHCOUNTS Foundation."),
               ("Test day", "Four rounds over about 3 hours. The Sprint round is 30 problems in 40 minutes with no calculator."),
               ("When", "Chapter contests in February 2027, state in March, national May 9 to 10, 2027."),
               ("How to enter", "Through a school team. If the school doesn't take part, a student can enter on their own."),
               ("Why take it", "Team spirit and a clear ladder to climb."),
               ("Where it leads", "School, then chapter, state and national. The top 4 in each state go to nationals, all expenses paid.")]),
    dict(k="amc8", name="AMC 8", grades="Grade 8 and below", ours="Lessons coming soon", diff=3,
         dl="It climbs: the last problems are hard",
         what="The first contest on the AMC ladder, with problems beyond the school curriculum.",
         rows=[("Run by", "The Mathematical Association of America (MAA)."),
               ("Test day", "25 questions in 40 minutes. Students must be under 15.5 on test day."),
               ("When", "Once a year. Next: January 21 to 27, 2027."),
               ("How to enter", "Through a school or a host site such as a college, math circle or learning center. Parents can't register with the MAA directly."),
               ("Why take it", "A great first look at real contest math, and a goal for the middle school years."),
               ("Where it leads", "To the AMC 10 in high school. The AMC 8 itself doesn't lead to the AIME.")]),
    dict(k="amc10", name="AMC 10", grades="Grade 10 and below", ours="Lessons coming soon", diff=4,
         dl="Hard",
         what="High school algebra, geometry, counting and number theory, with no precalculus.",
         rows=[("Run by", "The MAA."),
               ("Test day", "25 multiple choice questions in 75 minutes. Students must be under 17.5 on test day."),
               ("When", "Every November, on an A date and a B date. A student can take both."),
               ("How to enter", "Through a school or host site, like the AMC 8."),
               ("Why take it", "The MAA calls it the first step toward the US team for the International Math Olympiad."),
               ("Where it leads", "At least the top 2.5% are invited to the AIME.")]),
    dict(k="amc12", name="AMC 12", grades="Grade 12 and below", ours="Lessons coming soon", diff=5,
         dl="The hardest here",
         what="Everything on the AMC 10, plus trig, logarithms and complex numbers.",
         rows=[("Run by", "The MAA."),
               ("Test day", "25 multiple choice questions in 75 minutes. Students must be under 19.5 on test day."),
               ("When", "Every November, on the same dates as the AMC 10."),
               ("How to enter", "Through a school or host site."),
               ("Why take it", "The main road to the AIME and the USAMO for juniors and seniors."),
               ("Where it leads", "At least the top 5% are invited to the AIME.")]),
]
GUIDE_GRADES = [
    ("Grades 1 to 3", ["kangaroo", "noetic"], "Noetic starts in grade 2."),
    ("Grades 4 and 5", ["kangaroo", "noetic", "olympiad"], ""),
    ("Grade 6", ["kangaroo", "noetic", "olympiad", "mathcounts", "amc8"], ""),
    ("Grades 7 and 8", ["mathcounts", "amc8", "olympiad", "kangaroo", "noetic"], ""),
    ("High school", ["amc10", "amc12", "kangaroo"], ""),
]


def page_compare():
    """/contests/: a parents' guide to the contests (Nov 12). One card per contest, then the AMC and MATHCOUNTS
    ladders and an honest note on college. Kept short enough to skim on a phone."""
    root = "../"
    by_k = {g["k"]: g for g in GUIDE}
    jump = "".join(f'<a href="#c-{g["k"]}">{e(g["name"])}</a>' for g in GUIDE)
    def glink(k):
        return f'<a href="#c-{k}">{e(by_k[k]["name"])}</a>'
    grade_rows = "".join(
        f'<li><b>{e(lab)}</b><span>{", ".join(glink(k) for k in ks)}'
        + (f'<small>{e(note)}</small>' if note else "") + '</span></li>'
        for lab, ks, note in GUIDE_GRADES)

    def meter(n):
        return (f'<span class="cg-meter" role="img" aria-label="Difficulty {n} of 5">'
                + "".join(f'<i class="{"on" if i < n else ""}"></i>' for i in range(5)) + "</span>")

    cards = "".join(f"""<article class="cg-card" id="c-{g['k']}">
   <header class="cg-hd"><h2>{e(g['name'])}</h2><p class="cg-gr">{e(g['grades'])}</p></header>
   <p class="cg-what">{e(g['what'])}</p>
   <p class="cg-diff"><b>Difficulty</b>{meter(g['diff'])}<span>{e(g['dl'])}</span></p>
   <dl class="cg-dl">{"".join(f"<div><dt>{e(a)}</dt><dd>{e(b)}</dd></div>" for a, b in g['rows'])}</dl>
   <p class="cg-ft"><a href="{root}{CONTESTS[g['k']]['slug']}/">{e(CONTESTS[g['k']]['short'])} prep &rarr;</a><small>{e(g['ours'])}</small></p>
  </article>""" for g in GUIDE)
    amc = [("AMC 8", "Grade 8 and below. Practice for what comes next."),
           ("AMC 10 or AMC 12", "Every November."),
           ("AIME", "Top 2.5% on the AMC 10 or top 5% on the AMC 12. 15 questions in 3 hours, answers 0 to 999."),
           ("USAJMO or USAMO", "Picked by AMC and AIME scores together. Six proof problems over two days."),
           ("Summer program and US team", "Top scorers are invited to a summer program, where selection tests pick the US team for the International Math Olympiad.")]
    mc = [("School", "Up to 14 students per school."), ("Chapter", "February."), ("State", "March."),
          ("National", "Top 4 per state. May 9 to 10, 2027, in Washington, DC.")]
    ladder = lambda xs: "".join(f'<li><b>{e(a)}</b><span>{e(b)}</span></li>' for a, b in xs)
    body = head(f"A Parents' Guide to Math Contests: Kangaroo, Noetic, MOEMS, MATHCOUNTS, AMC | {NAME}",
                "What each math contest is for, who runs it, how hard it is, how to enter and where it leads, from Math Kangaroo and Noetic to MATHCOUNTS, the AMC and the AIME.",
                "contests/", root)
    body += nav(root, "contests")
    body += f"""<section class="page-head">
 <div class="wrap">
  <h1>A parents' guide to math contests</h1>
  <p class="lead">What each contest is for, how hard it is, how to enter and where it leads.</p>
  <p class="cg-jump">{jump}</p>
 </div>
</section>
<section class="sec sec-tight"><div class="wrap cg">
 <div class="cg-why">
  <h2>Why kids take contests</h2>
  <ul class="ticks">
   <li>The problems are more interesting than homework, at the right stretch.</li>
   <li>A date on the calendar makes practice stick.</li>
   <li>Certificates, ribbons and team days build confidence.</li>
  </ul>
 </div>
 <div class="cg-grades">
  <h2>Which contests fit which grade</h2>
  <ul class="cg-gl">{grade_rows}</ul>
 </div>
 <div class="cg-cards">{cards}</div>
 <div class="cg-paths">
  <div class="cg-path"><h2>The AMC ladder</h2><ol class="cg-ladder">{ladder(amc)}</ol></div>
  <div class="cg-path"><h2>The MATHCOUNTS ladder</h2><ol class="cg-ladder">{ladder(mc)}</ol></div>
 </div>
 <div class="cg-college">
  <h2>Do contests help with college?</h2>
  <p>No contest guarantees admission, and most strong applicants never take the AIME. A result is an achievement a student can list on applications, and reaching the AIME or beyond is rare by design.</p>
  <p>The lasting gain is the skill: reading a problem carefully, trying a plan and checking it. That carries into school math and later STEM classes.</p>
 </div>
 <p class="cg-teach">Teach a class or coach a team? See <a href="{root}teachers/">For teachers and clubs</a>.</p>
 <p class="glance-note">Facts are from each contest's own site, checked November 12, 2026. Rules and dates can change, so check there before you register. Difficulty is our own view. We are not affiliated with any contest.</p>
</div></section>
"""
    body += test_cta(root, compact=True) + foot(root)
    write("contests/index.html", body)


def page_teachers():
    """/teachers/: for teachers and club coaches (Nov 12, Jian approved the growth idea, then "Sell it" for the
    Club & Coach License). Diagnostics download straight away, a one-period plan, then the $99 license. Its Buy button
    shows only once shop.json has "club" (the Payhip link), which waits on Jian's yes to list it."""
    root = "../"
    club = SHOP.get("club") if SHOP.get("live") else None  # Nov 12: listed on Payhip after Jian's "List it on Payhip"
    rows = "".join(
        f'<li><span><b>{e(t["label"])} diagnostic</b><small>{grades_label(t["grades"])}</small></span>'
        f'<a class="btn btn-primary" href="{diag_url(t)}" rel="noopener">Download PDF</a></li>'
        for t in TEST_SETS if t["diag"])
    steps = [("Print one per student.", "Keep the answer key, the last page, for yourself."),
             ("Time it like the contest.", "One class period is enough."),
             ("Grade with the key.", "Each answer names the key move that solves it."),
             ("Send misses home.", "A QR code beside every problem opens a short video lesson on that move."),
             ("Warm up on the top miss.", "Next meeting, start with the key move most students missed.")]
    plan = "".join(f'<li><b>{e(a)}</b> {e(b)}</li>' for a, b in steps)
    buy = (f'<a class="btn btn-primary btn-lg" href="{e(club)}" rel="noopener">Get the Club License, $99</a>' if club
           else f'<p class="tc-soon"><b>Coming soon.</b> Want it when it opens? <a href="mailto:{CONTACT}?subject=Club%20License">Email us</a>.</p>')
    body = head(f"For Teachers and Math Clubs: Classroom Contest Tests | {NAME}",
                "Printable contest math diagnostic tests for your class, with answer keys and a video lesson for every problem, plus a Club License to copy 30 practice tests for your team.",
                "teachers/", root)
    body += nav(root, "teachers")
    body += f"""<section class="page-head">
 <div class="wrap">
  <h1>For teachers and clubs</h1>
  <p class="lead">Run contest practice in one class period. Everything prints, and every problem links to a short video lesson.</p>
 </div>
</section>
<section class="sec sec-tight"><div class="wrap tc">
 <div class="tc-box">
  <h2>Start with a diagnostic</h2>
  <p>Free to copy for your whole class. No sign-up. Answer key on the last page.</p>
  <ul class="tc-list">{rows}</ul>
 </div>
 <div class="tc-box">
  <h2>How to run it</h2>
  <ol class="tc-steps">{plan}</ol>
 </div>
 <div class="tc-box tc-club" id="club">
  <p class="eyebrow">Club &amp; Coach License &middot; $99</p>
  <h2>Running a club or team?</h2>
  <p>A whole season of practice, licensed to copy for your group.</p>
  <ul class="ticks">
   <li>30 practice tests for grades 4 to 6: Noetic-style Grade 5 Tests 1 to 20 and MOEMS-style Seasons 1 to 10</li>
   <li>Copy for every student in one club, team, class or program at one location, with no yearly renewal</li>
   <li>Coach kit: a 10-week season plan, team score trackers and every answer key in one booklet</li>
  </ul>
  {buy}
  <p class="small">Teaching one class? A <a href="{root}mock-tests/">10-test pack</a> covers one classroom.</p>
 </div>
 <p class="glance-note">Every problem is our own. Not affiliated with any contest. Questions: <a href="mailto:{CONTACT}">{CONTACT}</a></p>
</div></section>
"""
    body += foot(root)
    write("teachers/index.html", body)


def page_404():
    root = "/"
    body = head(f"Page not found | {NAME}", "This page does not exist.", "404.html", root, noindex=True)
    body += nav(root)
    body += f"""<section class="page-head"><div class="wrap"><h1>That page is missing.</h1>
<p class="lead">Even the best tool can't find it. Try the lessons instead.</p>
<p><a class="btn btn-primary btn-lg" href="{root}lessons/">See all lessons</a></p>
{search_form(root, "nf-q", "Or look for a key move")}</div></section>"""
    body += foot(root)
    write("404.html", body)


def page_qr(l):
    """Stable short link for QR codes in tests and videos: t/<tool number>/ sends the visitor to the video
    once YouTube has it public, and to the lesson page on this site until then (the hourly rebuild flips it)."""
    n = int(l["tool_num"])
    lesson_url = f"{SITE}/lessons/{l['slug']}/"
    target = f"https://youtu.be/{l['video_id']}" if l.get("video_id") and l["live"] else lesson_url
    t = e(target)
    write(f"t/{n}/index.html", f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tool #{n}: {e(l['tool'])} | {NAME}</title>
<meta name="robots" content="noindex">
<link rel="canonical" href="{e(lesson_url)}">
<meta http-equiv="refresh" content="0; url={t}">
<script>location.replace({json.dumps(target)});</script>
</head>
<body style="font-family:system-ui,sans-serif;padding:24px">
<p>Opening Tool #{n}, {e(l['tool'])}&hellip;</p>
<p><a href="{t}">Tap here if it does not open.</a></p>
</body>
</html>
""")


def load_upcoming():
    p = os.path.join(ROOT, "data", "upcoming_tools.json")
    return json.load(open(p))["tools"] if os.path.exists(p) else []


def page_qr_upcoming(t):
    """t/N for a tool printed on a test before its lesson exists (Nov 11: Kangaroo-style Grades 5-6 diagnostic
    QRs t/41, t/42). Opens the YouTube lesson once video_id is set and YouTube plays it; until then a short "lesson coming soon" page."""
    n = int(t["tool_num"])
    live_path = os.path.join(ROOT, "data/live.json")
    playable = set(json.load(open(live_path)).get("upcoming", [])) if os.path.exists(live_path) else set()
    if t.get("video_id") in playable:
        target = f"https://youtu.be/{t['video_id']}"
        write(f"t/{n}/index.html", f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tool #{n}: {e(t['tool'])} | {NAME}</title>
<meta name="robots" content="noindex">
<meta http-equiv="refresh" content="0; url={e(target)}">
<script>location.replace({json.dumps(target)});</script>
</head>
<body style="font-family:system-ui,sans-serif;padding:24px">
<p>Opening Tool #{n}, {e(t['tool'])}&hellip;</p>
<p><a href="{e(target)}">Tap here if it does not open.</a></p>
</body>
</html>
""")
        return
    root = "/"
    body = head(f"Tool #{n}: {e(t['tool'])} | {NAME}", f"Key move #{n}, {t['tool']}. Video lesson coming soon.",
                f"t/{n}/", root, noindex=True)
    body += nav(root)
    body += f"""<section class="page-head"><div class="wrap">
  <p class="eyebrow">{e(t['style'])} &middot; {e(t['grades'])} &middot; Tool #{n}</p>
  <h1>{e(t['tool'])}</h1>
  <p class="lead">The video lesson for this key move is coming soon. Subscribe and it will show up in your feed.</p>
  <p class="soon-ctas"><a class="btn btn-primary btn-lg" href="https://www.youtube.com/@keymovemath?sub_confirmation=1" rel="noopener">Subscribe on YouTube</a>
  <a class="btn btn-ghost-d btn-lg" href="{root}lessons/">See the lessons out now</a></p>
</div></section>"""
    body += foot(root)
    write(f"t/{n}/index.html", body)


def extras(lessons, urls):
    today = date.today().isoformat()
    sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in urls:
        sm.append(f"<url><loc>{SITE}/{u}</loc><lastmod>{today}</lastmod></url>")
    sm.append("</urlset>")
    write("sitemap.xml", "\n".join(sm) + "\n")
    write("robots.txt", f"User-agent: *\nAllow: /\nSitemap: {SITE}/sitemap.xml\n")
    write("assets/img/favicon.svg", mark(64))
    write(".nojekyll", "")


def main():
    lessons = load()
    SHOP.update(load_shop())
    # A grade is live once it has lessons or a free/practice test (Nov 11: MOEMS 4-6, AMC 8 and MATHCOUNTS 6-8).
    GRADES[:] = [(g, any(str(l["grade"]) == g for l in lessons) or any(int(g) in t["grades"] and test_live(t) for t in TEST_SETS))
                 for g, _ in GRADES]
    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    shutil.copytree(os.path.join(ROOT, "assets"), os.path.join(OUT, "assets"))
    page_home(lessons)
    page_lessons(lessons)
    for l in lessons:
        page_lesson(l, lessons)
    urls = ["", "free/", "lessons/", "key-moves/", "study-plan/", "contests/", "teachers/", "math-corner/", "grade-5/", "mock-tests/", "about/"]
    page_group("grade-5", f"Grade 5 Competition Math Lessons | {NAME}", "Grade 5 math",
               "The key moves that come up most on Grade 5 contests, grouped by topic. Each one is a short video lesson.",
               grade_lessons(lessons, 5),
               "Free Grade 5 competition math lessons: one tool per video, from shaded area to round-trip speed.",
               badge="5", picker=contest_picker(lessons, 5, "../"), pl=playlist_links(5))
    for g, live in GRADES:
        if live and g != "5":
            gt = [t for t in TEST_SETS if int(g) in t["grades"] and test_live(t)]
            page_group(f"grade-{g}", f"Grade {g} Competition Math: Free Tests and Lessons | {NAME}", f"Grade {g} math",
                       f"The key moves that come up most on Grade {g} contests, grouped by topic. Pick a contest for its tests.",
                       grade_lessons(lessons, g),
                       f"Free Grade {g} competition math diagnostic tests, by contest.",
                       badge=g, picker=contest_picker(lessons, g, "../"), tests=False,
                       extra="".join(test_blocks("../", gt, g)), pl=playlist_links(g))
            urls.append(f"grade-{g}/")
    for g, _ in GRADES:
        for k in CONTESTS:
            if combo_live(lessons, g, k):
                page_combo(lessons, g, k)
                urls.append(f"grade-{g}/{k}/")
    for k, C in CONTESTS.items():
        sub = [l for l in lessons if k in l["contests"]]
        lead = (f"Key moves that come up on {C['name']}. {C['blurb']} Independent practice, not affiliated with {C['name']}."
                if sub else f"{C['blurb']} Independent practice, not affiliated with the {C['name']} organizers.")
        page_group(C["slug"], f"{C['name']} Prep: Free Video Lessons | {NAME}", f"{C['name']} prep", lead, sub,
                   f"Free {C['name']} prep videos: the problem-solving tools that come up most, taught one at a time.",
                   picker=grade_picker(lessons, k, "../"),
                   tests=k,  # each contest page links only its own tests
                   pl=playlist_links(contest=k),
                   extra="" if sub else "".join(test_blocks("../", [t for t in TEST_SETS if t["contest"] == k])))
        if sub:
            urls.append(C["slug"] + "/")
    write("amc-prep/index.html", '<!doctype html><meta charset="utf-8"><meta name="robots" content="noindex">'
          '<meta http-equiv="refresh" content="0; url=/#contests-h"><a href="/#contests-h">AMC 8, AMC 10 and AMC 12</a>')
    page_tests(lessons, SHOP)
    page_free()
    page_teachers()
    LIVE_SLUGS.update({l['slug']: l['tool'] for l in lessons if l['live']})
    page_math_corner()
    page_cheatsheet(lessons)
    page_plan()
    page_compare()
    page_about(lessons)
    page_404()
    for l in lessons:
        page_qr(l)
    taken = {int(l["tool_num"]) for l in lessons}
    for t in load_upcoming():
        if int(t["tool_num"]) not in taken:  # a real lesson always wins the short link
            page_qr_upcoming(t)
    urls += [f"lessons/{l['slug']}/" for l in lessons if l["live"]]
    urls += [f"math-corner/{n['slug']}/" for n in MC]
    extras(lessons, urls)
    missing = [l["slug"] for l in lessons for x in (".webp", "-lg.webp", ".jpg")
               if not os.path.exists(os.path.join(ROOT, "assets/covers", l["slug"] + x))]
    if missing:  # a missing cover shows as a broken image on the site (Nov 11: 11 were missing)
        print("WARNING missing covers:", ", ".join(sorted(set(missing))))
    print(f"built {OUT}: {sum(l['live'] for l in lessons)} of {len(lessons)} lessons live")


if __name__ == "__main__":
    main()
