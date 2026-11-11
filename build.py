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
FORM = "https://forms.gle/83Bkot9sWTyZDhpj8"
NAME = "Key Move Math"
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
            ok = r.status == 200 and "unable to receive payments" not in page and "19.99" in page
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
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#0E1A32">
<link rel="icon" href="{root}assets/img/favicon.svg" type="image/svg+xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{root}assets/css/site.css?v={ASSET_V}">
{extra}
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
"""


def nav(root, active=""):
    """Header plus the always-visible browse bar (Jian, Nov 10: navigation at the top so people can go straight
    to the material they want). On phones the bar scrolls sideways; there is no hidden menu."""
    def a(href, label, key, cls="cat"):
        cur = ' aria-current="page"' if key == active else ""
        return f'<a class="{cls}" href="{root}{href}"{cur}>{label}</a>'
    contests = "".join(
        a(f'{C["slug"]}/', e(C["short"]) + (' <small>soon</small>' if C.get("soon") else ""), C["slug"])
        for C in CONTESTS.values())
    return f"""<header class="top">
 <div class="wrap top-in">
  <a class="brand" href="{root}" aria-label="{NAME} home">{mark(34)}<span><b>KEY MOVE</b> <i>MATH</i></span></a>
  <a class="btn btn-yt btn-sub" href="{YT_SUB}" rel="noopener">{YT_ICON}<span>Subscribe</span></a>
 </div>
 <nav class="catbar" aria-label="Browse">
  <div class="wrap cat-in">
   {a('free/', 'Free test', 'free', 'cat cat-free')}
   {a('mock-tests/', 'Mock tests', 'tests')}
   <span class="cat-label">By grade</span>
   {a('grade-5/', 'Grade 5', 'grade-5')}
   <span class="cat cat-soon">Grades 1 to 12 <small>soon</small></span>
   <span class="cat-label">By contest</span>
   {contests}
   <span class="cat-label">More</span>
   {a('lessons/', 'All lessons', 'lessons')}
   {a('about/', 'About', 'about')}
  </div>
 </nav>
</header>
<main id="main">
"""


def foot(root, cta=True):
    """cta: the phone-only bar pinned to the bottom of the screen with the free test button (Nov 11).
    Left off on /free, where the page itself is the sign-up."""
    yr = date.today().year
    bar = (f'<div class="mcta" id="mcta"><p><b>Free Grade 5 test</b><small>20 problems, answer key, a lesson for every miss</small></p>'
           f'<a class="btn btn-primary" href="{root}free/">Get it free</a></div>\n') if cta else ""
    contest_links = "".join(
        f'<li><a href="{root}{c["slug"]}/">{e(c["name"])}{" (soon)" if c.get("soon") else ""}</a></li>' for c in CONTESTS.values())
    return f"""</main>
<footer class="foot">
 <div class="wrap foot-grid">
  <div>
   <a class="brand brand-foot" href="{root}">{mark(30)}<span><b>KEY MOVE</b> <i>MATH</i></span></a>
   <p>Competition math, one key at a time. Free video lessons and a free test, starting with Grade 5. More grades are on the way.</p>
   <a class="btn btn-yt" href="{YT_SUB}" rel="noopener">{YT_ICON}<span>Subscribe on YouTube</span></a>
  </div>
  <div>
   <h3>Learn</h3>
   <ul><li><a href="{root}lessons/">All lessons</a></li><li><a href="{root}grade-5/">Grade 5</a></li>
   <li><a href="{root}mock-tests/">Mock tests</a></li><li><a href="{root}free/">Free Grade 5 test</a></li></ul>
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


def test_cta(root, compact=False):
    return f"""<section class="cta-band">
 <div class="wrap cta-in">
  <div>
   <p class="eyebrow">Free download</p>
   <h2>Take the Grade 5 Diagnostic Test</h2>
   <p>20 contest problems, easy to hard, 45 minutes, answer key included. Next to every problem is a QR code that opens the video lesson for it, so every miss turns into a lesson.</p>
   <a class="btn btn-primary btn-lg" href="{root}free/">Get the free test</a>
  </div>
  {'' if compact else f'<a class="paper" href="{root}mock-tests/"><img src="{root}assets/img/diagnostic-page1.webp" alt="First page of the Grade 5 Diagnostic Test" width="1105" height="1430" loading="lazy"></a>'}
 </div>
</section>"""


# ---------- sample pages and parent FAQ (Nov 11) ----------

# Real pages from the PDFs (mock-tests/preview/), small for phones and full size on tap.
SAMPLES = {
    "diagnostic": ("diagnostic-page1-sm.webp", "diagnostic-page1.webp", "Free test, page 1",
                   "20 problems, easy to hard, each with an answer box and a QR code to its lesson."),
    "practice": ("sample-test-page1.webp", "sample-test-page1-lg.webp", "Practice test, page 1",
                 "Every test in the pack has the same format, so the free test is a fair preview."),
    "key": ("sample-answer-key.webp", "sample-answer-key-lg.webp", "Answer key",
            "Each answer shows the working and names the tool it uses (sample from Practice Test 3)."),
}


def samples(root, keys=("diagnostic", "practice", "key")):
    figs = []
    for k in keys:
        sm, lg, title, text = SAMPLES[k]
        figs.append(f'<figure class="sample"><a href="{root}assets/img/{lg}" aria-label="{e(title)}, full size">'
                    f'<img src="{root}assets/img/{sm}" srcset="{root}assets/img/{sm} 560w, {root}assets/img/{lg} 1105w" '
                    f'sizes="(min-width: 960px) 340px, 78vw" width="560" height="725" loading="lazy" alt="{e(title)} of a Key Move Math Grade 5 test"></a>'
                    f'<figcaption><b>{e(title)}</b> {e(text)}</figcaption></figure>')
    return f'<div class="samples">{"".join(figs)}</div>'


SHOP = {"live": False}  # set in main() from data/shop.json


def faqs():
    live = SHOP.get("live")
    return {
        "free": ("Is the test really free?",
                 "Yes. Fill in a short form (email, grade and contest) and the link to the PDF shows right away. No payment, no card."),
        "who": ("Who is it for?",
                "Grade 5 students getting ready for a math contest, or any Grade 5 student who likes a challenge. Lessons for more grades are on the way."),
        "time": ("How long does it take?",
                 "45 minutes for 20 problems, no calculator. Print it at home, or open it on a tablet and write the answers on paper."),
        "misses": ("What do we do with the problems my child misses?",
                   "Scan the QR code beside the problem. It opens the video lesson for the key move behind it. Watch it, then try the problem again the next day without looking."),
        "original": ("Are the problems copied from real contests?",
                     "No. Every problem is our own, and every answer is checked by computer. We studied real Grade 5 contest tests to match their difficulty and the mix of tools they use, but we never copy them."),
        "share": ("Can I share the free test?",
                  "Yes. It is free for home and classroom use, so pass it on to a friend or a class."),
        "lessons": ("Do the video lessons cost anything?",
                    "No. Every lesson is free to watch on YouTube, and each one teaches a single named tool in about four minutes."),
        "pack": ("What is in the practice pack?",
                 "Ten more full tests in the same format: 20 problems and 45 minutes each, a worked answer key after every test, and a lesson QR beside every problem. One 60-page PDF, for one family or one classroom."),
        "when": (("How do I buy the practice tests?",
                  "One test is $3.99 and all 10 are $19.99, half the price of ten singles. Pick them on the Mock tests page; the PDF downloads right after checkout.")
                 if live else
                 ("When can I buy the practice tests?",
                  "Checkout opens soon: $3.99 for one test or $19.99 for all 10, half the price of ten singles. Until then, start with the free test, which uses the same format.")),
        "independent": ("Is Key Move Math run by a contest organizer?",
                        "No. Key Move Math is an independent practice channel. It is not affiliated with or endorsed by any contest organizer."),
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
        cards.append(f'<a class="contest c-{k}{" is-soon" if C.get("soon") else ""}" href="{C["slug"]}/"><h3>{e(C["name"])}</h3><p>{e(C["blurb"])}</p><span>{meta}</span></a>')
    grades = "".join(
        f'<a class="grade on" href="grade-5/"><b>Grade {g}</b><span>{len(lessons)} tools</span></a>' if live_g
        else f'<span class="grade"><b>Grade {g}</b><span>Coming</span></span>' for g, live_g in GRADES)
    ld = {"@context": "https://schema.org", "@type": "Organization", "name": NAME, "url": SITE + "/",
          "logo": SITE + "/assets/img/logo-512.png", "sameAs": [YT]}
    faq_html, faq_ld = faq(("free", "who", "time", "misses", "original", "lessons", "pack", "when", "independent"))
    body = head(f"{NAME}: Free Grade 5 Contest Math Test and Video Lessons",
                "Free Grade 5 contest math test: 20 problems, 45 minutes, answer key included, and a QR code beside every problem that opens a short video lesson on the key move for it.",
                "", root, extra=f'<script type="application/ld+json">{json.dumps(ld)}</script>' + faq_ld)
    body += nav(root)
    body += f"""<section class="hero">
 <div class="wrap hero-in">
  <div class="hero-copy">
   <p class="eyebrow eyebrow-y">Grade 5 &middot; Contest math</p>
   <h1>A free Grade 5 contest test, <span>with a video for every miss.</span></h1>
   <p class="lead">20 problems, 45 minutes, answer key included. Beside each problem is a QR code: scan the ones your child misses and the short lesson for that key move opens.</p>
   <div class="hero-cta" data-cta-watch>
    <a class="btn btn-primary btn-lg btn-wide" href="{root}free/">Get the free test</a>
    <a class="hero-alt" href="lessons/{feat['slug']}/">or watch a {round(feat.get('seconds', 240) / 60)}-minute lesson first &rarr;</a>
   </div>
   <ul class="hero-trust"><li>Free PDF</li><li>Answer key</li><li>Print or tablet</li><li>No payment</li></ul>
  </div>
  <div class="hero-media">
   {embed(feat, root, eager=True)}
   <p class="now">{'New' if feat['live'] else 'First up'}: <a href="lessons/{feat['slug']}/">Tool #{feat['tool_num']}, {e(feat['tool'])}</a> &middot; {n_live} of {len(lessons)} Grade 5 lessons live</p>
  </div>
 </div>
</section>

<section class="how" aria-labelledby="how-h">
 <div class="wrap">
  <p class="eyebrow center">How it works</p>
  <h2 id="how-h" class="center">Three steps, one key at a time</h2>
  <ol class="steps">
   <li><span class="n n1">1</span><h3>Take the free test</h3><p>Twenty Grade 5 contest problems, easy to hard, in 45 minutes. Check with the answer key and circle the misses.</p><a class="go" href="free/">Get the free test &rarr;</a></li>
   <li><span class="n n2">2</span><h3>Watch the key move</h3><p>Scan the QR beside each miss. The lesson names one tool, shows the trap, then climbs from easy to hard in about four minutes.</p><a class="go" href="lessons/">See all {len(lessons)} lessons &rarr;</a></li>
   <li><span class="n n3">3</span><h3>Practice with the pack</h3><p>Ten more full tests in the same format, each with a worked answer key and a lesson QR on every problem.</p><a class="go" href="mock-tests/">See the practice tests &rarr;</a></li>
  </ol>
 </div>
</section>

<section class="sec sec-alt" aria-labelledby="inside-h">
 <div class="wrap">
  <h2 id="inside-h">See inside the test</h2>
  <p class="sec-lead">Real pages from the PDFs. Tap any page to see it full size.</p>
  {samples(root)}
  <p class="sec-cta" data-cta-watch><a class="btn btn-primary btn-lg btn-wide" href="{root}free/">Get the free test</a></p>
 </div>
</section>

<section class="sec">
 <div class="wrap">
  <div class="sec-head"><h2>Grade 5 key moves</h2><a class="more" href="grade-5/">See all {len(lessons)} &rarr;</a></div>
  <p class="sec-lead">Every lesson: see the trap, learn the tool, climb from easy to hard, then pause and try the last one alone.</p>
  {grid(first, root)}
  {search_form(root, "home-q", "Know the topic? Find its key move.")}
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
  <p class="lead">One tool per video. {f"{n_live} live now, 2 new lessons a day until all {len(lessons)} Grade 5 tools are out." if n_live < len(lessons) else f"All {len(lessons)} Grade 5 tools are live."}</p>
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
    status += f'<a class="btn btn-primary" href="{root}free/">Free practice test</a>'
    if nxt:
        next_up = (f'<p class="next-up">Got this one? Next key: <a href="../{nxt["slug"]}/">Tool #{nxt["tool_num"]}, '
                   f'{e(nxt["tool"])} &rarr;</a></p>')
    else:
        next_up = f'<p class="next-up">That was the last Grade 5 tool. <a href="{root}lessons/">Pick another lesson &rarr;</a></p>'
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
  {pn}
 </div>
</article>
"""
    body += test_cta(root, compact=True) + foot(root)
    write(f"lessons/{l['slug']}/index.html", body)


def page_group(slug, title, h1, lead, lessons, desc, soon=False, active=None):
    root = "../"
    body = head(title, desc, f"{slug}/", root)
    body += nav(root, active or slug)
    if len(lessons) > 6:
        inner = filter_box(lessons, contests=False) + grid(lessons, root, "h2", search=True, gid="lesson-grid")
    elif lessons:
        inner = grid(lessons, root, "h2")
    else:
        inner = f"""<div class="empty">
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


def page_tests(lessons, shop):
    root = "../"
    live = shop["live"]
    pack_btn = (f'<a class="btn btn-primary btn-lg" href="{e(shop["pack"])}">Buy all 10 for $19.99</a>' if live else
                f'<a class="btn btn-ghost-d btn-lg" href="{root}free/">Coming soon: get the free test</a>')
    singles = "\n".join(
        f'    <li><span><b>Grade 5 Practice Test {n}</b><small>20 problems, 45 minutes, answer key</small></span><em>$3.99</em>'
        + (f'<a class="btn btn-buy" href="{e(u)}">Buy</a>' if live else '<span class="soon-tag">Coming soon</span>') + '</li>'
        for n, u in enumerate(shop["tests"], 1))
    body = head(f"Grade 5 Math Contest Mock Tests | {NAME}",
                "Grade 5 competition math mock tests: a free 20-problem diagnostic test, 10 practice tests at $3.99 each or $19.99 for all 10, each with an answer key and a lesson QR beside every problem.",
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
   <a class="btn btn-primary btn-lg" href="{root}free/">Get the free test</a>
   <p class="small">Fill in a short form (email, grade, contest) and the PDF link comes right up.</p>
  </div>
  <div class="test-card test-pack">
   <p class="eyebrow eyebrow-p">{"Best deal" if live else "Coming soon"}</p>
   <h2>Grade 5 Practice Pack</h2>
   <p class="price"><b>$19.99</b> for all 10 tests</p>
   <ul class="ticks">
    <li>10 more tests in the same format</li>
    <li>200 new problems, every one checked by computer</li>
    <li>Answer keys, plus a lesson QR on every problem</li>
   </ul>
   {pack_btn}
  </div>
  <div class="test-singles">
   <h2>Single tests, $3.99 each</h2>
   <p class="small">Each one is a full 20-problem test with its answer key. Ten singles cost $39.90, so the pack is half price.</p>
   <ul class="singles">
{singles}
   </ul>
   <a class="btn btn-primary" href="{root}free/">Start with the free test</a>
  </div>
  <figure class="paper paper-lg"><img src="{root}assets/img/diagnostic-page1.webp" alt="First page of the Grade 5 Diagnostic Test" width="1105" height="1430" loading="lazy"><figcaption>Page 1 of the free Grade 5 Diagnostic Test</figcaption></figure>
 </div>
</section>
"""
    body += foot(root)
    write("mock-tests/index.html", body)


def page_free():
    """keymovemath.com/free: the address every video, test and description points to for the free test (Nov 10).
    Signups go to the Google Form. Nov 11: a full landing page (what you get, what happens next, sample pages, FAQ)."""
    root = "../"
    faq_html, _ = faq(("free", "who", "time", "misses", "share", "original"), title="Before you start")
    go = (f'<a class="btn btn-primary btn-lg btn-wide" href="{FORM}" rel="noopener">Get the free test</a>')
    body = head(f"Free Grade 5 Math Contest Test | {NAME}",
                "Get the free 20-problem Grade 5 competition math test: answer key included, and a QR code beside every problem opens the key move for it.",
                "free/", root)
    body += nav(root, "free")
    body += f"""<section class="hero hero-free">
 <div class="wrap hero-in">
  <div class="hero-copy">
   <p class="eyebrow eyebrow-y">Free &middot; Grade 5</p>
   <h1>Your free Grade 5 contest test</h1>
   <p class="lead">Twenty problems at real test length, with the answer key. Stuck on one? Scan its QR code and the key move for it opens.</p>
   <div class="hero-cta">{go}</div>
   <p class="form-note">A short form asks for your email, grade and contest. The PDF link shows as soon as you send it.</p>
  </div>
  <a class="paper hero-paper" href="{root}assets/img/diagnostic-page1.webp"><img src="{root}assets/img/diagnostic-page1-sm.webp" srcset="{root}assets/img/diagnostic-page1-sm.webp 560w, {root}assets/img/diagnostic-page1.webp 1105w" sizes="(min-width: 960px) 380px, 70vw" alt="Page 1 of the free Grade 5 Diagnostic Test" width="560" height="725"></a>
 </div>
</section>
<section class="sec">
 <div class="wrap free-grid">
  <div class="test-card test-free">
   <h2>What you get</h2>
   <ul class="ticks">
    <li>20 original contest-style problems, easy to hard</li>
    <li>45 minutes, no calculator</li>
    <li>Answer key on the last page</li>
    <li>A QR code beside every problem opens its video lesson</li>
    <li>Free for home and classroom use, so share it</li>
   </ul>
  </div>
  <div class="test-card">
   <h2>What happens next</h2>
   <ol class="next-steps">
    <li><b>Send the short form.</b> The link to the PDF shows right away.</li>
    <li><b>Take the test.</b> Print it or use a tablet. Set a 45-minute timer.</li>
    <li><b>Fix every miss.</b> Check with the answer key, then scan the QR beside each miss to watch its key move.</li>
   </ol>
  </div>
 </div>
</section>
<section class="sec sec-alt">
 <div class="wrap">
  <h2>See the pages</h2>
  <p class="sec-lead">Page 1 of the free test and a page of worked answers. Tap to see full size.</p>
  {samples(root, ("diagnostic", "key"))}
 </div>
</section>
<section class="sec">
 <div class="wrap">
  {faq_html}
  <p class="sec-cta">{go}</p>
 </div>
</section>
"""
    body += foot(root, cta=False)
    write("free/index.html", body)


def page_about(lessons):
    root = "../"
    body = head(f"About | {NAME}",
                "Key Move Math teaches competition math as a set of named tools, with free video lessons and mock tests for grades 1 to 12.",
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
  <p>Students getting ready for Math Kangaroo, the Noetic Math Contest, MATHCOUNTS, AMC 8, 10 and 12, and math olympiads. The Grade 5 tools are out now. Other grades follow.</p>
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
    urls = ["", "free/", "lessons/", "grade-5/", "mock-tests/", "about/"]
    page_group("grade-5", f"Grade 5 Competition Math Lessons | {NAME}", "Grade 5 tools",
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
    page_tests(lessons, SHOP)
    page_free()
    page_about(lessons)
    page_404()
    for l in lessons:
        page_qr(l)
    urls += [f"lessons/{l['slug']}/" for l in lessons if l["live"]]
    extras(lessons, urls)
    print(f"built {OUT}: {sum(l['live'] for l in lessons)} of {len(lessons)} lessons live")


if __name__ == "__main__":
    main()
