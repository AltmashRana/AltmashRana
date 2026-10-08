#!/usr/bin/env python3
import calendar
import json
import os
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from xml.sax.saxutils import escape

USERNAME = os.environ["USER_NAME"]
TOKEN = os.environ["ACCESS_TOKEN"]
API_URL = "https://api.github.com/graphql"

HEADER = "@altmashRana"

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ascii_art.txt")) as f:
    ASCII_ART_LIGHT = f.read().splitlines()

ASCII_ART_DARK = ASCII_ART_LIGHT


def run_query(query: str) -> dict:
    body = json.dumps({"query": query}).encode("utf-8")
    req = urllib.request.Request(
        API_URL,
        data=body,
        headers={
            "Authorization": f"bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": USERNAME,
        },
        method="POST",
    )
    last_err = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if "errors" in data:
                    raise RuntimeError(f"GraphQL errors: {data['errors']}")
                return data["data"]
        except (urllib.error.URLError, RuntimeError) as e:
            last_err = e
            if attempt < 2:
                time.sleep(2 ** attempt)
    raise SystemExit(f"GraphQL request failed after retries: {last_err}")


def fetch_profile_and_repos() -> dict:
    query = f"""
    {{
      user(login: "{USERNAME}") {{
        name
        createdAt
        followers {{ totalCount }}
        repositories(first: 100, ownerAffiliations: [OWNER, ORGANIZATION_MEMBER], isFork: false) {{
          totalCount
          nodes {{ stargazerCount forkCount }}
          pageInfo {{ hasNextPage endCursor }}
        }}
      }}
    }}
    """
    data = run_query(query)["user"]
    repos = data["repositories"]["nodes"]
    cursor = data["repositories"]["pageInfo"]["endCursor"]
    has_next = data["repositories"]["pageInfo"]["hasNextPage"]

    while has_next:
        page_query = f"""
        {{
          user(login: "{USERNAME}") {{
            repositories(first: 100, after: "{cursor}", ownerAffiliations: [OWNER, ORGANIZATION_MEMBER], isFork: false) {{
              nodes {{ stargazerCount forkCount }}
              pageInfo {{ hasNextPage endCursor }}
            }}
          }}
        }}
        """
        page = run_query(page_query)["user"]["repositories"]
        repos.extend(page["nodes"])
        has_next = page["pageInfo"]["hasNextPage"]
        cursor = page["pageInfo"]["endCursor"]

    return {
        "name": data["name"] or USERNAME,
        "created_at": data["createdAt"],
        "followers": data["followers"]["totalCount"],
        "public_repos": data["repositories"]["totalCount"],
        "stars": sum(r["stargazerCount"] for r in repos),
        "forks": sum(r["forkCount"] for r in repos),
    }


def fetch_alltime_contributions(join_year: int) -> dict:
    now = datetime.now(timezone.utc)
    aliases = []
    for year in range(join_year, now.year + 1):
        start = f"{year}-01-01T00:00:00Z"
        end = (
            now.isoformat().replace("+00:00", "Z")
            if year == now.year
            else f"{year + 1}-01-01T00:00:00Z"
        )
        aliases.append(f"""
        y{year}: user(login: "{USERNAME}") {{
          contributionsCollection(from: "{start}", to: "{end}") {{
            totalCommitContributions
            totalPullRequestContributions
            totalIssueContributions
          }}
        }}
        """)
    # last 12 months, current month included (the API caps a collection at one year)
    first = now.year * 12 + now.month - 12
    months = [f"{m // 12}-{m % 12 + 1:02d}" for m in range(first, first + 12)]
    aliases.append(f"""
    cal: user(login: "{USERNAME}") {{
      contributionsCollection(from: "{months[0]}-01T00:00:00Z", to: "{now.isoformat().replace("+00:00", "Z")}") {{
        contributionCalendar {{ weeks {{ contributionDays {{ date contributionCount }} }} }}
      }}
    }}
    """)
    query = "{" + "".join(aliases) + "}"
    data = run_query(query)

    by_month = dict.fromkeys(months, 0)
    for week in data.pop("cal")["contributionsCollection"]["contributionCalendar"]["weeks"]:
        for day in week["contributionDays"]:
            if day["date"][:7] in by_month:
                by_month[day["date"][:7]] += day["contributionCount"]

    commits = prs = issues = 0
    for year_data in data.values():
        c = year_data["contributionsCollection"]
        commits += c["totalCommitContributions"]
        prs += c["totalPullRequestContributions"]
        issues += c["totalIssueContributions"]
    return {"commits": commits, "prs": prs, "issues": issues, "contributions_by_month": by_month}


# label, stats key, dark accent, light accent, 16x16 line icon
STAT_CARDS = [
    ("Repos", "public_repos", "#58a6ff", "#0969da",
     '<rect x="3" y="2" width="10" height="12" rx="2"/><line x1="6.5" y1="2" x2="6.5" y2="14"/>'),
    ("Stars", "stars", "#e3b341", "#9a6700",
     '<polygon points="8,1.5 9.9,5.8 14.5,6.2 11,9.3 12.1,13.9 8,11.4 3.9,13.9 5,9.3 1.5,6.2 6.1,5.8"/>'),
    ("Commits", "commits", "#3fb950", "#1a7f37",
     '<circle cx="8" cy="8" r="3"/><line x1="1" y1="8" x2="5" y2="8"/><line x1="11" y1="8" x2="15" y2="8"/>'),
    ("Pull Requests", "prs", "#bc8cff", "#8250df",
     '<circle cx="4" cy="3.5" r="2"/><circle cx="4" cy="12.5" r="2"/><circle cx="12" cy="12.5" r="2"/>'
     '<line x1="4" y1="5.5" x2="4" y2="10.5"/><path d="M12,10.5 V7 a3,3 0 0 0 -3,-3 H7.5"/>'),
    ("Issues", "issues", "#f85149", "#cf222e",
     '<circle cx="8" cy="8" r="6"/><circle cx="8" cy="8" r="1.2" fill="currentColor"/>'),
    ("Followers", "followers", "#39c5cf", "#1b7c83",
     '<circle cx="8" cy="5.5" r="2.8"/><path d="M2.5,14 a5.5,5.5 0 0 1 11,0"/>'),
]

CARD_W, CARD_H, CARD_GAP, GRID_COLS = 136, 104, 12, 3


def render_svg(stats: dict, dark: bool) -> str:
    bg = "#0d1117" if dark else "#ffffff"
    border = "#30363d" if dark else "#e1e4e8"
    header_color = "#58a6ff" if dark else "#0969da"
    label_color = "#8b949e" if dark else "#57606a"
    card_bg = "#161b22" if dark else "#f6f8fa"
    card_border = "#30363d" if dark else "#d0d7de"
    art_color = "#c9d1d9" if dark else "#24292f"
    text_color = "#e6edf3" if dark else "#1f2328"

    art_lines = ASCII_ART_DARK if dark else ASCII_ART_LIGHT
    art_font, art_lh, art_char_w = 6, 6, 3.6
    art_width = max(len(l) for l in art_lines) * art_char_w
    art_height = len(art_lines) * art_lh

    rows = -(-len(STAT_CARDS) // GRID_COLS)
    grid_w = GRID_COLS * CARD_W + (GRID_COLS - 1) * CARD_GAP
    grid_h = rows * CARD_H + (rows - 1) * CARD_GAP

    header_block_h = 72
    chart_h = 216
    info_width = grid_w
    info_height = header_block_h + grid_h + chart_h

    pad = 24
    gap = 36
    height = max(art_height + 2 * pad, info_height + 2 * pad)
    art_x = pad
    info_x = pad + art_width + gap + pad
    width = info_x + info_width + pad

    parts = [
        f'<svg width="{width:.0f}" height="{height:.0f}" viewBox="0 0 {width:.0f} {height:.0f}" '
        f'xmlns="http://www.w3.org/2000/svg" font-family="-apple-system, Segoe UI, Roboto, '
        f'SFMono-Regular, Consolas, \'Liberation Mono\', Menlo, monospace">',
        f'<rect x="0.5" y="0.5" width="{width - 1:.0f}" height="{height - 1:.0f}" rx="6" '
        f'fill="{bg}" stroke="{border}"/>',
    ]

    def tl(text_len_chars, char_w):
        return f'textLength="{text_len_chars * char_w:.1f}" lengthAdjust="spacingAndGlyphs"'

    art_y0 = (height - art_height) / 2
    for i, line in enumerate(art_lines):
        if not line.strip():
            continue
        y = art_y0 + (i + 1) * art_lh
        parts.append(
            f'<text x="{art_x:.0f}" y="{y:.0f}" fill="{art_color}" font-size="{art_font}" '
            f'xml:space="preserve" {tl(len(line), art_char_w)}>{escape(line)}</text>'
        )

    info_y0 = (height - info_height) / 2
    parts.append(
        f'<text x="{info_x:.0f}" y="{info_y0 + 22:.0f}" fill="{text_color}" '
        f'font-size="24" font-weight="800">{escape(stats["name"])}</text>'
    )
    parts.append(
        f'<text x="{info_x:.0f}" y="{info_y0 + 43:.0f}" fill="{label_color}" font-size="12">'
        f'<tspan fill="{header_color}" font-weight="600">{escape(HEADER)}</tspan>'
        f' · on GitHub since {stats["created_at"][:4]}</text>'
    )
    underline_end = STAT_CARDS[3][2 if dark else 3]
    parts.append(
        f'<defs><linearGradient id="underline"><stop offset="0" stop-color="{header_color}"/>'
        f'<stop offset="1" stop-color="{underline_end}"/></linearGradient></defs>'
        f'<rect x="{info_x:.0f}" y="{info_y0 + 54:.0f}" width="56" height="3" rx="1.5" fill="url(#underline)"/>'
    )

    grid_y0 = info_y0 + header_block_h
    for idx, (label, key, accent_dark, accent_light, icon) in enumerate(STAT_CARDS):
        col = idx % GRID_COLS
        row = idx // GRID_COLS
        cx = info_x + col * (CARD_W + CARD_GAP)
        cy = grid_y0 + row * (CARD_H + CARD_GAP)
        accent = accent_dark if dark else accent_light
        card = f'x="{cx:.0f}" y="{cy:.0f}" width="{CARD_W}" height="{CARD_H}" rx="12"'
        parts.append(
            f'<defs><linearGradient id="wash{idx}" x1="0" y1="0" x2="1" y2="1">'
            f'<stop offset="0" stop-color="{accent}" stop-opacity="0.18"/>'
            f'<stop offset="0.7" stop-color="{accent}" stop-opacity="0"/></linearGradient></defs>'
        )
        parts.append(f'<rect {card} fill="{card_bg}"/>')
        parts.append(f'<rect {card} fill="url(#wash{idx})" stroke="{card_border}"/>')
        parts.append(
            f'<rect x="{cx + 14:.0f}" y="{cy + 14:.0f}" width="28" height="28" rx="8" '
            f'fill="{accent}" fill-opacity="0.16"/>'
        )
        parts.append(
            f'<g transform="translate({cx + 20:.0f},{cy + 20:.0f})" fill="none" stroke="{accent}" '
            f'color="{accent}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">{icon}</g>'
        )
        parts.append(
            f'<text x="{cx + 14:.0f}" y="{cy + 74:.0f}" fill="{text_color}" '
            f'font-size="26" font-weight="800">{stats[key]}</text>'
        )
        parts.append(
            f'<text x="{cx + 14:.0f}" y="{cy + 91:.0f}" fill="{label_color}" '
            f'font-size="9.5" font-weight="600" letter-spacing="0.6">{escape(label.upper())}</text>'
        )

    by_month = stats.get("contributions_by_month", {})
    months = sorted(by_month)
    chart_y0 = grid_y0 + grid_h + 28
    parts.append(
        f'<text x="{info_x:.0f}" y="{chart_y0:.0f}" fill="{label_color}" '
        f'font-size="13" font-weight="700" letter-spacing="0.5">CONTRIBUTION ACTIVITY</text>'
    )
    if months:
        vals = [by_month[m] for m in months]
        top, baseline = chart_y0 + 32, chart_y0 + 169
        for gy in (top, (top + baseline) / 2):
            parts.append(
                f'<line x1="{info_x:.0f}" x2="{info_x + grid_w:.0f}" y1="{gy:.1f}" y2="{gy:.1f}" '
                f'stroke="{card_border}" stroke-dasharray="2 4"/>'
            )
        max_val = max(1, max(vals))
        inset = 14
        step = (grid_w - 2 * inset) / max(1, len(months) - 1)
        pts = [
            (info_x + inset + i * step, baseline - (v / max_val) * (baseline - top))
            for i, v in enumerate(vals)
        ]
        line = f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            mid = (x0 + x1) / 2
            line += f" C{mid:.1f},{y0:.1f} {mid:.1f},{y1:.1f} {x1:.1f},{y1:.1f}"
        parts.append(
            f'<defs><linearGradient id="area" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0" stop-color="{header_color}" stop-opacity="0.45"/>'
            f'<stop offset="1" stop-color="{header_color}" stop-opacity="0"/></linearGradient></defs>'
        )
        parts.append(
            f'<path d="{line} L{pts[-1][0]:.1f},{baseline:.1f} L{pts[0][0]:.1f},{baseline:.1f} Z" fill="url(#area)"/>'
        )
        parts.append(
            f'<path d="{line}" fill="none" stroke="{header_color}" stroke-width="2.5" stroke-linecap="round"/>'
        )
        peak = vals.index(max(vals))
        for i, (px, py) in enumerate(pts):
            if i == peak:
                parts.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="4.5" fill="{header_color}"/>')
                parts.append(
                    f'<text x="{px:.1f}" y="{py - 10:.1f}" fill="{art_color}" font-size="11" '
                    f'font-weight="700" text-anchor="middle">{vals[i]}</text>'
                )
            else:
                parts.append(
                    f'<circle cx="{px:.1f}" cy="{py:.1f}" r="2.5" fill="{bg}" '
                    f'stroke="{header_color}" stroke-width="1.5"/>'
                )
            parts.append(
                f'<text x="{px:.1f}" y="{baseline + 16:.1f}" fill="{label_color}" '
                f'font-size="10" text-anchor="middle">{calendar.month_abbr[int(months[i][5:])]}</text>'
            )

    parts.append("</svg>")
    return "\n".join(parts)


def main():
    profile = fetch_profile_and_repos()
    join_year = int(profile["created_at"][:4])
    contributions = fetch_alltime_contributions(join_year)
    stats = {**profile, **contributions}

    with open("dark_mode.svg", "w") as f:
        f.write(render_svg(stats, dark=True))
    with open("light_mode.svg", "w") as f:
        f.write(render_svg(stats, dark=False))

    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
