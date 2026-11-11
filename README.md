# Key Move Math website

Static site for the Key Move Math YouTube channel (https://www.youtube.com/@keymovemath), hosted free on GitHub Pages. The site lives at https://keymovemath.com (the repo keeps its old name).

- `data/lessons.json`: every lesson (tool, hook, problem, trap, rule, contests, YouTube id).
- `assets/covers/`: lesson covers (`<slug>.webp`, `<slug>-lg.webp`, `<slug>.jpg`).
- `assets/img/`: `diagnostic-page1*.webp`, `sample-test-page1*.webp` and `sample-answer-key*.webp` are real test pages (from `mock-tests/preview/`) shown on Home, /free and Mock tests. Replace them when the tests change.
- `data/shop.json`: Payhip links. Buy buttons say Coming soon until `live` is true (the hourly `--check` sets it once Payhip takes payments).
- `build.py`: writes the site to `_site/` and warns when a lesson cover is missing. Parent FAQ text lives in `faqs()`.
- `/free` is one free diagnostic page for every grade: `FREE_TESTS` in `build.py` maps a grade to its sign-up form (only Grade 5 today); other grades show Coming soon. `--check` asks YouTube which lessons are public.
- `t/<n>/`: stable QR links (one per lesson, n = tool number) for tests and videos. Each sends the visitor to the lesson's YouTube video once it is public, and to its lesson page on this site until then.
- `.github/workflows/deploy.yml`: rebuilds and deploys on every push and every hour, so scheduled lessons show up on their release day.

Preview locally: `python3 build.py && python3 -m http.server -d _site`.
