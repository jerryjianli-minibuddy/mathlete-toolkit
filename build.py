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
FORM = "https://forms.gle/83Bkot9sWTyZDhpj8"
# Same form, embeddable, shown right on /free (Nov 11, Jian: "where is the form?" ... "do forms then")
FORM_EMBED = "https://docs.google.com/forms/d/e/1FAIpQLSeY2xBicN38Pyy0swQS7LFQ6yd4mv8P0Zr3ur6HJFg9CxbO7Q/viewform?embedded=true"
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
        json.dump({"live": ids, "shorts": sids}, open(live_path, "w"), indent=1)
        print(f"live: {len(ids)} of {len(lessons)}, shorts: {len(sids)}")
    for l in lessons:
        l["live"] = l["video_id"] in live
        l["short_live"] = l["live"] and l.get("short_id") in shorts
        l["contests"] = [c for c in l["contests"] if c in CONTESTS]
    return lessons


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
            elif r.status == 200 and "19.99" in page:
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
    contests += f'<a class="dd-i dd-more" href="{root}contests/">Compare all contests</a>'
    tests = ""
    for t in TEST_SETS:
        who = grade_title(f'{t["grades"][0]}-{t["grades"][-1]}') if len(t["grades"]) > 1 else f'Grade {t["grades"][0]}'
        tests += f'<p class="dd-h">{t["label"]}, {who.replace(" to ", " and ")}</p>'
        tests += (f'<a class="dd-i" href="{free_href(root, t["contest"], t["grades"][0])}">Free diagnostic test<small class="dd-free">free</small></a>'
                  if t["diag"] else '<span class="dd-i dd-off">Free diagnostic test<small>soon</small></span>')
        tests += (f'<a class="dd-i" href="{root}mock-tests/">Practice tests</a>' if t["practice"]
                  else '<span class="dd-i dd-off">Practice tests<small>soon</small></span>')
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
   <a class="soc soc-ig" href="{IG}" rel="noopener" aria-label="Key Move Math on Instagram">{IG_ICON}</a>
   <a class="soc soc-tt" href="{TT}" rel="noopener" aria-label="Key Move Math on TikTok">{TT_ICON}</a>
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
    bar = (f'<div class="mcta" id="mcta"><p><b>Free diagnostic test</b><small>Answer key, and a lesson for every miss</small></p>'
           f'<a class="btn btn-primary" href="{root}free/">Get it free</a></div>\n') if cta else ""
    contest_links = "".join(
        f'<li><a href="{root}{c["slug"]}/">{e(c["name"])}{" (soon)" if c.get("soon") else ""}</a></li>' for c in CONTESTS.values())
    return f"""</main>
<footer class="foot">
 <div class="wrap foot-grid">
  <div>
   <a class="brand brand-foot" href="{root}">{mark(30)}<span><b>KEY MOVE</b> <i>MATH</i></span></a>
   <p>Competition math, one key at a time. Free video lessons and a free diagnostic test.</p>
   <p class="foot-mail">Stuck on a problem? <a href="mailto:{CONTACT}">{CONTACT}</a></p>
   <a class="btn btn-yt" href="{YT_SUB}" rel="noopener">{YT_ICON}<span>Subscribe on YouTube</span></a>
  </div>
  <div>
   <h3>Learn</h3>
   <ul><li><a href="{root}lessons/">All lessons</a></li><li><a href="{root}grade-5/">Grade 5</a></li>
   <li><a href="{root}key-moves/">Key moves cheat sheet</a></li><li><a href="{root}study-plan/">4-week contest plan</a></li>
   <li><a href="{root}mock-tests/">Mock tests</a></li><li><a href="{root}free/">Free diagnostic test</a></li></ul>
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


def grade_list(lessons, root):
    """One row per grade: a coloured badge, the grade, a few of its skills and a link to all of them."""
    groups = topic_groups(lessons)
    rows = []
    for i, (g, live) in enumerate(GRADES):
        badge = f'<span class="gl-badge gc-{g}">{e(g)}</span>'
        if live:
            picks = [next((l for l in items if l["live"]), items[0]) for _, _, items in groups][:6]
            inc = '<span class="gl-sep">|</span>'.join(f'<a href="{root}lessons/{l["slug"]}/">{e(l["tool"])}</a>' for l in picks)
            rows.append(f'<li class="gl-row">{badge}<div class="gl-body"><h3><a href="{root}grade-{g}/">{grade_title(g)}</a></h3>'
                        f'<p class="gl-inc"><span class="gl-lab">Includes:</span> {inc}</p>'
                        f'<a class="gl-all" href="{root}grade-{g}/">See all {len(lessons)} key moves &rarr;</a></div></li>')
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
    return f"""<section class="cta-band">
 <div class="wrap cta-in">
  <div>
   <p class="eyebrow">Free</p>
   <h2>Free diagnostic test</h2>
   <p>Pick your contest and grade. Answer key included, and every miss opens its lesson.</p>
   <a class="btn btn-primary btn-lg" href="{free_href(root, contest, grade)}">Get the free test</a>
  </div>
 </div>
</section>"""


# ---------- sample pages and parent FAQ (Nov 11) ----------

# Real pages from the PDFs (mock-tests/preview/), small for phones and full size on tap.
SAMPLES = {
    "diagnostic": ("diagnostic-page1-sm.webp", "diagnostic-page1.webp", "Free Noetic-style test, page 1",
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
                 "Yes. Fill in a short form, then download the PDF right away. No payment."),
        "who": ("Which grades?",
                "Pick your grade on the free test page. New grades are added as they are ready."),
        "misses": ("What do we do with the misses?",
                   "Scan the QR beside the problem to open its lesson. Try the problem again the next day."),
        "original": ("Are the problems copied from real contests?",
                     "No. Every problem is our own. We match real contest difficulty but never copy."),
        "share": ("Can I share the free test?",
                  "Yes. It is free for home and classroom use."),
        "lessons": ("Do the video lessons cost anything?",
                    "No. Every lesson is free on YouTube, one named tool in about four minutes."),
        "pack": ("What is in the practice pack?",
                 "Ten Grade 5 tests in the free test's format, each with a worked answer key. One 60-page PDF for one family or classroom."),
        "when": (("How do I buy the practice tests?",
                  "$3.99 for one Grade 5 test or $19.99 for all 10. The PDF downloads right after checkout.")
                 if live else
                 ("When can I buy the practice tests?",
                  "Checkout opens soon: $3.99 for one Grade 5 test or $19.99 for all 10. Start with the free test meanwhile.")),
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
    faq_html, faq_ld = faq(("free", "who", "misses", "original", "when", "independent"))
    body = head(f"{NAME}: Free Diagnostic Test and Contest Math Video Lessons",
                "Free contest math diagnostic test. Pick your grade: answer key included, and a QR code beside every problem opens a short video lesson on its key move.",
                "", root, extra=f'<script type="application/ld+json">{json.dumps(ld)}</script><script type="application/ld+json">{json.dumps(site_ld)}</script>' + faq_ld)
    body += nav(root)
    body += f"""<section class="hero">
 <div class="wrap hero-in">
  <div class="hero-copy">
   <p class="eyebrow eyebrow-y">Free &middot; Contest math</p>
   <h1>Free diagnostic test. <span>A video for every miss.</span></h1>
   <p class="lead">Find the key moves your child still needs.</p>
   <div class="hero-cta" data-cta-watch>
    <a class="btn btn-primary btn-lg btn-wide" href="{root}free/">Get the free test</a>
    <a class="hero-alt" href="lessons/{feat['slug']}/">or watch a lesson first &rarr;</a>
   </div>
   <ul class="hero-trust"><li>Free PDF</li><li>Answer key</li><li>No payment</li></ul>
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
  <li class="t-yt">Lessons free on YouTube</li>
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
   <li><span class="n n1">1</span><h3>Take the free test</h3><p>Pick your contest and grade. Check with the answer key.</p><a class="go" href="free/">Get the free test &rarr;</a></li>
   <li><span class="n n2">2</span><h3>Watch the key move</h3><p>Scan the QR beside each miss.</p><a class="go" href="lessons/">See all {len(lessons)} lessons &rarr;</a></li>
   <li><span class="n n3">3</span><h3>Practice with the pack</h3><p>Ten Noetic-style Grade 5 tests with worked answer keys.</p><a class="go" href="mock-tests/">See the practice tests &rarr;</a></li>
  </ol>
  <div class="freebies">
   <a class="freebie" href="key-moves/"><b>Key moves cheat sheet</b><span>Every rule and trap on one printable page</span></a>
   <a class="freebie" href="study-plan/"><b>4-week contest plan</b><span>15 to 20 minutes a day, with a miss log</span></a>
  </div>
 </div>
</section>

<section class="sec sec-alt" aria-labelledby="inside-h">
 <div class="wrap">
  <h2 id="inside-h">See inside</h2>
  {samples(root)}
  <p class="sec-cta" data-cta-watch><a class="btn btn-primary btn-lg btn-wide" href="{root}free/">Get the free test</a></p>
 </div>
</section>


<section class="sec sec-alt">
 <div class="wrap">
  <div class="sec-head"><h2 id="contests-h">Pick your contest</h2><a class="go" href="contests/">Compare all contests &rarr;</a></div>
  <div class="contests contests-short">{''.join(cards)}</div>
 </div>
</section>
<section class="sec" aria-label="Questions parents ask">
 <div class="wrap">{faq_html}</div>
</section>
{test_cta(root, compact=True)}
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
  <aside class="test-box" data-cta-watch>
   <div>
    <p class="eyebrow">Free diagnostic test</p>
    <h2>Which keys does your child still need?</h2>
    <p>Find out free. Every miss links to its lesson.</p>
   </div>
   <a class="btn btn-primary btn-lg" href="{root}free/">Get the free test</a>
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
    dict(key="noetic-5", contest="noetic", grades=[5], label="Noetic-style", diag=True, practice=True),
    dict(key="kangaroo-5-6", contest="kangaroo", grades=[5, 6], label="Kangaroo-style", diag=False, practice=False),
]
# Drive id of each diagnostic PDF (must be shared as anyone with the link).
DIAG_FILES = {"noetic-5": "1PReaxlTwr3zcN-xdEyVcYWJtY8c8Tc2p", "kangaroo-5-6": "1ggmbBeozrqJopzf2vQNeLZS5msb5WJ4W"}


def test_live(t):
    return t["diag"] or t["practice"]


def free_href(root, k=None, g=None):
    q = "&".join(x for x in (f"contest={k}" if k else "", f"grade={g}" if g else "") if x)
    return f"{root}free/" + (f"?{q}" if q else "")


def combo_lessons(lessons, g, k):
    return [l for l in lessons if str(l["grade"]) == str(g) and k in l["contests"]]


def combo_tests(g, k):
    return [t for t in TEST_SETS if t["contest"] == k and int(g) in t["grades"]]


def combo_live(lessons, g, k):
    """A grade and contest pair gets its own page once it has a lesson or a live test."""
    return bool(combo_lessons(lessons, g, k)) or any(test_live(t) for t in combo_tests(g, k))


def contest_picker(lessons, g, root, current=None):
    on = lambda x: ' pk-on" aria-current="page' if x == current else ""
    items = [f'<a class="pk{on(None)}" href="{root}grade-{g}/">All contests</a>']
    for k, C in CONTESTS.items():
        if combo_live(lessons, g, k):
            items.append(f'<a class="pk{on(k)}" href="{root}grade-{g}/{k}/">{e(C["name"])}</a>')
        else:
            items.append(f'<span class="pk pk-off">{e(C["name"])}<small>soon</small></span>')
    return (f'<div class="picker"><p class="pk-h">Pick a contest</p>'
            f'<div class="pk-row">{"".join(items)}</div></div>')


def grade_picker(lessons, k, root, current=None):
    items = []
    for g, _ in GRADES:
        badge = f'<span class="gl-badge gc-{g}">{g}</span>'
        if combo_live(lessons, g, k):
            cur = ' pk-on" aria-current="page' if str(g) == str(current) else ""
            items.append(f'<a class="pk pk-g{cur}" href="{root}grade-{g}/{k}/">{badge}Grade {g}</a>')
        else:
            items.append(f'<span class="pk pk-g pk-off">{badge}Grade {g}<small>soon</small></span>')
    return (f'<div class="picker"><p class="pk-h">Pick a grade</p>'
            f'<div class="pk-row pk-grades">{"".join(items)}</div></div>')


def page_combo(lessons, g, k):
    """grade-N/<contest>/: the lessons and tests for one grade and one contest, with both pickers on top."""
    root = "../../"
    C = CONTESTS[k]
    sub = combo_lessons(lessons, g, k)
    tests = combo_tests(g, k)
    slug = f"grade-{g}/{k}"
    blocks = []
    for t in tests:
        who = grade_title(f'{t["grades"][0]}-{t["grades"][-1]}').replace(" to ", " and ") if len(t["grades"]) > 1 else f"Grade {g}"
        if test_live(t):
            btns = (f'<a class="btn btn-primary" href="{free_href(root, k, g)}">Free diagnostic test</a>' if t["diag"] else "")
            btns += (f'<a class="btn btn-ghost-d" href="{root}mock-tests/">Practice tests</a>' if t["practice"]
                     else '<span class="btn btn-ghost-d btn-off">Practice tests soon</span>')
            blocks.append(f'<div class="combo-tests"><div><p class="eyebrow">Tests</p><h2>{t["label"]} tests, {who}</h2>'
                          f'<p>Printable, with a worked answer key and a lesson QR beside every problem.</p></div>'
                          f'<div class="combo-btns">{btns}</div></div>')
        else:
            blocks.append(f'<div class="combo-tests combo-soon"><div><p class="eyebrow">Tests</p>'
                          f'<h2>{t["label"]} tests, {who}</h2><p>Coming soon.</p></div></div>')
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
 <div class="wrap pickers">{contest_picker(lessons, g, root, k)}{grade_picker(lessons, k, root, g)}</div>
</section>
<section class="sec sec-tight"><div class="wrap">{"".join(blocks)}{glance(k)}{inner}</div></section>
"""
    body += test_cta(root, compact=True, contest=k, grade=g) + foot(root)
    write(f"{slug}/index.html", body)


# Contest format at a glance (Nov 11 overnight, toward "insanely useful for parents"). Source: the Contests tab of the
# Past Test Database, which Jian's tests were logged against. Dates are left out on purpose: they move every year.
CONTEST_FACTS = {
    "kangaroo": dict(who="Grades 1 to 12, one test for each pair of grades (1-2, 3-4, 5-6 and so on)",
                     rows=[("Questions", "24 for grades 1 to 4, 30 for grades 5 to 12. Multiple choice, 5 options."),
                           ("Time", "75 minutes"),
                           ("Scoring", "3, 4 and 5-point sections. The later problems are harder and worth more.")],
                     q=30, mins=75, pace_label="Pace, grades 5 to 12"),
    "noetic": dict(who="Grades 2 to 8, one test for each grade",
                   rows=[("Questions", "20 short-answer problems"),
                         ("Time", "45 minutes, no calculator"),
                         ("When", "Fall and Spring"),
                         ("Difficulty", "Problems 1 to 6 easy, 7 to 14 medium, 15 to 20 hard")],
                   q=20, mins=45),
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
                           ("Time", "Each problem has its own time limit, a few minutes each")]),
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


def page_group(slug, title, h1, lead, lessons, desc, soon=False, active=None, badge=None, picker="", tests=True):
    root = "../"
    n_live = sum(l["live"] for l in lessons)
    top = (f'<div class="sk-top"><p class="sk-count"><b>{len(lessons)}</b> key moves in {len(topic_groups(lessons))} topics'
           f'{f", {n_live} with a video now" if 0 < n_live < len(lessons) else ""}.</p>'
           f'<div class="sk-links">'
           + (f'<a class="btn btn-primary" href="{free_href(root, tests if isinstance(tests, str) else None)}">Free diagnostic test</a>'
              if tests is True or any(t["diag"] and t["contest"] == tests for t in TEST_SETS) else "")
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
 {f'<div class="wrap pickers">{picker}</div>' if picker else ""}
</section>
<section class="sec sec-tight"><div class="wrap">{glance(tests) if isinstance(tests, str) else ""}{inner}</div></section>
"""
    body += test_cta(root, compact=True, contest=tests if isinstance(tests, str) else None) + foot(root)
    write(f"{slug}/index.html", body)


YES = '<span class="yes" role="img" aria-label="Yes"></span>'


def page_tests(lessons, shop):
    """Mock tests as a pricing page (Nov 11): free vs single vs pack, what every test holds, sample pages, FAQ.
    Buy buttons link to Payhip only when shop["live"]; until then they say Coming soon and the free test is the action."""
    root = "../"
    live = shop["live"]
    faq_html, _ = faq(("pack", "when", "misses", "original", "independent"))
    if live:
        pack_btn = f'<a class="btn btn-primary btn-lg" href="{e(shop["pack"])}">Buy all 10 for $19.99</a>'
        single_btn = '<a class="btn btn-ghost-d btn-lg" href="#singles">Choose a test</a>'
    else:
        pack_btn = '<span class="btn btn-disabled btn-lg" aria-disabled="true">Coming soon</span>'
        single_btn = '<span class="btn btn-disabled btn-lg" aria-disabled="true">Coming soon</span>'
    soon_note = "" if live else f'<p class="small">Checkout opens soon. <a href="{root}free/">Start with the free test</a>.</p>'
    singles = "\n".join(
        f'    <li><span><b>Noetic-style Grade 5 Practice Test {n}</b><small>20 problems, 45 minutes, answer key</small></span><em>$3.99</em>'
        + (f'<a class="btn btn-buy" href="{e(u)}">Buy</a>' if live else '<span class="soon-tag">Coming soon</span>') + '</li>'
        for n, u in enumerate(shop["tests"], 1))
    body = head(f"Noetic-style Grade 5 Practice Tests | {NAME}",
                "Noetic-style Grade 5 practice tests at $3.99 each or $19.99 for all 10, each with a worked answer key and a lesson QR beside every problem. Start with the free diagnostic test.",
                "mock-tests/", root)
    body += nav(root, "tests")
    body += f"""<section class="page-head">
 <div class="wrap">
  <p class="eyebrow">Noetic-style &middot; Grade 5</p>
  <h1>Noetic-style Grade 5 practice tests</h1>
  <p class="lead">Real contest length. Every miss links to its key move. Start free.</p>
 </div>
</section>
<section class="sec sec-tight">
 <div class="wrap">
  <div class="plans">
   <div class="plan plan-free">
    <p class="eyebrow">Start here</p>
    <h2>Noetic-style diagnostic</h2>
    <p class="price"><b>Free</b></p>
    <ul class="facts-row"><li>PDF</li><li>Answer key</li><li>Free to share</li></ul>
    <a class="btn btn-primary btn-lg" href="{root}free/" data-cta-watch>Get the free test</a>
   </div>
   <div class="plan">
    <p class="eyebrow eyebrow-n">One test</p>
    <h2>Noetic-style Grade 5 test</h2>
    <p class="price"><b>$3.99</b> each</p>
    <ul class="facts-row"><li>Noetic-style</li><li>Grade 5</li><li>PDF</li><li>45 min</li></ul>
    {single_btn}
   </div>
   <div class="plan plan-pack">
    <p class="ribbon">Best value</p>
    <p class="eyebrow">All 10 tests</p>
    <h2>Noetic-style Grade 5 Practice Pack</h2>
    <p class="price"><b>$19.99</b> <s>$39.90</s> <span class="save">Save $19.91</span></p>
    <ul class="facts-row"><li>Noetic-style</li><li>Grade 5</li><li>10 tests</li><li>60 pages</li></ul>
    {pack_btn}
   </div>
  </div>
  {soon_note}
  <p class="test-note">{TEST_NOTE}</p>
  <div class="next-tests"><b>Kangaroo-style tests, Grades 5 and 6</b><span>Coming soon</span></div>
 </div>
</section>
<section class="sec sec-alt">
 <div class="wrap">
  <h2>Compare</h2>
  <div class="cmp-wrap">
   <table class="cmp">
    <thead><tr><th scope="col"><span class="vh">Feature</span></th><th scope="col">Free test</th><th scope="col">One test</th><th scope="col" class="cmp-best">Pack</th></tr></thead>
    <tbody>
     <tr><th scope="row">Problems</th><td>20</td><td>20</td><td class="cmp-best">200</td></tr>
     <tr><th scope="row">Easy to hard, 45 min</th><td>{YES}</td><td>{YES}</td><td class="cmp-best">{YES}</td></tr>
     <tr><th scope="row">Worked answer key</th><td>{YES}</td><td>{YES}</td><td class="cmp-best">{YES}</td></tr>
     <tr><th scope="row">Lesson QR on every problem</th><td>{YES}</td><td>{YES}</td><td class="cmp-best">{YES}</td></tr>
     <tr><th scope="row">Contest style</th><td>Noetic</td><td>Noetic</td><td class="cmp-best">Noetic</td></tr>
     <tr><th scope="row">Grade</th><td>5</td><td>5</td><td class="cmp-best">5</td></tr>
     <tr><th scope="row">Price</th><td>Free</td><td>$3.99</td><td class="cmp-best">$19.99</td></tr>
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
  <p class="sec-cta"><a class="btn btn-primary btn-lg btn-wide" href="{root}free/">Start with the free test</a></p>
 </div>
</section>
"""
    body += foot(root)
    write("mock-tests/index.html", body)


# Free diagnostic tests by grade (Nov 11, Jian: one landing page for every grade). A grade listed here
# links to its sign-up; every other grade on /free shows Coming soon. Add a grade when its test ships.
# Download after the form (Nov 11, Jian: "is there a way for people to just download the test after they fill out
# the form? set a password keymove"). The form's thank-you screen gives the password; typing it on /free downloads
# the PDF. The Drive link is stored scrambled with the password so it is not readable in the page source.
FREE_PASSWORD = "keymove"


def _scramble(text, pw):
    data = text.encode()
    ks = b"".join(hashlib.sha256(f"{pw}:{i}".encode()).digest() for i in range(len(data) // 32 + 1))
    import base64
    return base64.b64encode(bytes(a ^ b for a, b in zip(data, ks))).decode()


def unlock_form():
    check = hashlib.sha256(("keymovemath:" + FREE_PASSWORD).encode()).hexdigest()
    files = json.dumps({t["key"]: _scramble(f"https://drive.google.com/uc?export=download&id={DIAG_FILES[t['key']]}",
                                            FREE_PASSWORD) for t in TEST_SETS if t["diag"]})
    return f"""<form class="qform unlock" data-unlock data-check="{check}" data-files='{e(files)}'>
   <label for="pw">The password is on the last screen of the form.</label>
   <div class="qrow"><input id="pw" name="pw" type="text" placeholder="Password" autocomplete="off" autocapitalize="none" autocorrect="off" spellcheck="false" enterkeyhint="go">
   <button class="btn btn-primary" type="submit">Download</button></div>
   <p class="unlock-msg" aria-live="polite"></p>
  </form>"""


def page_free():
    """keymovemath.com/free: one free-test page for every contest and grade. Pick a contest and a grade; a pick with
    a ready diagnostic downloads that test after the form, every other pick says Coming soon (assets/js/site.js).
    ?contest=noetic&grade=5 preselects, so grade and contest pages link straight to their own test."""
    root = "../"
    faq_html, _ = faq(("free", "misses", "share", "original"), title="Questions")
    ready = {}  # contest -> {grade: [test key, label, who]}
    for t in TEST_SETS:
        if t["diag"]:
            who = grade_title(f'{t["grades"][0]}-{t["grades"][-1]}').replace(" to ", " and ") if len(t["grades"]) > 1 else f'Grade {t["grades"][0]}'
            for g in t["grades"]:
                ready.setdefault(t["contest"], {})[str(g)] = [t["key"], f'{t["label"]} test, {who}']
    cbtn = "".join(f'<button type="button" class="pk" data-contest="{k}">{e(C["name"])}</button>' for k, C in CONTESTS.items())
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
                "Free contest math diagnostic test. Pick your contest and grade: answer key included, and a QR code beside every problem opens its video lesson.",
                "free/", root)
    body += nav(root, "free")
    body += f"""<section class="hero hero-free">
 <div class="wrap">
  <p class="eyebrow eyebrow-y">Free</p>
  <h1>Free diagnostic test</h1>
  <p class="lead">Pick your contest and grade. Answer key included, and every miss opens its video lesson.</p>
  <ol class="free-steps">
   <li><b>Pick your contest and grade.</b></li>
   <li><b>Fill in the short form.</b></li>
   <li><b>Type the password it shows you.</b></li>
  </ol>
  {picker}
  <div class="signup" id="signup">
   <p class="signup-h"><span>2</span>Fill in the short form</p>
   <iframe class="signup-form" src="{FORM_EMBED}" title="Free diagnostic test sign-up form" loading="lazy">Loading the form&hellip;</iframe>
   <p class="signup-alt">Form not showing? <a href="{e(FORM)}" rel="noopener">Open it in a new tab</a>.</p>
  </div>
  <p class="signup-h signup-h3" id="unlock-step"><span>3</span>Type the password to download</p>
  <p class="pw-reveal" hidden>&#128273; Your password: <b>{FREE_PASSWORD.upper()}</b></p>
  {unlock_form()}
  <p class="teacher-note"><b>Teachers:</b> it is free to copy for your class.</p>
  <p class="test-note test-note-d">Every problem is our own. Not affiliated with any contest.</p>
 </div>
</section>
<section class="sec">
 <div class="wrap">
  <ul class="ticks ticks-3">
   <li>Contest-style problems, easy to hard</li>
   <li>Answer key on the last page</li>
   <li>A QR beside every problem opens its lesson</li>
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
   <p><a class="btn btn-primary" href="{root}free/">See for yourself: get the free test</a></p>
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
    body += test_cta(root, compact=True) + foot(root)
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
         f'Take the <a href="{root}free/">free diagnostic</a> with a timer. Mark every miss, then watch the lesson for one miss a day.'),
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
 <ol class="plan">{wk}</ol>
 <div class="pl-two">
  <section class="pl-tips"><h2>Four habits that help</h2><ul>{tp}</ul></section>
  <section class="pl-log"><h2>Miss log</h2>
   <table><thead><tr><th>Date</th><th>Problem</th><th>Trap</th><th>Key move</th><th>Redo</th></tr></thead><tbody>{rows}</tbody></table>
  </section>
 </div>
</div></section>
"""
    body += test_cta(root, compact=True) + foot(root)
    write("study-plan/index.html", body)


COMPARE = [  # contest, grades, questions, time, answers (same source as CONTEST_FACTS)
    ("kangaroo", "1 to 12", "24 or 30", "75 min", "Multiple choice"),
    ("noetic", "2 to 8", "20", "45 min", "Short answer"),
    ("mathcounts", "6 to 8", "Sprint: 30", "Sprint: 40 min", "Short answer, 4 rounds"),
    ("amc8", "8 and below", "25", "40 min", "Multiple choice"),
    ("amc10", "10 and below", "25", "75 min", "Multiple choice"),
    ("amc12", "12 and below", "25", "75 min", "Multiple choice"),
    ("olympiad", "4 to 8 (MOEMS)", "5 per contest", "A few min each", "Short answer, 5 contests a year"),
]


def page_compare():
    """/contests/: every contest side by side, so a parent can see which ones fit their child's grade."""
    root = "../"
    rows = "".join(
        f'<tr><th scope="row"><a href="{root}{CONTESTS[k]["slug"]}/">{e(CONTESTS[k]["name"])}</a></th>'
        f'<td data-l="Grades">{g}</td><td data-l="Questions">{q}</td><td data-l="Time">{t}</td><td data-l="Answers">{a}</td></tr>'
        for k, g, q, t, a in COMPARE)
    body = head(f"Math Contests Compared: Grades, Questions and Time | {NAME}",
                "Math Kangaroo, Noetic, MATHCOUNTS, AMC 8, AMC 10, AMC 12 and MOEMS side by side: who can take each, how many questions, and how long.",
                "contests/", root)
    body += nav(root, "contests")
    body += f"""<section class="page-head">
 <div class="wrap">
  <h1>Contests compared</h1>
  <p class="lead">Who can take each one, and what test day looks like. Tap a contest for its lessons.</p>
 </div>
</section>
<section class="sec sec-tight"><div class="wrap">
 <table class="cmp"><thead><tr><th scope="col">Contest</th><th scope="col">Grades</th><th scope="col">Questions</th><th scope="col">Time</th><th scope="col">Answers</th></tr></thead>
 <tbody>{rows}</tbody></table>
 <p class="glance-note">Formats can change. Check each contest's own site for dates and rules. We are not affiliated with any of them.</p>
</div></section>
"""
    body += test_cta(root, compact=True) + foot(root)
    write("contests/index.html", body)


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
    QRs t/41, t/42). Opens the YouTube lesson once video_id is set; until then a short "lesson coming soon" page."""
    n = int(t["tool_num"])
    if t.get("video_id"):
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
    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    shutil.copytree(os.path.join(ROOT, "assets"), os.path.join(OUT, "assets"))
    page_home(lessons)
    page_lessons(lessons)
    for l in lessons:
        page_lesson(l, lessons)
    urls = ["", "free/", "lessons/", "key-moves/", "study-plan/", "contests/", "grade-5/", "mock-tests/", "about/"]
    page_group("grade-5", f"Grade 5 Competition Math Lessons | {NAME}", "Grade 5 math",
               "Every key move for grade 5 contests, grouped by topic. Each one is a short video lesson.", lessons,
               "Free Grade 5 competition math lessons: one tool per video, from shaded area to round-trip speed.",
               badge="5", picker=contest_picker(lessons, 5, "../"))
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
                   tests=k)  # each contest page links only its own tests
        if sub:
            urls.append(C["slug"] + "/")
    write("amc-prep/index.html", '<!doctype html><meta charset="utf-8"><meta name="robots" content="noindex">'
          '<meta http-equiv="refresh" content="0; url=/#contests-h"><a href="/#contests-h">AMC 8, AMC 10 and AMC 12</a>')
    page_tests(lessons, SHOP)
    page_free()
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
    extras(lessons, urls)
    missing = [l["slug"] for l in lessons for x in (".webp", "-lg.webp", ".jpg")
               if not os.path.exists(os.path.join(ROOT, "assets/covers", l["slug"] + x))]
    if missing:  # a missing cover shows as a broken image on the site (Nov 11: 11 were missing)
        print("WARNING missing covers:", ", ".join(sorted(set(missing))))
    print(f"built {OUT}: {sum(l['live'] for l in lessons)} of {len(lessons)} lessons live")


if __name__ == "__main__":
    main()
