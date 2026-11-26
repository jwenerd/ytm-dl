"""Prompt construction and fallback template generator for Crate-Digger listening reports."""

import json

SYSTEM_INSTRUCTION = (
    "You are a sharp, warm record-store clerk and seasoned crate-digger writing an editorial "
    "listening zine for a regular with deep, eclectic taste. Your voice is knowledgeable, "
    "conversational, and rich with real musical context—band-member crossovers, studio/label "
    "lineage, release years, sample connections, and why a groove hits. Avoid dry academic "
    "jargon and corporate filler, and never use markdown tables. Copy all YouTube Music URLs "
    "verbatim from the provided JSON so every recommended track, album, and set is a clickable "
    "Markdown link. Format strictly in GitHub Flavored Markdown."
)


def _format_md_link(title: str, url: str | None) -> str:
    """Formats a bold clickable Markdown link if a URL is present, else bold title."""
    clean_title = title.replace("[", "(").replace("]", ")")
    return f"**[{clean_title}]({url})**" if url else f"**{title}**"


def build_report_prompt(context: dict) -> str:
    """Constructs the Crate-Digger prompt for Gemini Flash based on aggregated context."""
    cadence = context["cadence"].lower()
    period_label = context["period_label"]
    t = context["telemetry"]
    radar = context.get("radar_candidates") or []
    forgotten = context.get("forgotten_candidates") or []
    long_form = context.get("long_form_picks") or {"albums": [], "long_sets": []}
    milestones = context.get("milestones") or []
    obsessions = context.get("obsessions") or {}
    has_obsessions = any(
        obsessions.get(k)
        for k in ("tracks_on_repeat", "artist_signals", "album_binges", "taste_phases")
    )

    data_summary = {
        "cadence": cadence,
        "period": period_label,
        "telemetry": t,
        "radar_candidates": radar,
        "forgotten_candidates": forgotten,
        "long_form_picks": long_form,
    }
    if milestones:
        data_summary["milestones"] = milestones
    if has_obsessions:
        data_summary["obsessions"] = obsessions
    raw_json = json.dumps(data_summary, indent=2)

    stats_line = (
        f"- **Stats**: {t['total_tracks']} plays · {t['total_duration_display']} · "
        f"{t['unique_artists_count']} artists · {t.get('new_artists_count', 0)} new artists"
    )

    heading_map = {
        "daily": (
            f"# Daily Listening Log: {period_label}",
            "*Recorded via ytm-dl | Crate-Digger Daily*",
            "3 to 4",
            "2 to 3",
            (
                "Target roughly 260 to 340 words total (or ~140 words if total_tracks < 5): "
                "scannable sections, lively callout boxes, and handwritten record-bin style blurbs."
            ),
        ),
        "weekly": (
            f"# Weekly Crate Digest: {period_label}",
            "*Recorded via ytm-dl | Crate-Digger Weekly*",
            "4 to 5",
            "3",
            (
                "Target roughly 350 to 450 words total: conversational behind-the-counter recap, "
                "3 rich callout boxes, and 2-sentence staff-pick cards."
            ),
        ),
        "monthly": (
            f"# Monthly Crate Retrospective: {period_label}",
            "*Recorded via ytm-dl | Crate-Digger Monthly*",
            "5 to 6",
            "3 to 4",
            (
                "Target roughly 420 to 550 words total: retrospective zine opener, "
                "3 to 4 deep callout boxes, and 2-sentence staff-pick cards."
            ),
        ),
    }
    h1_title, subtitle, radar_count, callout_count, length_rule = heading_map.get(
        cadence, heading_map["daily"]
    )

    radar_heading = "## Today's Radar" if cadence == "daily" else "## Radar Picks"

    prompt = f"""{SYSTEM_INSTRUCTION}

You are generating a {cadence.upper()} listening zine issue for: {period_label}.
{length_rule}

Structured listening data and candidate shelves:
```json
{raw_json}
```

Output MUST follow this exact Markdown layout (no extra H2 sections, no markdown tables):

{h1_title}
{subtitle}

{stats_line}

**The Spin:** [1 punchy editorial headline sentence (12–20 words) capturing the day's core groove, arc, or genre swerve—this renders as the big masthead headline.]

[Behind the Counter Opener: 2 to 3 warm, conversational sentences unpacking how the session actually flowed—who anchored the turntable, how the mood shifted across the session, and what gave it personality.]

## On the Turntable
- **Heavy Rotation:** [List top 4–6 artists with play counts, e.g. Octave Cat (14) · The Disco Biscuits (4) · Waylon Jennings (2).]
- **First-Time Spins:** [Include if `new_artists` is non-empty: name 3–5 standout first-time artists discovered in this window.]
- **Fresh Likes:** [Include ONLY if `new_likes` is non-empty: list up to 4 newly liked tracks as clickable **[Title](url)** — Artist links.]

[Include {callout_count} distinct Markdown blockquote callout cards (`> `), each 2 to 3 lively sentences (35–55 words each), picking the best angles from today's data such as:
- `> **🔗 Lineage & Personnel:** ...` (Band-member crossovers, side projects, shared producers/labels, or historical roots linking artists in the session)
- `> **⚡ Double-Take / Hard Left Turn:** ...` (Cover/standard `version_collisions`, wild genre whiplash, or repeat earworms)
- `> **🌱 First-Timer Spotlight:** ...` (Quick record-clerk intro to the coolest brand-new artist in `new_artists`)
- `> **📼 Tape & Soundtrack Check:** ...` (Concert bootleg dates/venues, live jams, or soundtrack/album deep dives)
- `> **🏅 Milestones & Obsessions:** ...` (Highlight any newly crossed `milestones` or active `obsessions` surges/loops in this window, if present)
Separate each blockquote card with a blank line!]

{radar_heading}
[Pick {radar_count} standout tracks from `radar_candidates`. Write each as a 2-sentence (~20–32 word) handwritten record-bin staff-pick card using its exact `url` from JSON:]
- **[Track Title](url)** — Artist — *[Sentence 1: What it sounds like—instruments, era/city, label or album vibe. Sentence 2: Exact thread connecting or contrasting it with today's spin.]*

## Deep Cuts & Long Spins
- **Liked & Forgotten:** **[Track Title](url)** — Artist — *[Pick 1 gem from `forgotten_candidates`; 2 sentences (~22–32 words) weaving in when they liked/last spun it (`note`) + why its sound deserves a fresh spin right now. Omit ONLY if `forgotten_candidates` is empty.]*
- **Full Album:** **[Album Title](url)** — Artist — *[Pick 1 LP from `long_form_picks.albums`; 2 sentences (~20–30 words) pitching why this record rewards a front-to-back listen. Omit ONLY if `albums` is empty.]*
- **Long Spin:** **[Set/Show Title](url)** — Artist — *[Pick 1 full show/set from `long_form_picks.long_sets`; 2 sentences (~20–30 words) setting the scene for this concert or extended mix. Omit ONLY if `long_sets` is empty.]*
"""
    return prompt.strip()


def generate_fallback_report(context: dict) -> str:
    """
    Generates a deterministic Crate-Digger Markdown report when Gemini is unavailable.
    Includes opener, blockquote callout cards, and clickable picks.
    """
    cadence = context["cadence"].lower()
    period_label = context["period_label"]
    t = context["telemetry"]
    radar = context.get("radar_candidates") or []
    forgotten = context.get("forgotten_candidates") or []
    long_form = context.get("long_form_picks") or {"albums": [], "long_sets": []}

    title_map = {
        "daily": (
            f"# Daily Listening Log: {period_label}",
            "*Recorded via ytm-dl | Crate-Digger Daily*",
            "## Today's Radar",
            4,
        ),
        "weekly": (
            f"# Weekly Crate Digest: {period_label}",
            "*Recorded via ytm-dl | Crate-Digger Weekly*",
            "## Radar Picks",
            5,
        ),
        "monthly": (
            f"# Monthly Crate Retrospective: {period_label}",
            "*Recorded via ytm-dl | Crate-Digger Monthly*",
            "## Radar Picks",
            6,
        ),
    }
    h1_title, subtitle, radar_heading, radar_limit = title_map.get(cadence, title_map["daily"])

    lines = [
        h1_title,
        subtitle,
        "",
        (
            f"- **Stats**: {t['total_tracks']} plays · {t['total_duration_display']} · "
            f"{t['unique_artists_count']} artists · {t.get('new_artists_count', 0)} new artists"
        ),
        "",
    ]

    if t["total_tracks"] > 0:
        top_artist = t["top_artists"][0]["artist"] if t.get("top_artists") else "eclectic cuts"
        lines.append(
            f"**The Spin:** {t['total_duration_display']} of crate-digging across {t['unique_artists_count']} artists, anchored heavily by {top_artist}."
        )
        lines.append("")
        lines.append(
            f"A lively {t['total_tracks']}-track run kept the turntable warm for {t['total_duration_display']}, "
            f"with **{top_artist}** setting the central groove while {t.get('new_artists_count', 0)} first-time artists entered the catalog."
        )
    else:
        lines.append(
            "**The Spin:** Quiet turntable—no spins logged during this observation window."
        )
    lines.append("")

    lines.append("## On the Turntable")
    if t.get("top_artists"):
        anchors = " · ".join(f"{a['artist']} ({a['count']})" for a in t["top_artists"][:5])
        lines.append(f"- **Heavy Rotation:** {anchors}")
    else:
        lines.append("- **Heavy Rotation:** No active rotation recorded.")

    if t.get("new_artists"):
        first_timers = ", ".join(t["new_artists"][:5])
        lines.append(f"- **First-Time Spins:** {first_timers}")

    if t.get("new_likes"):
        likes_str = " · ".join(
            f"{_format_md_link(lk['title'], lk.get('url'))} — {lk['artist']}"
            for lk in t["new_likes"][:4]
        )
        lines.append(f"- **Fresh Likes:** {likes_str}")
    lines.append("")

    collisions = t.get("version_collisions") or []
    if collisions:
        col = collisions[0]
        lines.append(
            f"> **⚡ Double-Take — Same Song, Different Hands:** Caught multiple versions of *{col['title']}* "
            f"in the same window ({' vs. '.join(col['artists'][:3])}), putting distinct arrangements side by side."
        )
        lines.append("")
    if t.get("repeat_tracks"):
        rep = t["repeat_tracks"][0]
        lines.append(
            f"> **🔁 Heavy Replay:** {_format_md_link(rep['title'], rep.get('url'))} by {rep['artist']} "
            f"pulled {rep['count']} spins, acting as the recurring anchor cut of the session."
        )
        lines.append("")
    elif t.get("live_track_count", 0) > 0:
        lines.append(
            f"> **📼 Tape & Stage Check:** {t['live_track_count']} live concert or archival stage recordings "
            f"cut through the studio queue, keeping improvisational energy in the mix."
        )
        lines.append("")

    milestones = context.get("milestones") or []
    if milestones:
        ms = milestones[0]
        lines.append(
            f"> **🏅 Milestone Unlocked:** {ms['entity']} crossed {int(ms['threshold']):,} "
            f"({ms['category'].replace('_', ' ')}) on {ms['date']}."
        )
        lines.append("")

    lines.append(radar_heading)
    if radar:
        for c in radar[:radar_limit]:
            badge = (
                "Fresh arrival"
                if c.get("is_new")
                else f"Recurring `{c.get('shelf', 'radar')}` standout"
            )
            lines.append(
                f"- {_format_md_link(c['title'], c.get('url'))} — {c['artists']} — *{badge} sitting at #{c.get('latest_position', 1)} on your shelves, queued up as a natural companion to this session's palette.*"
            )
    else:
        lines.append("- No fresh radar tracks queued for this period.")
    lines.append("")

    albums = long_form.get("albums") or []
    long_sets = long_form.get("long_sets") or []
    if forgotten or albums or long_sets:
        lines.append("## Deep Cuts & Long Spins")
        if forgotten:
            fg = forgotten[0]
            lines.append(
                f"- **Liked & Forgotten:** {_format_md_link(fg['title'], fg.get('url'))} — {fg['artists']} — *{fg.get('note', 'Buried in the crates')}—well worth pulling back onto the platter today.*"
            )
        if albums:
            alb = albums[0]
            lines.append(
                f"- **Full Album:** {_format_md_link(alb['title'], alb.get('url'))} — {alb['artists']} — *Pulled from your album shelf for an uninterrupted, front-to-back LP listen.*"
            )
        if long_sets:
            ls = long_sets[0]
            lines.append(
                f"- **Long Spin:** {_format_md_link(ls['title'], ls.get('url'))} — {ls['artists']} — *Extended live session or mix ready when you want one long continuous groove.*"
            )

    return "\n".join(lines).strip() + "\n"
