# Mathlete Toolkit website

Static site for the Mathlete Toolkit YouTube channel, hosted free on GitHub Pages.

- `data/lessons.json`: every lesson (tool, hook, problem, trap, rule, contests, YouTube id).
- `assets/covers/`: lesson covers (`<slug>.webp`, `<slug>-lg.webp`, `<slug>.jpg`).
- `build.py`: writes the site to `_site/`. `--check` asks YouTube which lessons are public.
- `.github/workflows/deploy.yml`: rebuilds and deploys on every push and every hour, so scheduled lessons show up on their release day.

Preview locally: `python3 build.py && python3 -m http.server -d _site`.
