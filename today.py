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
        repositories(first: 100, ownerAffiliations: [OWNER], isFork: false, privacy: PUBLIC) {{
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
            repositories(first: 100, after: "{cursor}", ownerAffiliations: [OWNER], isFork: false, privacy: PUBLIC) {{
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
    for year_data in data.values():
        c = year_data["contributionsCollection"]
        commits += c["totalCommitContributions"]
        prs += c["totalPullRequestContributions"]
        issues += c["totalIssueContributions"]
    return {"commits": commits, "prs": prs, "issues": issues}


def dotted_row(label: str, value: str, col: int) -> tuple:
    prefix = f".{label}:"
    pad = max(2, col - len(prefix))
    return prefix, "." * pad, str(value)


def section_row(title: str, col: int) -> str:
    text = f"- {title} "
    return text + "-" * max(2, col - len(text))


def build_info_rows(stats: dict) -> list:
    col = 34
    rows = [
        ("header", HEADER),
        ("rule", col + 10),
        ("blank", None),
        ("section", section_row("GitHub Stats", col + 10)),
    ]
    for label, value in [
        ("Repos", stats["public_repos"]),
        ("Stars", stats["stars"]),
        ("Commits", stats["commits"]),
        ("Pull Requests", stats["prs"]),
        ("Issues", stats["issues"]),
        ("Followers", stats["followers"]),
    ]:
        rows.append(("dotted", dotted_row(label, value, col)))
    return rows


def render_svg(stats: dict, dark: bool) -> str:
    bg = "#0d1117" if dark else "#ffffff"
    border = "#30363d" if dark else "#e1e4e8"
    header_color = "#58a6ff" if dark else "#0969da"
    section_color = "#e3b341" if dark else "#9a6700"
    label_color = "#c9d1d9" if dark else "#24292f"
    dot_color = "#484f58" if dark else "#8c959f"
    value_color = "#79c0ff" if dark else "#0969da"
    art_color = "#c9d1d9" if dark else "#24292f"

    art_lines = ASCII_ART_DARK if dark else ASCII_ART_LIGHT
    art_font, art_lh, art_char_w = 6, 7, 3.6
    info_font, info_lh, info_char_w = 13, 20, 7.8

    art_width = max(len(l) for l in art_lines) * art_char_w
    art_height = len(art_lines) * art_lh

    info_rows = build_info_rows(stats)
    info_width = 0
    for kind, payload in info_rows:
        if kind == "header":
            info_width = max(info_width, len(payload) * info_char_w)
        elif kind == "rule":
            info_width = max(info_width, payload * info_char_w)
        elif kind == "section":
            info_width = max(info_width, len(payload) * info_char_w)
        elif kind == "dotted":
            prefix, dots, value = payload
            info_width = max(info_width, (len(prefix) + len(dots) + 1 + len(value)) * info_char_w)
    info_height = len(info_rows) * info_lh

    pad = 24
    gap = 36
    art_panel_h = art_height + 2 * pad
    info_panel_h = info_height + 2 * pad
    height = max(art_panel_h, info_panel_h)
    art_x = pad
    info_x = pad + art_width + gap + pad
    width = info_x + info_width + pad

    parts = [
        f'<svg width="{width:.0f}" height="{height:.0f}" viewBox="0 0 {width:.0f} {height:.0f}" '
        f'xmlns="http://www.w3.org/2000/svg" font-family="SFMono-Regular, Consolas, '
        f'\'Liberation Mono\', Menlo, monospace">',
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
    y = info_y0
    for kind, payload in info_rows:
        y += info_lh
        if kind == "blank":
            continue
        if kind == "header":
            parts.append(
                f'<text x="{info_x:.0f}" y="{y:.0f}" fill="{header_color}" '
                f'font-size="{info_font}" font-weight="700" {tl(len(payload), info_char_w)}>'
                f'{escape(payload)}</text>'
            )
        elif kind == "rule":
            rule_text = "─" * payload
            parts.append(
                f'<text x="{info_x:.0f}" y="{y:.0f}" fill="{dot_color}" '
                f'font-size="{info_font}" {tl(payload, info_char_w)}>{rule_text}</text>'
            )
        elif kind == "section":
            parts.append(
                f'<text x="{info_x:.0f}" y="{y:.0f}" fill="{section_color}" '
                f'font-size="{info_font}" font-weight="700" {tl(len(payload), info_char_w)}>'
                f'{escape(payload)}</text>'
            )
        elif kind == "dotted":
            prefix, dots, value = payload
            value_text = f" {value}"
            parts.append(
                f'<text x="{info_x:.0f}" y="{y:.0f}" font-size="{info_font}">'
                f'<tspan fill="{label_color}" {tl(len(prefix), info_char_w)}>{escape(prefix)}</tspan>'
                f'<tspan fill="{dot_color}" {tl(len(dots), info_char_w)}>{escape(dots)}</tspan>'
                f'<tspan fill="{value_color}" {tl(len(value_text), info_char_w)}>{escape(value_text)}</tspan>'
                f'</text>'
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
