"""Prompt construction and fallback template generator for AI listening reports."""

import json

SYSTEM_INSTRUCTION = (
    "You are an observant, objective musicologist conducting ongoing fieldwork on modern digital "
    "listening behavior. Your writing style is minimalist, clean, and analytical—resembling an "
    "observant field notebook or a scientific journal entry. Maintain an objective eye with "
    "discerning, thoughtful aesthetic commentary when warranted. Avoid hype, flowery marketing "
    "buzzwords, and sterile corporate language. Format strictly in GitHub Flavored Markdown."
)


def build_report_prompt(context: dict) -> str:
    """Constructs the prompt for Gemini Flash based on the aggregated context."""
    cadence = context["cadence"]
    period_label = context["period_label"]
    telemetry = context["telemetry"]
    radar = context["radar_candidates"]

    # Compact JSON representation of raw data
    data_summary = {
        "cadence": cadence,
        "period": period_label,
        "telemetry": telemetry,
        "radar_candidates": radar,
    }
    raw_json = json.dumps(data_summary, indent=2)

    prompt = f"""{SYSTEM_INSTRUCTION}

You are generating a {cadence.upper()} report for the period: {period_label}.

Here is the structured telemetry and recommendation candidates extracted from the user's YouTube Music database:
```json
{raw_json}
```

Instructions for the report structure:
"""

    if cadence == "daily":
        prompt += f"""
Produce a report in the following Markdown structure:
# 🎧 Daily Listening Log: {period_label}
*Recorded via ytm-dl | Cadence: Daily Observation*

## 1. Session Telemetry
- Total Tracks Observed: {telemetry["total_tracks"]}
- Auditory Duration: {telemetry["total_duration_display"]}
- Unique Artists: {telemetry["unique_artists_count"]}
- Library Ratio: {telemetry["library_ratio_pct"]}% library tracks
- Temporal Distribution: Morning ({telemetry["temporal_distribution"]["morning"]}), Afternoon ({telemetry["temporal_distribution"]["afternoon"]}), Evening ({telemetry["temporal_distribution"]["evening"]}), Night ({telemetry["temporal_distribution"]["night"]})

## 2. Musicological Notes
[Provide 2-3 focused paragraphs analyzing the listening session. Discuss pacing, live vs studio versions, repeat loops, and the sonic continuity of the session. If the session has 0 plays, briefly note an inactive observation period.]

## 3. Algorithmic Suggestions Radar
[Evaluate 3 to 5 candidate tracks from the provided radar_candidates list. Cross-reference them against what the user listened to today. Present as a markdown table with columns: Track | Artist | Shelf Source | Prior Impressions | Musicologist Appraisal. The appraisal should explain objectively why this recommendation fits or contrasts with today's listening session.]
"""
    elif cadence == "weekly":
        prompt += f"""
Produce a report in the following Markdown structure:
# 📈 Weekly Sonic Digest: {period_label}

## 1. Macro Analysis
- Cumulative Volume: {telemetry["total_tracks"]} plays across {telemetry["total_duration_display"]}
- Unique Artists: {telemetry["unique_artists_count"]}
- Top Artists: List top 3-5 artists by play count
- Library Ratio: {telemetry["library_ratio_pct"]}%

## 2. Genre & Texture Distribution
[Estimate and summarize the primary sonic genres and textures observed across the week based on the artist roster.]

## 3. The Replay Loop & New Catalog Additions
- Replays: Mention notable repeat tracks (if any from repeat_tracks)
- Liked Songs: List any newly added likes from the week

## 4. Algorithmic Hit Rate & Discovery Queue
[Audit the recommendation shelves. Highlight 3-5 of the highest priority suggestions from the radar_candidates that warrant a listen during the upcoming weekend, noting their shelf source and a concise appraisal.]
"""
    elif cadence == "monthly":
        prompt += f"""
Produce a report in the following Markdown structure:
# 📜 Monthly Retrospective: {period_label}

## 1. Month in Review
- Total Volume: {telemetry["total_tracks"]} plays ({telemetry["total_duration_display"]})
- Artist Breadth: {telemetry["unique_artists_count"]} distinct artists, {telemetry["unique_albums_count"]} albums
- Top Artists: Top 5 artists by volume

## 2. Sonic Cartography & Macro Shifts
[A deep-dive musicological essay on the dominant themes, artist rabbit holes, live performance explorations, and tonal shifts observed over the course of the month.]

## 3. Curated Archive Playlist: {period_label}
[Construct an AI-curated 10-track thematic retrospective playlist inspired by the month's listening. List Track, Artist, and a 1-sentence liner note for each selection.]
"""

    return prompt.strip()


def generate_fallback_report(context: dict) -> str:
    """
    Generates a high-quality deterministic Markdown report when GEMINI is unavailable.
    Guarantees that telemetry and radar candidates are always saved without crashing.
    """
    cadence = context["cadence"]
    period_label = context["period_label"]
    t = context["telemetry"]
    radar = context["radar_candidates"]

    lines = []
    if cadence == "daily":
        lines.append(f"# 🎧 Daily Listening Log: {period_label}")
        lines.append("*Recorded via ytm-dl | Cadence: Daily Observation*\n")
        lines.append("## 1. Session Telemetry")
        lines.append(f"- **Total Tracks Observed**: {t['total_tracks']}")
        lines.append(f"- **Auditory Duration**: {t['total_duration_display']}")
        lines.append(f"- **Unique Artists**: {t['unique_artists_count']}")
        lines.append(f"- **Library Ratio**: {t['library_ratio_pct']}%")
        lines.append(
            f"- **Temporal Windows**: Morning: {t['temporal_distribution']['morning']} | "
            f"Afternoon: {t['temporal_distribution']['afternoon']} | "
            f"Evening: {t['temporal_distribution']['evening']} | "
            f"Night: {t['temporal_distribution']['night']}\n"
        )

        lines.append("## 2. Musicological Notes")
        if t["total_tracks"] > 0:
            top_artist = t["top_artists"][0]["artist"] if t["top_artists"] else "Various Artists"
            lines.append(
                f"Session activity centered predominantly around **{top_artist}** with "
                f"{t['unique_artists_count']} distinct artists logged across "
                f"{t['total_duration_display']} of playback."
            )
            if t["repeat_tracks"]:
                repeats_str = ", ".join(
                    f"*{r['title']}* ({r['count']}x)" for r in t["repeat_tracks"][:3]
                )
                lines.append(f"\nRepeat loops detected: {repeats_str}.")
        else:
            lines.append("No playback sessions recorded during this observation window.")
        lines.append("")

        lines.append("## 3. Algorithmic Suggestions Radar")
        if radar:
            lines.append("| Track | Artist | Shelf Source | Impressions | Position | Status |")
            lines.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
            for c in radar[:5]:
                status = "✨ New Arrival" if c["is_new"] else "🔁 Recurring"
                lines.append(
                    f"| {c['title']} | {c['artists']} | `{c['shelf']}` | "
                    f"{c['times_recommended']}x | #{c['latest_position']} | {status} |"
                )
        else:
            lines.append("No fresh shelf suggestions detected for this period.")

    elif cadence == "weekly":
        lines.append(f"# 📈 Weekly Sonic Digest: {period_label}\n")
        lines.append("## 1. Macro Analysis")
        lines.append(
            f"- **Cumulative Volume**: {t['total_tracks']} plays ({t['total_duration_display']})"
        )
        lines.append(f"- **Distinct Artists**: {t['unique_artists_count']}")
        lines.append(f"- **Library Ratio**: {t['library_ratio_pct']}%\n")

        lines.append("## 2. Top Rotations")
        for a in t["top_artists"][:5]:
            lines.append(f"- **{a['artist']}**: {a['count']} plays")
        lines.append("")

        lines.append("## 3. Algorithmic Suggestions Radar")
        if radar:
            lines.append("| Track | Artist | Shelf Source | Impressions |")
            lines.append("| :--- | :--- | :--- | :--- |")
            for c in radar[:5]:
                lines.append(
                    f"| {c['title']} | {c['artists']} | `{c['shelf']}` | {c['times_recommended']}x |"
                )
        else:
            lines.append("No active recommendations captured.")

    elif cadence == "monthly":
        lines.append(f"# 📜 Monthly Retrospective: {period_label}\n")
        lines.append("## 1. Month in Review")
        lines.append(f"- **Total Plays**: {t['total_tracks']} ({t['total_duration_display']})")
        lines.append(
            f"- **Catalog Breadth**: {t['unique_artists_count']} artists, {t['unique_albums_count']} albums\n"
        )

        lines.append("## 2. Top Artists")
        for a in t["top_artists"][:10]:
            lines.append(f"- **{a['artist']}**: {a['count']} plays")
        lines.append("")

        lines.append("## 3. Algorithmic Suggestions Radar")
        if radar:
            lines.append("| Track | Artist | Shelf Source | Impressions |")
            lines.append("| :--- | :--- | :--- | :--- |")
            for c in radar[:8]:
                lines.append(
                    f"| {c['title']} | {c['artists']} | `{c['shelf']}` | {c['times_recommended']}x |"
                )

    return "\n".join(lines).strip() + "\n"
