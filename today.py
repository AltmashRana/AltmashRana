#!/usr/bin/env python3
"""Fetch GitHub stats for the profile owner and regenerate the theme-aware SVG cards.

Designed to be cheap and robust:
- Exactly 2 GraphQL calls per run, regardless of account age or repo count
  (one for profile/repo aggregates, one multi-year aliased query for all-time
  commit/PR/issue totals) - well under GitHub's rate limits.
- No per-repo cloning or line-of-code counting (the expensive part of similar
  scripts) - just aggregate counts the GraphQL API already tracks.
- Retries transient network failures; exits non-zero on real failure instead
  of silently committing bad/partial data.
- Relies on `git diff` in the workflow to skip commits when nothing changed.
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone

USERNAME = os.environ["USER_NAME"]
TOKEN = os.environ["ACCESS_TOKEN"]
API_URL = "https://api.github.com/graphql"


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
        repositories(first: 100, ownerAffiliation: OWNER, isFork: false, privacy: PUBLIC) {{
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
            repositories(first: 100, after: "{cursor}", ownerAffiliation: OWNER, isFork: false, privacy: PUBLIC) {{
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


def render_svg(stats: dict, dark: bool) -> str:
    bg = "#0d1117" if dark else "#ffffff"
    border = "#30363d" if dark else "#e1e4e8"
    title_color = "#58a6ff" if dark else "#0969da"
    text_color = "#c9d1d9" if dark else "#24292f"
    label_color = "#8b949e" if dark else "#57606a"

    rows = [
        ("⭐ Total Stars", stats["stars"]),
        ("📦 Public Repos", stats["public_repos"]),
        ("✅ Total Commits", stats["commits"]),
        ("🔀 Pull Requests", stats["prs"]),
        ("🐛 Issues", stats["issues"]),
        ("👥 Followers", stats["followers"]),
    ]

    row_height = 30
    top_padding = 65
    height = top_padding + row_height * len(rows) + 20
    width = 380

    row_svgs = []
    for i, (label, value) in enumerate(rows):
        y = top_padding + i * row_height
        row_svgs.append(f"""
          <text x="30" y="{y}" fill="{label_color}" font-size="14">{label}</text>
          <text x="{width - 30}" y="{y}" fill="{text_color}" font-size="14" font-weight="600" text-anchor="end">{value}</text>
        """)

    return f"""<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" font-family="'Segoe UI', Ubuntu, Sans-Serif">
  <rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="6" fill="{bg}" stroke="{border}"/>
  <text x="30" y="35" fill="{title_color}" font-size="18" font-weight="600">{stats['name']}'s GitHub Stats</text>
  {''.join(row_svgs)}
</svg>"""


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
