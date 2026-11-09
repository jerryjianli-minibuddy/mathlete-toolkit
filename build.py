#!/usr/bin/env python3
"""Builds the Mathlete Toolkit website into _site/.

  python3 build.py            use data/live.json for which lessons are public
  python3 build.py --check    ask YouTube which lessons are public now, update data/live.json

A lesson shows its video only once YouTube says it is public, so lessons
scheduled for later appear by themselves on their release day (the GitHub
workflow rebuilds every hour). To add a lesson, add a row to data/lessons.json
and a cover to assets/covers/<slug>.webp, <slug>-lg.webp and <slug>.jpg.
"""
import html, json, os, shutil, sys, urllib.request, urllib.error
from datetime import date

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "_site")
SITE = "https://jerryjianli-minibuddy.github.io/mathlete-toolkit"
YT = "https://www.youtube.com/@MathleteToolkit"
YT_SUB = YT + "?sub_confirmation=1"
FORM = "https://forms.gle/83Bkot9sWTyZDhpj8"
NAME = "Mathlete Toolkit"
UPLOADED = "2026-11-09"

CONTESTS = {
    "kangaroo": dict(name="Math Kangaroo", slug="math-kangaroo-prep", short="Kangaroo",
                     blurb="Picture puzzles, logic and counting, with no calculator."),
    "noetic": dict(name="Noetic Math Contest", slug="noetic-math-contest-prep", short="Noetic",
                   blurb="Word problems that reward a clean method over long arithmetic."),
    "mathcounts": dict(name="MATHCOUNTS", slug="mathcounts-prep", short="MATHCOUNTS",
                       blurb="Fast, exact answers: counting, rates, number theory and geometry."),
    "amc": dict(name="AMC 8, 10 and 12", slug="amc-prep", short="AMC", soon=True,
                blurb="Multiple choice, harder every level. Lessons are on the way."),
    "olympiad": dict(name="Math Olympiad", slug="math-olympiad-prep", short="Olympiad", soon=True,
                     blurb="Short answer, deep thinking. Lessons are on the way."),
}
GRADES = [("1-2", False), ("3-4", False), ("5", True), ("6", False), ("7-8", False), ("9-10", False), ("11-12", False)]

e = html.escape


def mmss(s):
    return f"{s // 60}:{s % 60:02d}"


def iso_dur(s):
    return f"PT{s // 60}M{s % 60}S"


# ---------- data ----------

def load():
    lessons = json.load(open(os.path.join(ROOT, "data/lessons.json")))
    live_path = os.path.join(ROOT, "data/live.json")
    live = set(json.load(open(live_path))["live"]) if os.path.exists(live_path) else set()
    if "--check" in sys.argv:
        found = set()
        for l in lessons:
            url = ("https://www.youtube.com/oembed?format=json&url=https://www.youtube.com/watch?v="
                   + l["video_id"])
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "mathlete-site"}), timeout=20) as r:
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
        json.dump({"live": ids}, open(live_path, "w"), indent=1)
        print(f"live: {len(ids)} of {len(lessons)}")
    for l in lessons:
        l["live"] = l["video_id"] in live
        l["contests"] = [c for c in l["contests"] if c in CONTESTS]
    return lessons


# ---------- pieces ----------

def cube(size=34, cls="cube"):
    c, h = 0.866, 0.5
    def p(pts): return " ".join(f"{x:.3f},{y:.3f}" for x, y in pts)
    top = [(0, -1), (c, -h), (0, 0), (-c, -h)]
    left = [(-c, -h), (0, 0), (0, 1), (-c, h)]
    right = [(0, 0), (c, -h), (c, h), (0, 1)]
    # '=' bars lying on the top face
    u, v = (c, -h), (c, h)
    bars = []
    for off in (-0.13, 0.13):
        cx, cy = 0 + v[0] * off * 0.9, -0.5 + v[1] * off * 0.9
        L, W = 0.26, 0.06
        q = [(cx - u[0] * L - v[0] * W, cy - u[1] * L - v[1] * W), (cx + u[0] * L - v[0] * W, cy + u[1] * L - v[1] * W),
             (cx + u[0] * L + v[0] * W, cy + u[1] * L + v[1] * W), (cx - u[0] * L + v[0] * W, cy - u[1] * L + v[1] * W)]
        bars.append(f'<polygon points="{p(q)}" fill="#0E1A32"/>')
    return (f'<svg class="{cls}" width="{size}" height="{size}" viewBox="-1.08 -1.08 2.16 2.16" aria-hidden="true">'
            f'<g stroke="#0E1A32" stroke-width="0.07" stroke-linejoin="round">'
            f'<polygon points="{p(top)}" fill="#FFD23F"/><polygon points="{p(left)}" fill="#E0457B"/>'
            f'<polygon points="{p(right)}" fill="#2BA59A"/></g>{"".join(bars)}'
            f'<g transform="translate(-0.433 0.25) skewY(30)" stroke="#fff" stroke-width="0.12">'
            f'<path d="M-0.2 0H0.2M0 -0.2V0.2"/></g>'
            f'<g transform="translate(0.433 0.25) skewY(-30) rotate(45)" stroke="#fff" stroke-width="0.12">'
            f'<path d="M-0.2 0H0.2M0 -0.2V0.2"/></g></svg>')


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
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#0E1A32">
<link rel="icon" href="{root}assets/img/favicon.svg" type="image/svg+xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{root}assets/css/site.css">
{extra}
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
"""


def nav(root, active=""):
    def a(href, label, key):
        cur = ' aria-current="page"' if key == active else ""
        return f'<a href="{root}{href}"{cur}>{label}</a>'
    return f"""<header class="top">
 <div class="wrap top-in">
  <a class="brand" href="{root}" aria-label="{NAME} home">{cube(34)}<span><b>MATHLETE</b> <i>TOOLKIT</i></span></a>
  <button class="menu" aria-expanded="false" aria-controls="nav" aria-label="Menu"><span></span><span></span><span></span></button>
  <nav id="nav">
   {a('lessons/', 'Lessons', 'lessons')}
   {a('mock-tests/', 'Mock tests', 'tests')}
   {a('about/', 'About', 'about')}
   <a class="btn btn-yt" href="{YT_SUB}" rel="noopener">{YT_ICON}<span>Subscribe</span></a>
  </nav>
 </div>
</header>
<main id="main">
"""


def foot(root):
    yr = date.today().year
    contest_links = "".join(
        f'<li><a href="{root}{c["slug"]}/">{e(c["name"])}{" (soon)" if c.get("soon") else ""}</a></li>' for c in CONTESTS.values())
    return f"""</main>
<footer class="foot">
 <div class="wrap foot-grid">
  <div>
   <a class="brand brand-foot" href="{root}">{cube(30)}<span><b>MATHLETE</b> <i>TOOLKIT</i></span></a>
   <p>Competition math, one tool at a time. Free video lessons for grades 1 to 12.</p>
   <a class="btn btn-yt" href="{YT_SUB}" rel="noopener">{YT_ICON}<span>Subscribe on YouTube</span></a>
  </div>
  <div>
   <h3>Learn</h3>
   <ul><li><a href="{root}lessons/">All lessons</a></li><li><a href="{root}grade-5/">Grade 5</a></li>
   <li><a href="{root}mock-tests/">Mock tests</a></li><li><a href="{FORM}" rel="noopener">Free Grade 5 test</a></li></ul>
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
<script src="{root}assets/js/site.js" defer></script>
</body>
</html>
"""


def chips(l, root):
    out = []
    for c in l["contests"]:
        C = CONTESTS[c]
        out.append(f'<a class="chip chip-{c}" href="{root}{C["slug"]}/">{e(C["short"])}</a>')
    return "".join(out)


def card(l, root, h="h3"):
    href = f'{root}lessons/{l["slug"]}/'
    data = " ".join(l["contests"])
    if l["live"]:
        badge = f'<span class="dur">{mmss(l["seconds"])}</span>'
        cls = "card"
    else:
        badge = '<span class="soon">Coming soon</span>'
        cls = "card is-soon"
    return f"""<article class="{cls}" data-contests="{data}" data-family="{e(l['family'])}">
 <a class="thumb" href="{href}" tabindex="-1" aria-hidden="true"><img src="{root}assets/covers/{l['slug']}.webp" alt="" width="640" height="360" loading="lazy">{badge}</a>
 <div class="card-body">
  <p class="tool-num">Tool #{l['tool_num']} &middot; {e(l['family'])}</p>
  <{h}><a href="{href}">{e(l['tool'])}</a></{h}>
  <p class="hook">{e(l['hook'])}</p>
 </div>
</article>"""


def grid(lessons, root, h="h3"):
    return '<div class="grid">' + "\n".join(card(l, root, h) for l in lessons) + "</div>"


def test_cta(root, compact=False):
    return f"""<section class="cta-band">
 <div class="wrap cta-in">
  <div>
   <p class="eyebrow">Free download</p>
   <h2>Take the Grade 5 Diagnostic Test</h2>
   <p>20 contest problems, easy to hard, 45 minutes, answer key included. Next to every problem is a QR code that opens the video lesson for it, so every miss turns into a lesson.</p>
   <a class="btn btn-primary btn-lg" href="{FORM}" rel="noopener">Get the free test</a>
  </div>
  {'' if compact else f'<a class="paper" href="{root}mock-tests/"><img src="{root}assets/img/diagnostic-page1.webp" alt="First page of the Grade 5 Diagnostic Test" width="1105" height="1430" loading="lazy"></a>'}
 </div>
</section>"""


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
        cards.append(f'<a class="contest c-{k}{" is-soon" if C.get("soon") else ""}" href="{C["slug"]}/"><h3>{e(C["name"])}</h3><p>{e(C["blurb"])}</p><span>{meta}</span></a>')
    grades = "".join(
        f'<a class="grade on" href="grade-5/"><b>Grade {g}</b><span>{len(lessons)} tools</span></a>' if live_g
        else f'<span class="grade"><b>Grade {g}</b><span>Coming</span></span>' for g, live_g in GRADES)
    ld = {"@context": "https://schema.org", "@type": "Organization", "name": NAME, "url": SITE + "/",
          "logo": SITE + "/assets/img/logo-512.png", "sameAs": [YT]}
    body = head(f"{NAME}: Competition Math Lessons, One Tool at a Time",
                "Free competition math video lessons for grades 1 to 12. Each lesson names one problem-solving tool, shows the common trap, and works problems from easy to hard. Free Grade 5 diagnostic test.",
                "", root, extra=f'<script type="application/ld+json">{json.dumps(ld)}</script>')
    body += nav(root)
    body += f"""<section class="hero">
 <div class="wrap hero-in">
  <div class="hero-copy">
   <p class="eyebrow eyebrow-y">Free video lessons &middot; Grades 1 to 12</p>
   <h1>Competition math, <span>one tool at a time.</span></h1>
   <p class="lead">Hard contest problems get easy once you know the right tool. Every lesson names one tool, shows the trap most kids fall into, then works problems from easy to hardest, so the next one is yours.</p>
   <div class="hero-cta">
    <a class="btn btn-primary btn-lg" href="{FORM}" rel="noopener">Get the free Grade 5 test</a>
    <a class="btn btn-ghost btn-lg" href="lessons/">Watch the lessons</a>
   </div>
   <ul class="hero-stats"><li><b>{len(lessons)}</b> Grade 5 tools</li><li><b>{n_live}</b> live now</li>{"<li><b>2</b> new a day</li>" if n_live < len(lessons) else "<li><b>Free</b> to watch</li>"}</ul>
  </div>
  <div class="hero-media">
   {embed(feat, root, eager=True)}
   <p class="now">{'New' if feat['live'] else 'First up'}: <a href="lessons/{feat['slug']}/">Tool #{feat['tool_num']}, {e(feat['tool'])}</a></p>
  </div>
 </div>
</section>

<section class="how">
 <div class="wrap">
  <h2 class="center">How every lesson works</h2>
  <ol class="steps">
   <li><span class="n n1">1</span><h3>See the trap</h3><p>Every contest problem has an answer that looks right and isn't. We show it first, so it never catches you.</p></li>
   <li><span class="n n2">2</span><h3>Learn the tool</h3><p>One short, named move, like <em>Find the Cycle</em> or <em>Keep the Gap</em>. Easy to remember when the clock is running.</p></li>
   <li><span class="n n3">3</span><h3>Climb easy to hard</h3><p>The same tool on harder and harder problems, slower on the tough ones. Then pause and try one alone.</p></li>
  </ol>
 </div>
</section>

<section class="sec">
 <div class="wrap">
  <div class="sec-head"><h2>Grade 5 toolkit</h2><a class="more" href="grade-5/">See all {len(lessons)} &rarr;</a></div>
  {grid(first, root)}
 </div>
</section>

<section class="sec sec-alt">
 <div class="wrap">
  <div class="sec-head"><h2>Pick your contest</h2></div>
  <div class="contests">{''.join(cards)}</div>
  <h3 class="sub">Grades</h3>
  <div class="grades">{grades}</div>
 </div>
</section>
{test_cta(root)}
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


def page_lessons(lessons):
    root = "../"
    fams = sorted({l["family"] for l in lessons})
    contest_btns = "".join(
        f'<button class="f" data-contest="{k}" aria-pressed="false">{e(C["short"])}</button>'
        for k, C in CONTESTS.items() if not C.get("soon"))
    fam_opts = "".join(f'<option value="{e(f)}">{e(f)}</option>' for f in fams)
    n_live = sum(l["live"] for l in lessons)
    body = head(f"All Lessons | {NAME}",
                "Every Mathlete Toolkit lesson in one place. Filter by contest (Math Kangaroo, Noetic, MATHCOUNTS) or topic. Free competition math videos.",
                "lessons/", root)
    body += nav(root, "lessons")
    body += f"""<section class="page-head">
 <div class="wrap">
  <h1>All lessons</h1>
  <p class="lead">One tool per video. {f"{n_live} live now, 2 new lessons a day until all {len(lessons)} Grade 5 tools are out." if n_live < len(lessons) else f"All {len(lessons)} Grade 5 tools are live."}</p>
 </div>
</section>
<section class="sec sec-tight">
 <div class="wrap">
  <div class="filters" role="group" aria-label="Filter lessons">
   <div class="f-row"><span class="f-label">Grade</span><button class="f" aria-pressed="true" disabled>Grade 5</button><span class="f-note">More grades coming</span></div>
   <div class="f-row"><span class="f-label">Contest</span><button class="f" data-contest="" aria-pressed="true">All</button>{contest_btns}</div>
   <div class="f-row"><label class="f-label" for="fam">Topic</label><select id="fam"><option value="">All topics</option>{fam_opts}</select>
   <label class="f-check"><input type="checkbox" id="liveonly"> Live only</label></div>
  </div>
  <p class="count" aria-live="polite"></p>
  {grid(lessons, root, "h2")}
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
                         "uploadDate": UPLOADED, "duration": iso_dur(l["seconds"]),
                         "embedUrl": f"https://www.youtube.com/embed/{l['video_id']}",
                         "contentUrl": f"https://www.youtube.com/watch?v={l['video_id']}",
                         "educationalLevel": "Grade 5", "learningResourceType": "Video lesson"})
        ld = f'<script type="application/ld+json">{ld}</script>'
    body = head(f"{l['tool']}: {l['hook']} | Grade 5 | {NAME}", desc, f"lessons/{l['slug']}/", root,
                image=f"assets/covers/{l['slug']}.jpg", noindex=not l["live"], extra=ld)
    body += nav(root, "lessons")
    status = (f'<a class="btn btn-yt" href="https://www.youtube.com/watch?v={l["video_id"]}" rel="noopener">{YT_ICON}<span>Watch on YouTube</span></a>'
              if l["live"] else '<p class="soon-note">This lesson goes live soon. New lessons come out every day at 7 AM and 4 PM Pacific.</p>')
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
  <p class="crumbs"><a href="{root}lessons/">Lessons</a> / <a href="{root}grade-5/">Grade 5</a> / Tool #{l['tool_num']}</p>
  <div class="lesson-grid">
   <div class="lesson-main">
    {embed(l, root, eager=True)}
    <div class="lesson-actions">{status}</div>
   </div>
   <aside class="lesson-side">
    <p class="tool-num">Tool #{l['tool_num']} &middot; Grade 5 &middot; {e(l['family'])}{' &middot; ' + mmss(l['seconds']) if l['live'] else ''}</p>
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
  {pn}
 </div>
</article>
"""
    body += test_cta(root, compact=True) + foot(root)
    write(f"lessons/{l['slug']}/index.html", body)


def page_group(slug, title, h1, lead, lessons, desc, soon=False, active="lessons"):
    root = "../"
    body = head(title, desc, f"{slug}/", root)
    body += nav(root, active)
    inner = grid(lessons, root, "h2") if lessons else f"""<div class="empty">
  <h2>Lessons are on the way</h2>
  <p>We are building this set now. Many Grade 5 tools already carry over, so start there.</p>
  <a class="btn btn-primary" href="{root}grade-5/">See the Grade 5 tools</a>
 </div>"""
    body += f"""<section class="page-head">
 <div class="wrap">
  <h1>{h1}</h1>
  <p class="lead">{lead}</p>
 </div>
</section>
<section class="sec sec-tight"><div class="wrap">{inner}</div></section>
"""
    body += test_cta(root, compact=True) + foot(root)
    write(f"{slug}/index.html", body)


def page_tests(lessons):
    root = "../"
    body = head(f"Free Grade 5 Mock Test | {NAME}",
                "A free 20-problem Grade 5 competition math diagnostic test with answer key and a QR code to a video lesson beside every problem.",
                "mock-tests/", root)
    body += nav(root, "tests")
    body += f"""<section class="page-head">
 <div class="wrap">
  <h1>Mock tests</h1>
  <p class="lead">Practice at real contest length, then fix every miss with the matching video.</p>
 </div>
</section>
<section class="sec sec-tight">
 <div class="wrap tests">
  <div class="test-card test-free">
   <p class="eyebrow">Free</p>
   <h2>Grade 5 Diagnostic Test</h2>
   <ul class="ticks">
    <li>20 original contest-style problems, easy to hard</li>
    <li>45 minutes, no calculator</li>
    <li>Answer key on the last page</li>
    <li>A QR code beside every problem opens its video lesson</li>
   </ul>
   <a class="btn btn-primary btn-lg" href="{FORM}" rel="noopener">Get the free test</a>
   <p class="small">Fill in a short form (email, grade, contest) and the PDF link comes right up.</p>
  </div>
  <div class="test-card test-pack">
   <p class="eyebrow eyebrow-p">Coming soon</p>
   <h2>Grade 5 Practice Pack</h2>
   <p class="price"><b>$14.99</b> for 10 full tests</p>
   <ul class="ticks">
    <li>10 more tests in the same format</li>
    <li>200 new problems, every one checked by computer</li>
    <li>Answer keys, plus a lesson QR on every problem</li>
   </ul>
   <span class="btn btn-disabled btn-lg" aria-disabled="true">Coming soon</span>
  </div>
  <figure class="paper paper-lg"><img src="{root}assets/img/diagnostic-page1.webp" alt="First page of the Grade 5 Diagnostic Test" width="1105" height="1430" loading="lazy"><figcaption>Page 1 of the free Grade 5 Diagnostic Test</figcaption></figure>
 </div>
</section>
"""
    body += foot(root)
    write("mock-tests/index.html", body)


def page_about(lessons):
    root = "../"
    body = head(f"About | {NAME}",
                "Mathlete Toolkit teaches competition math as a set of named tools, with free video lessons and mock tests for grades 1 to 12.",
                "about/", root)
    body += nav(root, "about")
    body += f"""<section class="page-head">
 <div class="wrap">
  <h1>About {NAME}</h1>
  <p class="lead">Contest math is not about being a genius. It is about knowing the right tool and spotting the trap.</p>
 </div>
</section>
<section class="sec sec-tight">
 <div class="wrap prose">
  <p>Most contest problems look hard because the obvious way is slow or wrong. Underneath, a small set of moves shows up again and again: glue two things together, count the pickiest spot first, keep the gap, find the cycle. We give each move a short name and teach it on its own.</p>
  <h2>What one lesson looks like</h2>
  <ul class="ticks">
   <li>A real contest-style problem in the first five seconds</li>
   <li>Why it looks hard, and what most kids try first</li>
   <li>The tool, named on every slide, with the clue words that point to it</li>
   <li>Problems from easy to hardest, slower on the tough ones</li>
   <li>A last problem to pause and try alone</li>
  </ul>
  <h2>Who it is for</h2>
  <p>Students getting ready for Math Kangaroo, the Noetic Math Contest, MATHCOUNTS, AMC 8, 10 and 12, and math olympiads. The Grade 5 toolkit is out now. Other grades follow.</p>
  <h2>Our problems</h2>
  <p>Every problem in our videos and tests is written by us and checked by computer. We study past contests to learn which tools come up and how hard they get, but we never copy their problems.</p>
  <p class="note">{NAME} is an independent practice channel. It is not affiliated with or endorsed by Math Kangaroo, Noetic Learning, MATHCOUNTS, the MAA (AMC) or any math olympiad.</p>
  <p><a class="btn btn-yt" href="{YT_SUB}" rel="noopener">{YT_ICON}<span>Subscribe on YouTube</span></a></p>
 </div>
</section>
"""
    body += test_cta(root, compact=True) + foot(root)
    write("about/index.html", body)


def page_404():
    root = "/mathlete-toolkit/"
    body = head(f"Page not found | {NAME}", "This page does not exist.", "404.html", root, noindex=True)
    body += nav(root)
    body += f"""<section class="page-head"><div class="wrap"><h1>That page is missing.</h1>
<p class="lead">Even the best tool can't find it. Try the lessons instead.</p>
<p><a class="btn btn-primary btn-lg" href="{root}lessons/">See all lessons</a></p></div></section>"""
    body += foot(root)
    write("404.html", body)


def extras(lessons, urls):
    today = date.today().isoformat()
    sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in urls:
        sm.append(f"<url><loc>{SITE}/{u}</loc><lastmod>{today}</lastmod></url>")
    sm.append("</urlset>")
    write("sitemap.xml", "\n".join(sm) + "\n")
    write("robots.txt", f"User-agent: *\nAllow: /\nSitemap: {SITE}/sitemap.xml\n")
    write("assets/img/favicon.svg", cube(64))
    write(".nojekyll", "")


def main():
    lessons = load()
    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    shutil.copytree(os.path.join(ROOT, "assets"), os.path.join(OUT, "assets"))
    page_home(lessons)
    page_lessons(lessons)
    for l in lessons:
        page_lesson(l, lessons)
    urls = ["", "lessons/", "grade-5/", "mock-tests/", "about/"]
    page_group("grade-5", f"Grade 5 Competition Math Lessons | {NAME}", "Grade 5 toolkit",
               f"{len(lessons)} tools for grade 5 contests, in the order we teach them. Start at Tool #1.", lessons,
               "Free Grade 5 competition math lessons: one tool per video, from shaded area to round-trip speed.")
    for k, C in CONTESTS.items():
        sub = [l for l in lessons if k in l["contests"]]
        lead = (f"Grade 5 tools that come up on {C['name']}. {C['blurb']} Independent practice, not affiliated with {C['name']}."
                if sub else f"{C['blurb']} Independent practice, not affiliated with the {C['name']} organizers.")
        page_group(C["slug"], f"{C['name']} Prep: Free Video Lessons | {NAME}", f"{C['name']} prep", lead, sub,
                   f"Free {C['name']} prep videos: the problem-solving tools that come up most, taught one at a time.")
        if sub:
            urls.append(C["slug"] + "/")
    page_tests(lessons)
    page_about(lessons)
    page_404()
    urls += [f"lessons/{l['slug']}/" for l in lessons if l["live"]]
    extras(lessons, urls)
    print(f"built {OUT}: {sum(l['live'] for l in lessons)} of {len(lessons)} lessons live")


if __name__ == "__main__":
    main()
