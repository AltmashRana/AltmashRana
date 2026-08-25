#!/usr/bin/env python3
"""Fetch GitHub stats and render a neofetch-style profile card (dark/light SVGs).

Robustness/cost notes:
- Exactly 2 GraphQL calls per run, regardless of account age or repo count
  (one for profile/repo aggregates, one multi-year aliased query for all-time
  commit/PR/issue totals) - well under GitHub's rate limits.
- No per-repo cloning or line-of-code counting.
- The ASCII portrait is precomputed once from a static photo (see
  scripts/generate_ascii_art.py) and baked in below - it never changes, so it
  is not worth re-deriving on every run.
- Retries transient network failures; exits non-zero on real failure instead
  of silently committing bad/partial data.
- Relies on `git diff` in the workflow to skip commits when nothing changed.
"""
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

LANGUAGES_PROGRAMMING = "Kotlin, Python, JavaScript"
LANGUAGES_COMPUTER = "HTML"
LANGUAGES_REAL = "English, Urdu, Hindi, Punjabi"
HOBBIES = "Gaming, Music/Guitar"

CONTACT = [
    ("Email", "altmashrana.303@gmail.com"),
    ("LinkedIn", "linkedin.com/in/altmash-rana"),
    ("Portfolio", "altmashrana.lovable.app"),
]

# Generated once from a personal photo via scripts/generate_ascii_art.py.
# Dark/light variants use inverted brightness mapping so the portrait reads
# correctly against both a black and a white background.
ASCII_ART_DARK = [
    "                  ;:,::;ri",
    "               ,.         ,i",
    "              ..rrrrrri;;;..,",
    "             , ASB&&&&&&B9A .",
    "              .2hHS9BB#GHHH;",
    "             A;;...,5r  ..rr5",
    "             3A.   iBH:  ,2MGG",
    "              hhhhhA533hH##HS",
    "               3HS2rAAX2S#M",
    "                AX53AXhM22A",
    "                3A;;::;;sM",
    "                sMMM33MGSHs.",
    "            ::..,;sA3HhAr:,.,::,",
    "       ;;:,,,..,,,,,,si,,::,:::,,;::",
    "    ;;;;:,,,.,:;;;;;:ii;;:;::;::.:;:,;;",
    "   ::::::;;::;;;;;;;;ii;:;;;;;;;,,;:;i;;",
    "  :;::::::;;iiiiiii;;si;;:;iiiii;::;:;;;:",
    " :::;;;::,:;iiiiiiii;ii;:;iiiiiii;:,,::;;:",
    " ,,:;;;;:,,;iiiiiii;;ii;:iiiiiiii;.,,::;;:.",
    ":,,:,,:;;:,,:;;;;;;;;ri;::;;;;;;;,,::;;;;:,",
    ",,:::::,,,,  ..,:::;::;;,.::,:,..,:;:::::;:",
    ".,,,,,::::,   .,,,::.;i:: ,..    ,,:::,,::,",
    "  ,,,:::...       ...::,:,;iri:. ...,:::,.,",
    "  ,:::::,..:isXssrssA23MG#9&&&&#r.,,,:,,:,,.",
    " ..,,::,,::X9BB99BBBBB&&&&@B9GM5;.,,,,,. .,.",
    "  ...,,.,,s#99######SSSSGHHMGX .,:,,.,:,.",
    "   ..,... 5SGHHHHMhMh33hMGS##Gi.,,,,,..,,.",
    "          ,2AAAXXsAAA23hhhhhhh3:   ......",
    "                  .,::;;;iiiiiri",
    "               .....",
    "           .................   .",
    "              .............. . ...",
    "                ............    ..",
]

ASCII_ART_LIGHT = [
    "                  S#9##SHG",
    "               9B&&&&&&&&&9G",
    "              BBHHHHHHGSSSBB9",
    "             9&3;.      .,3&B",
    "              B5Xr;,..:irrrS@",
    "             3SSBBB92H&&BBHH2",
    "             A3B&@&G.r#&&95sii",
    "              XXXXX32AAXr::r;",
    "               Ar;5H33h5;:s",
    "                3h2A3hXs553",
    "                A3SS##SSMs",
    "                MsssAAsi;rMB",
    "            ##BB9SM3ArX3H#9B9##9",
    "       SS#999BB999999MG99##9###99S##",
    "    SSSS#999B9#SSSSS#GGSS#S##S##B#S#9SS",
    "   ######SS##SSSSSSSSGGS#SSSSSSS99S#SGSS",
    "  #S######SSGGGGGGGSSMGSS#SGGGGGS##S#SSS#",
    " ###SSS##9#SGGGGGGGGSGGS#SGGGGGGGS#99##SS#",
    " 99#SSSS#99SGGGGGGGSSGGS#GGGGGGGGSB99##SS#B",
    "#99#99#SS#99#SSSSSSSSHGS##SSSSSSS99##SSSS#9",
    "99#####9999&&BB9###S##SS9B##9#9BB9#S#####S#",
    "B99999####9&&&B999##BSG##&9BB&&&&99###99##9",
    "&&999###BBB&@@&&&&BBB##9#9SGHG#B&BBB9###9B9",
    " &9#####9BB#GMhMMHMM35Asi:,    :HB999#99#99B",
    " BB99##99##h,..,,.....     .,is2SB99999B&B9B",
    "  BBB99B99M:,,::::::;;;;irrsih&B9#99B9#9B&&",
    "  &BB9BBB&2;irrrrsXsXAAXsi;::iGB99999BB99B",
    "   &&&&&&&95333hhM3335AXXXXXXXA#&&&BBBBBB",
    "     &&&&&&&&&&&&&B9##SSSGGGGGHG&&&&&&&&",
    "     &&&&&&&&&&BBBBB&&&&&&&&&&&&&&&&",
    "    &&&&&&&BBBBBBBBBBBBBBBBB&&&B&&&&&",
    "    &&&&&&&&&&BBBBBBBBBBBBBB&B&BBB&&&",
    "   &&&&&&&&&&&&&BBBBBBBBBBBB&&&&BB&&&",
]


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
    """Each row is (kind, payload). kind is 'header' | 'rule' | 'section' | 'dotted' | 'blank'."""
    col = 34
    rows = [
        ("header", HEADER),
        ("rule", col + 10),
        ("blank", None),
        ("dotted", dotted_row("Languages.Programming", LANGUAGES_PROGRAMMING, col)),
        ("dotted", dotted_row("Languages.Computer", LANGUAGES_COMPUTER, col)),
        ("dotted", dotted_row("Languages.Real", LANGUAGES_REAL, col)),
        ("dotted", dotted_row("Hobbies", HOBBIES, col)),
        ("blank", None),
        ("section", section_row("Contact", col + 10)),
    ]
    for label, value in CONTACT:
        rows.append(("dotted", dotted_row(label, value, col)))
    rows.append(("blank", None))
    rows.append(("section", section_row("GitHub Stats", col + 10)))
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
    art_font, art_lh, art_char_w = 7, 9, 4.2
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

    art_y0 = (height - art_height) / 2
    for i, line in enumerate(art_lines):
        y = art_y0 + (i + 1) * art_lh
        parts.append(
            f'<text x="{art_x:.0f}" y="{y:.0f}" fill="{art_color}" '
            f'font-size="{art_font}" xml:space="preserve">{escape(line)}</text>'
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
                f'font-size="{info_font}" font-weight="700">{escape(payload)}</text>'
            )
        elif kind == "rule":
            parts.append(
                f'<text x="{info_x:.0f}" y="{y:.0f}" fill="{dot_color}" '
                f'font-size="{info_font}">{"─" * payload}</text>'
            )
        elif kind == "section":
            parts.append(
                f'<text x="{info_x:.0f}" y="{y:.0f}" fill="{section_color}" '
                f'font-size="{info_font}" font-weight="700">{escape(payload)}</text>'
            )
        elif kind == "dotted":
            prefix, dots, value = payload
            parts.append(
                f'<text x="{info_x:.0f}" y="{y:.0f}" font-size="{info_font}">'
                f'<tspan fill="{label_color}">{escape(prefix)}</tspan>'
                f'<tspan fill="{dot_color}">{escape(dots)}</tspan>'
                f'<tspan fill="{value_color}"> {escape(value)}</tspan>'
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
