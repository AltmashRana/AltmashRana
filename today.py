#!/usr/bin/env python3
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

ASCII_ART_LIGHT = [
    '                                            #  #   #',
    '                                        #               %%#',
    '                                     #%',
    '                                   #                          %',
    ' ',
    ' ',
    ' ',
    '                               %    #+===-=----=-+**#######',
    '                                   #=--::...............::-=',
    '                                  %*+--:..              .:--*',
    '                                   #*-::.               .--=%',
    '                                   #+--:.               .:--=',
    '                                  #*+---::...   ..:--*###*---+',
    '                                  **         +-=+           -=',
    '                               *                                 -:',
    '                              #=              :.             *% --#',
    '                             *#=             #  =            -- =:=',
    '                              *# #           -. .=          #-=%*#-',
    '                              =+*##         #-...-=       %-:-+-:-.',
    '                               *=##+++**===+##*+**-==--::::::-+:--',
    '                                =+#+=------=##*#+#+-:--:...:-+-.:',
    '                                 ##*=----=*%   #     %=-::::-+',
    '                                   #+=--+     ####     -::---*',
    '                                   #*++==***#*====+*=-+----=*',
    '                                    %###*==+#     %*----*+*##',
    '                                     % ##+----+*+#=:::=*##%%',
    '                                     #%    #%#%%  %#%%    #*',
    '                                     ##%                ##*+',
    '                                     *####%          %##*=+-',
    '                                     #+*############*+++=---',
    '                                      +====+*###*++*+=--:--=',
    '                                      #++=----=++*+=------#',
    '                              %         %++==----------*',
    '                                             +--=--+',
    '                                                *+',
    '                    %                            #',
    ' ',
    '            #                                    ##',
    ' ',
    ' ',
    ' ',
    '      #',
    ' ',
    '                                                 %',
    '                                                 #%',
    '   %',
    ' ',
    ' ',
    ' ',
    ' ',
    '                                                 #',
    '                                                 #%',
    ' ',
    ' ',
    ' ',
    ' ',
    ' ',
    '                                                 #',
    '                                                 ##',
    ' ',
    '                                                                %##',
    '                                                        #+---::::::::-=+#',
    '                                                 %*=---:::...         .-=#',
    '                          %%=-----------==--------:.:....               -#',
    '                           =:::::::::--:::::::::......                  :#',
    '                          #:...:::.:.:...........               ..  .-#',
    '                         %:.......... . ..   .  ... .. .. .   .:-+',
    '                         -:.:.. ......:. . .:.::---:-::::::::-#%+-#',
    '                        -.::::.::::::::-:-------------:---+# +=----',
    '                       #:::-:----------==++=+-+-=-:---=#%#=---:-::-+',
    '                       #-------=-===++=+*+*===-==+*#% #--:-::::----=',
    '                        ======-=+++++*++++=-=**#  #+=-----:::-:----==',
    '                        #***=++#******#+***#   %#*+======---------=-==',
    '                         ####%########%   %##################**+++**#*%',
    '                                          %%###**+***###%% %% %%%%##%%#',
    '                                                    %%%#######%##%%%%%#%',
]

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
    query = "{" + "".join(aliases) + "}"
    data = run_query(query)

    commits = prs = issues = 0
    by_year = {}
    for alias, year_data in data.items():
        year = int(alias[1:])
        c = year_data["contributionsCollection"]
        commits += c["totalCommitContributions"]
        prs += c["totalPullRequestContributions"]
        issues += c["totalIssueContributions"]
        by_year[year] = c["totalCommitContributions"]
    return {"commits": commits, "prs": prs, "issues": issues, "commits_by_year": by_year}


STAT_CARDS = [
    ("Repos", "public_repos", "📦", "#58a6ff", "#0969da"),
    ("Stars", "stars", "⭐", "#e3b341", "#9a6700"),
    ("Commits", "commits", "✅", "#3fb950", "#1a7f37"),
    ("Pull Requests", "prs", "🔀", "#bc8cff", "#8250df"),
    ("Issues", "issues", "🐛", "#f85149", "#cf222e"),
    ("Followers", "followers", "👥", "#39c5cf", "#1b7c83"),
]

CARD_W, CARD_H, CARD_GAP, GRID_COLS = 180, 80, 14, 2


def render_svg(stats: dict, dark: bool) -> str:
    bg = "#0d1117" if dark else "#ffffff"
    border = "#30363d" if dark else "#e1e4e8"
    header_color = "#58a6ff" if dark else "#0969da"
    rule_color = "#484f58" if dark else "#8c959f"
    label_color = "#8b949e" if dark else "#57606a"
    card_bg = "#161b22" if dark else "#f6f8fa"
    card_border = "#30363d" if dark else "#d0d7de"
    art_color = "#c9d1d9" if dark else "#24292f"

    art_lines = ASCII_ART_DARK if dark else ASCII_ART_LIGHT
    art_font, art_lh, art_char_w = 6, 6, 3.6
    art_width = max(len(l) for l in art_lines) * art_char_w
    art_height = len(art_lines) * art_lh

    header_font = 20
    rule_len = 34
    rule_char_w = 9.5

    rows = -(-len(STAT_CARDS) // GRID_COLS)
    grid_w = GRID_COLS * CARD_W + (GRID_COLS - 1) * CARD_GAP
    grid_h = rows * CARD_H + (rows - 1) * CARD_GAP

    header_block_h = header_font + 16 + 24
    chart_h = 118
    info_width = max(len(HEADER) * (header_font * 0.6), rule_len * rule_char_w, grid_w)
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
        f'<text x="{info_x:.0f}" y="{info_y0 + header_font:.0f}" fill="{header_color}" '
        f'font-family="SFMono-Regular, Consolas, \'Liberation Mono\', Menlo, monospace" '
        f'font-size="{header_font}" font-weight="700" {tl(len(HEADER), header_font * 0.6)}>'
        f'{escape(HEADER)}</text>'
    )
    rule_y = info_y0 + header_font + 16
    parts.append(
        f'<text x="{info_x:.0f}" y="{rule_y:.0f}" fill="{rule_color}" '
        f'font-family="SFMono-Regular, Consolas, \'Liberation Mono\', Menlo, monospace" '
        f'font-size="{header_font}" {tl(rule_len, rule_char_w)}>{"─" * rule_len}</text>'
    )

    grid_y0 = rule_y + 24
    for idx, (label, key, icon, accent_dark, accent_light) in enumerate(STAT_CARDS):
        col = idx % GRID_COLS
        row = idx // GRID_COLS
        cx = info_x + col * (CARD_W + CARD_GAP)
        cy = grid_y0 + row * (CARD_H + CARD_GAP)
        accent = accent_dark if dark else accent_light
        parts.append(
            f'<rect x="{cx:.0f}" y="{cy:.0f}" width="{CARD_W}" height="{CARD_H}" rx="10" '
            f'fill="{card_bg}" stroke="{card_border}"/>'
        )
        parts.append(f'<rect x="{cx:.0f}" y="{cy:.0f}" width="3" height="{CARD_H}" rx="1.5" fill="{accent}"/>')
        parts.append(
            f'<text x="{cx + 14:.0f}" y="{cy + 24:.0f}" font-size="16">{icon}</text>'
        )
        parts.append(
            f'<text x="{cx + 14:.0f}" y="{cy + 50:.0f}" fill="{accent}" '
            f'font-size="22" font-weight="800">{stats[key]}</text>'
        )
        parts.append(
            f'<text x="{cx + 14:.0f}" y="{cy + 68:.0f}" fill="{label_color}" '
            f'font-size="10" font-weight="600" letter-spacing="0.5">{escape(label.upper())}</text>'
        )

    by_year = stats.get("commits_by_year", {})
    years = sorted(by_year)
    chart_y0 = grid_y0 + grid_h + 28
    parts.append(
        f'<text x="{info_x:.0f}" y="{chart_y0:.0f}" fill="{label_color}" '
        f'font-size="13" font-weight="700" letter-spacing="0.5">COMMITS BY YEAR</text>'
    )
    if years:
        baseline = chart_y0 + 78
        bar_max_h = 60
        max_val = max(1, max(by_year.values()))
        bar_gap = 10
        bar_w = (grid_w - (len(years) - 1) * bar_gap) / len(years)
        for i, yr in enumerate(years):
            val = by_year[yr]
            bar_h = max(2, (val / max_val) * bar_max_h)
            bx = info_x + i * (bar_w + bar_gap)
            by = baseline - bar_h
            is_current = i == len(years) - 1
            bar_color = header_color if is_current else card_border
            parts.append(
                f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bar_w:.1f}" height="{bar_h:.1f}" rx="3" fill="{bar_color}"/>'
            )
            parts.append(
                f'<text x="{bx + bar_w / 2:.1f}" y="{by - 6:.1f}" fill="{label_color}" '
                f'font-size="10" text-anchor="middle">{val}</text>'
            )
            parts.append(
                f'<text x="{bx + bar_w / 2:.1f}" y="{baseline + 16:.1f}" fill="{label_color}" '
                f'font-size="10" text-anchor="middle">{str(yr)[2:]}</text>'
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
