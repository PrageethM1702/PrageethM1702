"""Render self-hosted GitHub stats cards as SVG.

The public github-readme-stats instance is paused and serves HTTP 503
(anuraghazra/github-readme-stats#4737), so the cards are generated here and
committed to the repo instead of being fetched at render time.

With GITHUB_TOKEN set (as in CI) commit totals come from the GraphQL
contributions API. Without one the script falls back to the REST search API so
it can still be run locally.
"""

import datetime as dt
import json
import os
import urllib.error
import urllib.request

USER = os.environ.get("GH_USER", "PrageethM1702")
TOKEN = os.environ.get("GITHUB_TOKEN")
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "assets")

BG = "#0D1526"
PANEL = "#132038"
ACCENT = "#7FB3E8"
TEXT = "#C8DCF5"
MUTED = "#6E88AB"

LANG_COLORS = {
    "Python": "#3572A5", "Jupyter Notebook": "#DA5B0B", "MATLAB": "#e16737",
    "C++": "#f34b7d", "C": "#555555", "HTML": "#e34c26", "CSS": "#563d7c",
    "JavaScript": "#f1e05a", "Shell": "#89e051", "TeX": "#3D6117",
    "CMake": "#DA3434", "Makefile": "#427819", "Dockerfile": "#384d54",
    "Component Pascal": "#B0CE4E",
}
FALLBACK = ["#7FB3E8", "#5B8FD4", "#4A6FA5", "#3E5C8A", "#9BC4EC", "#2F4A70"]


def _req(url, data=None, headers=None):
    h = {"User-Agent": "profile-stats", "Accept": "application/vnd.github+json"}
    if TOKEN:
        h["Authorization"] = f"Bearer {TOKEN}"
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=h)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def api(path):
    return _req(f"https://api.github.com{path}")


def graphql(query, variables):
    body = json.dumps({"query": query, "variables": variables}).encode()
    out = _req("https://api.github.com/graphql", data=body,
               headers={"Content-Type": "application/json"})
    if "errors" in out:
        raise RuntimeError(out["errors"])
    return out["data"]


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def human(n):
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M".replace(".0M", "M")
    if n >= 1_000:
        return f"{n / 1_000:.1f}k".replace(".0k", "k")
    return str(n)


def all_time_commits(created_year):
    """Sum commit contributions per year. GraphQL caps each query at one year."""
    q = """query($login:String!,$from:DateTime!,$to:DateTime!){
      user(login:$login){ contributionsCollection(from:$from,to:$to){
        totalCommitContributions restrictedContributionsCount } } }"""
    total = 0
    for year in range(created_year, dt.datetime.now(dt.timezone.utc).year + 1):
        d = graphql(q, {
            "login": USER,
            "from": f"{year}-01-01T00:00:00Z",
            "to": f"{year}-12-31T23:59:59Z",
        })["user"]["contributionsCollection"]
        total += d["totalCommitContributions"] + d["restrictedContributionsCount"]
    return total


def search_total(path):
    try:
        return _req(f"https://api.github.com/search/{path}&per_page=1")["total_count"]
    except urllib.error.HTTPError:
        return 0


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
    created_year = int(user["created_at"][:4])

    # Count each repo's primary language rather than raw bytes: .ipynb files
    # embed their cell output, so a byte-weighted split reads ~98% notebooks
    # and hides everything else.
    langs = {}
    for r in owned:
        if r.get("language"):
            langs[r["language"]] = langs.get(r["language"], 0) + 1

    if TOKEN:
        commits = all_time_commits(created_year)
        prs = graphql("query($l:String!){user(login:$l){pullRequests{totalCount}}}",
                      {"l": USER})["user"]["pullRequests"]["totalCount"]
        issues = graphql("query($l:String!){user(login:$l){issues{totalCount}}}",
                         {"l": USER})["user"]["issues"]["totalCount"]
    else:
        commits = search_total(f"commits?q=author:{USER}")
        prs = search_total(f"issues?q=author:{USER}+type:pr")
        issues = search_total(f"issues?q=author:{USER}+type:issue")

    return {
        "repos": len(owned),
        "stars": sum(r["stargazers_count"] for r in owned),
        "forks": sum(r["forks_count"] for r in owned),
        "followers": user.get("followers", 0),
        "commits": commits,
        "prs": prs,
        "issues": issues,
        "years": max(1, dt.datetime.now(dt.timezone.utc).year - created_year + 1),
        "langs": sorted(langs.items(), key=lambda kv: (-kv[1], kv[0])),
    }


def shell(w, h, title, subtitle):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" role="img" aria-label="{esc(title)}">'
        f'<title>{esc(title)}</title>'
        f'<defs>'
        f'<linearGradient id="edge" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{ACCENT}"/><stop offset="1" stop-color="#3E5C8A"/>'
        f'</linearGradient>'
        f'<linearGradient id="sheen" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="#16233c"/><stop offset="1" stop-color="{BG}"/>'
        f'</linearGradient>'
        f'</defs>'
        f'<style>'
        f'.ti{{font:700 15px "Segoe UI",Ubuntu,sans-serif;fill:{ACCENT};letter-spacing:.5px}}'
        f'.sub{{font:400 10px "Segoe UI",Ubuntu,sans-serif;fill:{MUTED}}}'
        f'.num{{font:700 21px "Segoe UI",Ubuntu,sans-serif;fill:#fff}}'
        f'.lab{{font:400 9.5px "Segoe UI",Ubuntu,sans-serif;fill:{MUTED};letter-spacing:.6px}}'
        f'.k{{font:400 12.5px "Segoe UI",Ubuntu,sans-serif;fill:{TEXT}}}'
        f'.v{{font:700 12.5px "Segoe UI",Ubuntu,sans-serif;fill:#fff}}'
        f'@keyframes fi{{from{{opacity:0;transform:translateY(6px)}}to{{opacity:1;transform:translateY(0)}}}}'
        f'.r{{animation:fi .5s ease-out both}}'
        f'@keyframes gw{{from{{width:0}}}}'
        f'.b{{animation:gw .9s cubic-bezier(.2,.8,.2,1) both}}'
        f'</style>'
        f'<rect width="{w}" height="{h}" rx="12" fill="url(#sheen)" stroke="#1E3153"/>'
        f'<rect x="0" y="12" width="3" height="26" rx="1.5" fill="url(#edge)"/>'
        f'<text x="20" y="30" class="ti">{esc(title)}</text>'
        f'<text x="{w - 20}" y="30" class="sub" text-anchor="end">{esc(subtitle)}</text>'
    )


def stats_card(d):
    w, h = 430, 210
    tiles = [
        ("COMMITS", d["commits"]), ("REPOSITORIES", d["repos"]),
        ("STARS EARNED", d["stars"]), ("FOLLOWERS", d["followers"]),
        ("ISSUES OPENED", d["issues"]), ("LANGUAGES", len(d["langs"])),
    ]
    out = [shell(w, h, "GITHUB STATS", f"{d['years']} yrs active")]

    cols, cw, ch = 3, 130, 62
    x0, y0 = 20, 48
    for i, (label, value) in enumerate(tiles):
        cx = x0 + (i % cols) * (cw + 5)
        cy = y0 + (i // cols) * (ch + 8)
        out.append(
            f'<g class="r" style="animation-delay:{i * .07:.2f}s">'
            f'<rect x="{cx}" y="{cy}" width="{cw}" height="{ch}" rx="8" '
            f'fill="{PANEL}" stroke="#1E3153"/>'
            f'<text x="{cx + 14}" y="{cy + 32}" class="num">{human(value)}</text>'
            f'<text x="{cx + 14}" y="{cy + 48}" class="lab">{label}</text></g>'
        )
    out.append(f'<text x="20" y="{h - 12}" class="sub">'
               f'Generated daily from the GitHub API</text>')
    return "".join(out) + "</svg>"


def langs_card(d, top=6):
    langs = d["langs"][:top]
    total = sum(v for _, v in d["langs"]) or 1
    w = 430
    h = 210
    out = [shell(w, h, "LANGUAGES", f"{d['repos']} repositories")]

    # stacked summary bar
    bx, bw = 20, w - 40
    x = bx
    for i, (name, count) in enumerate(langs):
        seg = bw * count / total
        color = LANG_COLORS.get(name, FALLBACK[i % len(FALLBACK)])
        out.append(f'<rect class="b" style="animation-delay:{i * .06:.2f}s" '
                   f'x="{x:.1f}" y="46" width="{seg:.1f}" height="9" fill="{color}"/>')
        x += seg
    out.append(f'<rect x="{bx}" y="46" width="{bw}" height="9" rx="4.5" fill="none"/>')

    y = 82
    for i, (name, count) in enumerate(langs):
        pct = count / total * 100
        color = LANG_COLORS.get(name, FALLBACK[i % len(FALLBACK)])
        out.append(
            f'<g class="r" style="animation-delay:{i * .07:.2f}s">'
            f'<circle cx="26" cy="{y - 4}" r="4.5" fill="{color}"/>'
            f'<text x="40" y="{y}" class="k">{esc(name)}</text>'
            f'<text x="{w - 20}" y="{y}" class="v" text-anchor="end">'
            f'{count} repo{"s" if count != 1 else ""} &#183; {pct:.0f}%</text></g>'
        )
        y += 21
    out.append(f'<text x="20" y="{h - 12}" class="sub">'
               f'By primary language, not bytes, so notebooks do not skew it</text>')
    return "".join(out) + "</svg>"


if __name__ == "__main__":
    data = collect()
    os.makedirs(OUT_DIR, exist_ok=True)
    for fname, svg in (("stats.svg", stats_card(data)),
                       ("top-langs.svg", langs_card(data))):
        with open(os.path.join(OUT_DIR, fname), "w", encoding="utf-8") as f:
            f.write(svg)
        print("wrote", fname)
    print(f"commits={data['commits']} repos={data['repos']} stars={data['stars']} "
          f"issues={data['issues']} langs={len(data['langs'])}")
