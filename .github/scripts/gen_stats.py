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

# tokyonight, matching the github-readme-stats theme of the same name
BG = "#1a1b27"
PANEL = "#20222f"
ACCENT = "#70a5fd"
ICON = "#bf91f3"
TEXT = "#38bdae"
MUTED = "#7982a9"

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


def fetch_calendar(created_year):
    """Return {date: contribution_count} for the whole account history.

    With a token the GraphQL calendar gives exact per-day counts across every
    year. Without one, fall back to the public contributions HTML, which only
    covers the trailing year and exposes activity levels rather than counts.
    """
    if TOKEN:
        q = """query($login:String!,$from:DateTime!,$to:DateTime!){
          user(login:$login){ contributionsCollection(from:$from,to:$to){
            contributionCalendar{ weeks{ contributionDays{ date contributionCount }}}}}}"""
        days = {}
        for year in range(created_year, dt.datetime.now(dt.timezone.utc).year + 1):
            cal = graphql(q, {
                "login": USER,
                "from": f"{year}-01-01T00:00:00Z",
                "to": f"{year}-12-31T23:59:59Z",
            })["user"]["contributionsCollection"]["contributionCalendar"]
            for week in cal["weeks"]:
                for day in week["contributionDays"]:
                    days[day["date"]] = day["contributionCount"]
        return days, True

    import re
    req = urllib.request.Request(
        f"https://github.com/users/{USER}/contributions",
        headers={"User-Agent": "profile-stats"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        html = r.read().decode("utf-8", "replace")
    # Only the level (0 to 4) is exposed here, so treat it as presence.
    days = {d: (1 if int(lvl) > 0 else 0)
            for d, lvl in re.findall(
                r'data-date="(\d{4}-\d{2}-\d{2})"[^>]*data-level="(\d+)"', html)}
    return days, False


def streaks(days):
    """Current streak, longest streak and active-day count."""
    if not days:
        return 0, 0, 0, None, None

    ordered = sorted(days)
    active = sum(1 for d in ordered if days[d] > 0)

    longest = run = 0
    best_end = run_start = None
    best_start = best_endd = None
    for d in ordered:
        if days[d] > 0:
            run += 1
            if run == 1:
                run_start = d
            if run > longest:
                longest, best_start, best_endd = run, run_start, d
        else:
            run = 0

    # The current streak may legitimately end yesterday: today is still in play.
    today = dt.datetime.now(dt.timezone.utc).date()
    current = 0
    cursor = today
    if days.get(today.isoformat(), 0) == 0:
        cursor = today - dt.timedelta(days=1)
    while days.get(cursor.isoformat(), 0) > 0:
        current += 1
        cursor -= dt.timedelta(days=1)

    return current, longest, active, best_start, best_endd


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


def list_repos():
    """Prefer /user/repos, which includes private repos when the token is a PAT.

    The Actions GITHUB_TOKEN is scoped to a single repository and cannot
    enumerate the account, so fall back to the public listing.
    """
    if TOKEN:
        try:
            repos, page = [], 1
            while True:
                batch = _req("https://api.github.com/user/repos"
                             f"?per_page=100&page={page}&affiliation=owner&visibility=all")
                repos += batch
                if len(batch) < 100:
                    break
                page += 1
            if repos:
                return repos, True
        except urllib.error.HTTPError:
            pass

    repos, page = [], 1
    while True:
        batch = api(f"/users/{USER}/repos?per_page=100&page={page}&type=owner")
        repos += batch
        if len(batch) < 100:
            break
        page += 1
    return repos, False


def collect():
    user = api(f"/users/{USER}")
    repos, saw_private = list_repos()

    owned = [r for r in repos if not r["fork"]]
    private = sum(1 for r in owned if r.get("private"))
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

    stars = sum(r["stargazers_count"] for r in owned)
    followers = user.get("followers", 0)

    reviews = 0
    if TOKEN:
        try:
            reviews = graphql(
                "query($l:String!){user(login:$l){contributionsCollection"
                "{totalPullRequestReviewContributions}}}", {"l": USER}
            )["user"]["contributionsCollection"]["totalPullRequestReviewContributions"]
        except Exception:
            reviews = 0

    grade, percentile = calculate_rank(commits, prs, issues, reviews, stars, followers)

    calendar, exact_calendar = fetch_calendar(created_year)
    cur_streak, longest_streak, active_days, best_start, best_end = streaks(calendar)

    return {
        "current_streak": cur_streak,
        "longest_streak": longest_streak,
        "active_days": active_days,
        "best_start": best_start,
        "best_end": best_end,
        "exact_calendar": exact_calendar,
        "repos": len(owned),
        "private": private,
        "saw_private": saw_private,
        "stars": stars,
        "forks": sum(r["forks_count"] for r in owned),
        "followers": followers,
        "commits": commits,
        "prs": prs,
        "issues": issues,
        "reviews": reviews,
        "grade": grade,
        "percentile": percentile,
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
        f'<stop offset="0" stop-color="{ACCENT}"/><stop offset="1" stop-color="{ICON}"/>'
        f'</linearGradient>'
        f'<linearGradient id="sheen" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="#222434"/><stop offset="1" stop-color="{BG}"/>'
        f'</linearGradient>'
        f'<linearGradient id="ring" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="{ACCENT}"/><stop offset="1" stop-color="{ICON}"/>'
        f'</linearGradient>'
        f'</defs>'
        f'<style>'
        f'.ti{{font:700 15px "Segoe UI",Ubuntu,sans-serif;fill:{ACCENT};letter-spacing:.5px}}'
        f'.sub{{font:400 10px "Segoe UI",Ubuntu,sans-serif;fill:{MUTED}}}'
        f'.num{{font:700 19px "Segoe UI",Ubuntu,sans-serif;fill:#fff}}'
        f'.lab{{font:400 9px "Segoe UI",Ubuntu,sans-serif;fill:{MUTED};letter-spacing:.6px}}'
        f'.k{{font:400 12.5px "Segoe UI",Ubuntu,sans-serif;fill:{TEXT}}}'
        f'.v{{font:700 12.5px "Segoe UI",Ubuntu,sans-serif;fill:#fff}}'
        f'.gr{{font:700 30px "Segoe UI",Ubuntu,sans-serif;fill:{ACCENT}}}'
        f'@keyframes fi{{from{{opacity:0;transform:translateY(6px)}}to{{opacity:1;transform:translateY(0)}}}}'
        f'.r{{animation:fi .5s ease-out both}}'
        f'@keyframes gw{{from{{width:0}}}}'
        f'.b{{animation:gw .9s cubic-bezier(.2,.8,.2,1) both}}'
        f'@keyframes dash{{from{{stroke-dashoffset:var(--c)}}}}'
        f'.ring{{animation:dash 1.1s ease-out both}}'
        f'</style>'
        f'<rect width="{w}" height="{h}" rx="12" fill="url(#sheen)" stroke="#2a2e45"/>'
        f'<rect x="0" y="12" width="3" height="26" rx="1.5" fill="url(#edge)"/>'
        f'<text x="20" y="30" class="ti">{esc(title)}</text>'
        f'<text x="{w - 20}" y="30" class="sub" text-anchor="end">{esc(subtitle)}</text>'
    )


def exponential_cdf(x):
    return 1 - 2 ** -x


def log_normal_cdf(x):
    return x / (1 + x)


def calculate_rank(commits, prs, issues, reviews, stars, followers):
    """Port of github-readme-stats src/calculateRank.js so the grade is comparable."""
    weights = [
        (2, exponential_cdf, commits / 1000),
        (3, exponential_cdf, prs / 50),
        (1, exponential_cdf, issues / 25),
        (1, exponential_cdf, reviews / 2),
        (4, log_normal_cdf, stars / 50),
        (1, log_normal_cdf, followers / 10),
    ]
    total_w = sum(w for w, _, _ in weights)
    score = sum(w * fn(v) for w, fn, v in weights) / total_w
    pct = (1 - score) * 100

    thresholds = [1, 12.5, 25, 37.5, 50, 62.5, 75, 87.5, 100]
    levels = ["S", "A+", "A", "A-", "B+", "B", "B-", "C+", "C"]
    grade = next(l for t, l in zip(thresholds, levels) if pct <= t)
    return grade, pct


def stats_card(d):
    w, h = 470, 215
    repo_label = "REPOSITORIES"
    if d["saw_private"] and d["private"]:
        repo_label = f"REPOS ({d['private']} PRIVATE)"
    tiles = [
        ("COMMITS", d["commits"]), (repo_label, d["repos"]),
        ("STARS EARNED", d["stars"]), ("FOLLOWERS", d["followers"]),
        ("ISSUES OPENED", d["issues"]), ("LANGUAGES", len(d["langs"])),
    ]
    out = [shell(w, h, "GITHUB STATS", f"{d['years']} yrs active")]

    cols, cw, ch = 2, 115, 48
    x0, y0 = 20, 48
    for i, (label, value) in enumerate(tiles):
        cx = x0 + (i % cols) * (cw + 6)
        cy = y0 + (i // cols) * (ch + 6)
        out.append(
            f'<g class="r" style="animation-delay:{i * .07:.2f}s">'
            f'<rect x="{cx}" y="{cy}" width="{cw}" height="{ch}" rx="8" '
            f'fill="{PANEL}" stroke="#2a2e45"/>'
            f'<text x="{cx + 12}" y="{cy + 26}" class="num">{human(value)}</text>'
            f'<text x="{cx + 12}" y="{cy + 40}" class="lab">{label}</text></g>'
        )

    # Rank ring. Fill reflects standing, so a lower percentile fills more.
    grade, pct = d["grade"], d["percentile"]
    cx, cy, rad = 375, 122, 46
    circ = 2 * 3.14159265 * rad
    filled = circ * max(0.02, (100 - pct) / 100)
    out.append(
        f'<g transform="translate({cx},{cy})">'
        f'<circle r="{rad}" fill="none" stroke="#2a2e45" stroke-width="7"/>'
        f'<circle class="ring" style="--c:{circ:.1f}" r="{rad}" fill="none" '
        f'stroke="url(#ring)" stroke-width="7" stroke-linecap="round" '
        f'stroke-dasharray="{filled:.1f} {circ - filled:.1f}" '
        f'transform="rotate(-90)"/>'
        f'<text y="4" class="gr" text-anchor="middle">{esc(grade)}</text>'
        f'<text y="22" class="lab" text-anchor="middle">TOP {pct:.1f}%</text>'
        f'</g>'
    )
    return "".join(out) + "</svg>"


def langs_card(d, top=6):
    langs = d["langs"][:top]
    total = sum(v for _, v in d["langs"]) or 1
    w = 470
    h = 215
    out = [shell(w, h, "LANGUAGES", f"{d['repos']} repositories")]

    # stacked summary bar
    bx, bw = 20, w - 40
    x = bx
    for i, (name, count) in enumerate(langs):
        seg = bw * count / total
        color = LANG_COLORS.get(name, FALLBACK[i % len(FALLBACK)])
        out.append(f'<rect class="b" style="animation-delay:{i * .06:.2f}s" '
                   f'x="{x:.1f}" y="44" width="{seg:.1f}" height="9" fill="{color}"/>')
        x += seg

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
        y += 22
    return "".join(out) + "</svg>"


def streak_card(d):
    w, h = 560, 165
    cur, longest, active = d["current_streak"], d["longest_streak"], d["active_days"]
    span = ""
    if d["best_start"] and d["best_end"]:
        fmt = lambda s: dt.date.fromisoformat(s).strftime("%d %b %Y")
        span = fmt(d["best_start"]) if d["best_start"] == d["best_end"] else \
            f'{fmt(d["best_start"])} to {fmt(d["best_end"])}'

    scope = "all time" if d["exact_calendar"] else "past year"
    out = [shell(w, h, "CONTRIBUTION STREAK", scope)]

    third = w / 3
    for i, (value, label, sub) in enumerate([
        (active, "ACTIVE DAYS", ""),
        (cur, "CURRENT STREAK", "days"),
        (longest, "LONGEST STREAK", span),
    ]):
        cx = third * i + third / 2
        if i == 1:
            # Ring sits above the shared label baseline so the two never overlap.
            rad, circ = 29, 2 * 3.14159265 * 29
            frac = 0 if longest == 0 else min(1.0, cur / max(longest, 1))
            filled = circ * max(0.02, frac)
            out.append(
                f'<g transform="translate({cx:.0f},86)">'
                f'<circle r="{rad}" fill="none" stroke="#2a2e45" stroke-width="6"/>'
                f'<circle class="ring" style="--c:{circ:.1f}" r="{rad}" fill="none" '
                f'stroke="url(#ring)" stroke-width="6" stroke-linecap="round" '
                f'stroke-dasharray="{filled:.1f} {circ - filled:.1f}" transform="rotate(-90)"/>'
                f'<text y="8" class="gr" text-anchor="middle" '
                f'style="font-size:24px">{value}</text></g>'
                f'<text x="{cx:.0f}" y="132" class="lab" text-anchor="middle">{label}</text>'
                f'<text x="{cx:.0f}" y="148" class="sub" text-anchor="middle">{esc(sub)}</text>'
            )
        else:
            out.append(
                f'<g class="r" style="animation-delay:{i * .1:.1f}s">'
                f'<text x="{cx:.0f}" y="96" class="num" text-anchor="middle" '
                f'style="font-size:26px">{human(value)}</text>'
                f'<text x="{cx:.0f}" y="132" class="lab" text-anchor="middle">{label}</text>'
                f'<text x="{cx:.0f}" y="148" class="sub" text-anchor="middle">{esc(sub)}</text>'
                f'</g>'
            )

    for x in (third, third * 2):
        out.append(f'<line x1="{x:.0f}" y1="52" x2="{x:.0f}" y2="152" stroke="#2a2e45"/>')
    return "".join(out) + "</svg>"


if __name__ == "__main__":
    data = collect()
    os.makedirs(OUT_DIR, exist_ok=True)
    for fname, svg in (("stats.svg", stats_card(data)),
                       ("top-langs.svg", langs_card(data)),
                       ("streak.svg", streak_card(data))):
        with open(os.path.join(OUT_DIR, fname), "w", encoding="utf-8") as f:
            f.write(svg)
        print("wrote", fname)
    print(f"commits={data['commits']} repos={data['repos']} stars={data['stars']} "
          f"issues={data['issues']} langs={len(data['langs'])} "
          f"rank={data['grade']} (top {data['percentile']:.1f}%)")
