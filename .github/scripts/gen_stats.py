"""Render self-hosted GitHub stats cards as SVG.

The public github-readme-stats instance is frequently rate-limited (HTTP 503),
so the cards are generated here and committed to the repo instead.
"""

import json
import os
import urllib.request

USER = os.environ.get("GH_USER", "PrageethM1702")
TOKEN = os.environ.get("GITHUB_TOKEN")
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "assets")

BG = "#0D1526"
ACCENT = "#7FB3E8"
TEXT = "#C8DCF5"
MUTED = "#6E88AB"

LANG_COLORS = {
    "Python": "#3572A5", "Jupyter Notebook": "#DA5B0B", "MATLAB": "#e16737",
    "C++": "#f34b7d", "C": "#555555", "HTML": "#e34c26", "CSS": "#563d7c",
    "JavaScript": "#f1e05a", "Shell": "#89e051", "TeX": "#3D6117",
    "CMake": "#DA3434", "Makefile": "#427819", "Dockerfile": "#384d54",
}
FALLBACK = ["#7FB3E8", "#5B8FD4", "#4A6FA5", "#3E5C8A", "#9BC4EC", "#2F4A70"]


def api(path):
    req = urllib.request.Request(
        f"https://api.github.com{path}",
        headers={
            "User-Agent": "profile-stats",
            "Accept": "application/vnd.github+json",
            **({"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}),
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def collect():
    user = api(f"/users/{USER}")
    repos, page = [], 1
    while True:
        batch = api(f"/users/{USER}/repos?per_page=100&page={page}&type=owner")
        repos += batch
        if len(batch) < 100:
            break
        page += 1

    owned = [r for r in repos if not r["fork"]]
    stars = sum(r["stargazers_count"] for r in owned)
    forks = sum(r["forks_count"] for r in owned)

    # Count each repo's primary language rather than raw bytes: .ipynb files
    # embed their cell output, so a byte-weighted split reads ~98% notebooks
    # and hides everything else.
    totals = {}
    for r in owned:
        lang = r.get("language")
        if lang:
            totals[lang] = totals.get(lang, 0) + 1

    return {
        "name": user.get("name") or USER,
        "repos": len(owned),
        "stars": stars,
        "forks": forks,
        "followers": user.get("followers", 0),
        "langs": sorted(totals.items(), key=lambda kv: -kv[1]),
    }


def header(w, h, title):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" role="img" aria-label="{esc(title)}">'
        f'<title>{esc(title)}</title>'
        f'<style>'
        f'.t{{font:600 16px "Segoe UI",Ubuntu,sans-serif;fill:{ACCENT}}}'
        f'.k{{font:400 13px "Segoe UI",Ubuntu,sans-serif;fill:{TEXT}}}'
        f'.v{{font:600 13px "Segoe UI",Ubuntu,sans-serif;fill:#fff}}'
        f'.s{{font:400 11px "Segoe UI",Ubuntu,sans-serif;fill:{MUTED}}}'
        f'@keyframes fi{{from{{opacity:0;transform:translateX(-8px)}}'
        f'to{{opacity:1;transform:translateX(0)}}}}'
        f'.r{{animation:fi .5s ease-out both}}'
        f'@keyframes gw{{from{{width:0}}}}'
        f'.b{{animation:gw .9s ease-out both}}'
        f'</style>'
        f'<rect width="{w}" height="{h}" rx="10" fill="{BG}" stroke="#1B2A4A"/>'
        f'<text x="22" y="32" class="t">{esc(title)}</text>'
    )


def stats_card(d):
    w, h = 420, 195
    rows = [("Public repositories", d["repos"]), ("Total stars earned", d["stars"]),
            ("Total forks", d["forks"]), ("Followers", d["followers"])]
    out = [header(w, h, "GitHub Stats")]
    y = 66
    for i, (k, v) in enumerate(rows):
        out.append(f'<g class="r" style="animation-delay:{i * .1:.1f}s">'
                   f'<text x="22" y="{y}" class="k">{esc(k)}</text>'
                   f'<text x="{w - 22}" y="{y}" class="v" text-anchor="end">{v}</text></g>')
        y += 30
    out.append(f'<text x="22" y="{h - 14}" class="s">Generated daily &#183; no external service</text>')
    return "".join(out) + "</svg>"


def langs_card(d, top=6):
    langs = d["langs"][:top]
    total = sum(v for _, v in d["langs"]) or 1
    w = 420
    h = 66 + len(langs) * 26 + 26
    out = [header(w, h, "Languages by Repository")]

    track_x, track_w = 236, 104   # bar sits between the label and the percentage
    y = 60
    for i, (name, count) in enumerate(langs):
        pct = count / total * 100
        color = LANG_COLORS.get(name, FALLBACK[i % len(FALLBACK)])
        bar = max(4, round(track_w * pct / 100))
        out.append(
            f'<g class="r" style="animation-delay:{i * .1:.1f}s">'
            f'<circle cx="28" cy="{y - 4}" r="5" fill="{color}"/>'
            f'<text x="42" y="{y}" class="k">{esc(name)}</text>'
            f'<rect x="{track_x}" y="{y - 12}" width="{track_w}" height="10" rx="5" fill="#1B2A4A"/>'
            f'<rect class="b" style="animation-delay:{i * .1:.1f}s" x="{track_x}" y="{y - 12}" '
            f'width="{bar}" height="10" rx="5" fill="{color}"/>'
            f'<text x="{w - 22}" y="{y}" class="v" text-anchor="end">{pct:.0f}%</text></g>'
        )
        y += 26
    out.append(f'<text x="22" y="{h - 14}" class="s">Share of public repositories by primary language</text>')
    return "".join(out) + "</svg>"


if __name__ == "__main__":
    data = collect()
    os.makedirs(OUT_DIR, exist_ok=True)
    for fname, svg in (("stats.svg", stats_card(data)),
                       ("top-langs.svg", langs_card(data))):
        with open(os.path.join(OUT_DIR, fname), "w", encoding="utf-8") as f:
            f.write(svg)
        print("wrote", fname)
    print(f"{data['repos']} repos, {data['stars']} stars, "
          f"top lang {data['langs'][0][0] if data['langs'] else 'n/a'}")
