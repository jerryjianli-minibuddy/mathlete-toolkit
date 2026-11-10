# Key Move Math website

Static site for the Key Move Math YouTube channel (https://www.youtube.com/@keymovemath), hosted free on GitHub Pages. The repo keeps its old name, so the site lives at https://jerryjianli-minibuddy.github.io/mathlete-toolkit/.

- `data/lessons.json`: every lesson (tool, hook, problem, trap, rule, contests, YouTube id).
- `assets/covers/`: lesson covers (`<slug>.webp`, `<slug>-lg.webp`, `<slug>.jpg`).
- `build.py`: writes the site to `_site/`. `--check` asks YouTube which lessons are public.
- `t/<n>/`: stable QR links (one per lesson, n = tool number) for tests and videos. Each sends the visitor to the lesson's YouTube video once it is public, and to its lesson page on this site until then.
- `.github/workflows/deploy.yml`: rebuilds and deploys on every push and every hour, so scheduled lessons show up on their release day.

Preview locally: `python3 build.py && python3 -m http.server -d _site`.
