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
        anchor_info = (
            f"- Catalog Anchor: {telemetry['catalog_anchor']}\n"
            if telemetry.get("catalog_anchor")
            else ""
        )
        prompt += f"""
Produce a report in the following Markdown structure:
# 🎧 Daily Listening Log: {period_label}
*Recorded via ytm-dl | Cadence: Daily Observation*

## 1. Session Telemetry
- Total Tracks Observed: {telemetry["total_tracks"]}
- Auditory Duration: {telemetry["total_duration_display"]}
- Unique Artists: {telemetry["unique_artists_count"]} ({telemetry["unique_albums_count"]} albums)
{anchor_info}- Library Ratio: {telemetry["library_ratio_pct"]}% library tracks

## 2. Musicological Notes
### Field Observations
[Provide 3 to 4 concise bullet points highlighting key session facts. Each bullet MUST start with a bold label like **Primary Anchor**, **Harmonic Texture**, **Pacing & Transitions**, or **Anomalies & Drift**.]

### Narrative Synthesis
[Provide 1 to 2 focused, tightly written paragraphs synthesizing the listening session. Keep it analytical, observant, and direct without unnecessary wordiness. If the session has 0 plays, briefly note an inactive observation period.]

## 3. Dynamic Field Spotlight
[Dynamically select and include 1 or 2 of the following features that BEST fit today's data:
- **Sonic Texture & Timbre**: (Dominant instrumentation, vocal density, production era)
- **Live Archives & Performance Notes**: (If live recordings were detected, note jam duration, venue, or live vs studio dynamics)
- **Catalog Archaeology & Deep Cuts**: (Deep album cuts vs greatest hits, track sequencing)
- **Earworm / Replay Loop**: (If repeat tracks were played, analyze why that specific take was repeated)
- **Historical Field Note**: (1-2 sentence fascinating historical recording or studio trivia connecting today's artists)]

## 4. Algorithmic Suggestions Radar
[Evaluate 3 to 5 candidate tracks from the provided radar_candidates list. Cross-reference them against what the user listened to today. Present as a markdown table with columns: Track | Artist | Shelf Source | Prior Impressions | Musicologist Appraisal. The appraisal should explain objectively why this recommendation fits or contrasts with today's listening session.]
"""
    elif cadence == "weekly":
        anchor_info = (
            f"- Catalog Anchor: {telemetry['catalog_anchor']}\n"
            if telemetry.get("catalog_anchor")
            else ""
        )
        prompt += f"""
Produce a report in the following Markdown structure:
# 📈 Weekly Sonic Digest: {period_label}

## 1. Macro Analysis
- Cumulative Volume: {telemetry["total_tracks"]} plays across {telemetry["total_duration_display"]}
- Unique Artists: {telemetry["unique_artists_count"]} ({telemetry["unique_albums_count"]} albums)
{anchor_info}- Top Artists: List top 3-5 artists by play count
- Library Ratio: {telemetry["library_ratio_pct"]}%

## 2. Weekly Field Observations
[Provide 3 to 4 concise bullet points capturing the week's key shifts with bold labels like **Primary Anchor**, **Emerging Obsessions**, **Texture Range**, **Catalog Penetration**.]

## 3. Narrative Synthesis
[Provide 1 to 2 focused paragraphs analyzing the macro arc of the week, shifts between workdays and weekends, and predominant listening modes.]

## 4. Dynamic Weekly Spotlight
[Dynamically select and include 1 or 2 of the following features that BEST reflect this week's data:
- **Genre & Texture Distribution**: (Percentage breakdown of observed sonic textures and micro-genres)
- **Live Circuit & Tour Archive**: (If live recordings were prevalent, note venues, tour eras, and extended jams)
- **Catalog Archaeology & Deep Dives**: (Album-level continuity vs shuffle track hopping)
- **Earworm & Replay Loops**: (Analysis of repeated tracks across multiple sessions)
- **Weekly Historical Footnote**: (Historical studio or songwriting lineage linking the week's artists)]

## 5. Replay Loops & Catalog Additions
- Replays: Mention notable repeat tracks (if any from repeat_tracks)
- Liked Songs: List any newly added likes from the week

## 6. Algorithmic Suggestions Radar & Weekend Queue
[Audit the recommendation shelves. Highlight 3 to 5 of the highest priority suggestions from the radar_candidates that warrant a listen during the upcoming weekend. Present strictly as a markdown table with columns: Track | Artist | Shelf Source | Prior Impressions | Musicologist Appraisal. The appraisal should explain objectively why this recommendation fits or contrasts with this week's listening trends.]
"""
    elif cadence == "monthly":
        anchor_info = (
            f"- Catalog Anchor: {telemetry['catalog_anchor']}\n"
            if telemetry.get("catalog_anchor")
            else ""
        )
        likes_count = len(telemetry.get("new_likes", []))
        prompt += f"""
Produce a report in the following Markdown structure:
# 📜 Monthly Retrospective: {period_label}

## 1. Month in Review
- Total Volume: {telemetry["total_tracks"]} plays ({telemetry["total_duration_display"]})
- Artist Breadth: {telemetry["unique_artists_count"]} distinct artists, {telemetry["unique_albums_count"]} albums
{anchor_info}- Library Growth: {likes_count} new catalog likes
- Top Artists: Top 5 artists by volume

## 2. Monthly Field Observations
[Provide 4 to 5 concise bullet points capturing the month's macro shifts with bold labels like **Monthly Anchor**, **New Frontier**, **Deep Catalog Exploration**, **Soundtrack Texture**.]

## 3. Sonic Cartography & Narrative Essay
[A 2-3 paragraph deep-dive musicological essay on the dominant themes, artist rabbit holes, live performance explorations, and tonal shifts observed over the course of the month.]

## 4. Dynamic Monthly Spotlight
[Dynamically select and include 1 or 2 of the following deep-dive features based on the month's data:
- **Macro Sonic Texture Map**: (Detailed percentage breakdown of moods and styles throughout the month)
- **Comfort Zone vs Frontier Matrix**: (Core staples vs newly explored artists and genres)
- **The Month's Defining Deep Dives**: (Full albums or artist catalogs explored from start to finish)
- **Live Tapes & Tour Retrospective**: (Concert recordings, festival sets, and improvisation highlights)
- **Historical Lineage & Liner Notes**: (Broad historical essay tracing recording lineage across the month's top works)]

## 5. Algorithmic Suggestions Radar & Curated Archive Mixtape
[Evaluate 5 to 8 candidate tracks from the provided radar_candidates list to curate an archival discovery queue inspired by the month's listening. Present strictly as a markdown table with columns: Track | Artist | Shelf Source | Prior Impressions | Musicologist Appraisal. The appraisal should provide an analytical liner note explaining why this recommendation warrants inclusion based on the month's aesthetic trajectory.]
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
        lines.append(
            f"- **Unique Artists**: {t['unique_artists_count']} ({t['unique_albums_count']} albums)"
        )
        if t.get("catalog_anchor"):
            lines.append(f"- **Catalog Anchor**: {t['catalog_anchor']}")
        lines.append(f"- **Library Ratio**: {t['library_ratio_pct']}%\n")

        lines.append("## 2. Musicological Notes")
        lines.append("### Field Observations")
        if t["total_tracks"] > 0:
            top_artist = t["top_artists"][0]["artist"] if t["top_artists"] else "Various Artists"
            lines.append(
                f"- **Primary Anchor**: Centered around {top_artist} ({t['unique_artists_count']} unique artists observed)."
            )
            if t["repeat_tracks"]:
                repeats_str = ", ".join(
                    f"*{r['title']}* ({r['count']}x)" for r in t["repeat_tracks"][:3]
                )
                lines.append(f"- **Repeat Loop**: {repeats_str}.")
            if t.get("live_track_count", 0) > 0:
                lines.append(
                    f"- **Performance Mode**: {t['live_track_count']} live recordings captured."
                )
            lines.append("")
            lines.append("### Narrative Synthesis")
            lines.append(
                f"Playback centered predominantly on **{top_artist}** across "
                f"{t['total_duration_display']} of active listening."
            )
        else:
            lines.append(
                "- **Observation**: No playback sessions recorded during this observation window."
            )
        lines.append("")

        lines.append("## 3. Dynamic Field Spotlight")
        if t.get("live_track_count", 0) > 0:
            lines.append(
                f"- **Live Archive Tracking**: {t['live_track_count']} tracks logged from live concert recordings."
            )
        elif t.get("repeat_tracks"):
            lines.append(
                f"- **Earworm Analysis**: Multiple replays recorded for *{t['repeat_tracks'][0]['title']}*."
            )
        else:
            lines.append(
                "- **Sonic Timbre**: Studio catalog listening focused on studio production and album sequencing."
            )
        lines.append("")

        lines.append("## 4. Algorithmic Suggestions Radar")
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
        lines.append(
            f"- **Distinct Artists**: {t['unique_artists_count']} ({t['unique_albums_count']} albums)"
        )
        if t.get("catalog_anchor"):
            lines.append(f"- **Catalog Anchor**: {t['catalog_anchor']}")
        lines.append(f"- **Library Ratio**: {t['library_ratio_pct']}%\n")

        lines.append("## 2. Weekly Field Observations")
        if t["top_artists"]:
            lines.append(
                f"- **Primary Anchor**: {t['top_artists'][0]['artist']} ({t['top_artists'][0]['count']} plays)"
            )
        if t.get("repeat_tracks"):
            lines.append(
                f"- **Key Loops**: {', '.join(r['title'] for r in t['repeat_tracks'][:3])}"
            )
        if t.get("live_track_count", 0) > 0:
            lines.append(f"- **Live Share**: {t['live_track_count']} live recordings captured.")
        lines.append("")

        lines.append("## 3. Narrative Synthesis")
        if t["top_artists"]:
            lines.append(
                f"Weekly playback prioritized extended listening sessions dominated by **{t['top_artists'][0]['artist']}** "
                f"with exploration spanning {t['unique_artists_count']} distinct artists."
            )
        lines.append("")

        lines.append("## 4. Dynamic Weekly Spotlight")
        if t.get("live_track_count", 0) > 0:
            lines.append(
                f"- **Live Performance Spotlight**: High live recording engagement ({t['live_track_count']} tracks logged)."
            )
        else:
            lines.append(
                "- **Catalog Depth**: Balanced representation of catalog deep-cuts and flagship tracks."
            )
        lines.append("")

        lines.append("## 5. Replay Loops & Catalog Additions")
        for a in t["top_artists"][:5]:
            lines.append(f"- **{a['artist']}**: {a['count']} plays")
        lines.append("")

        lines.append("## 6. Algorithmic Suggestions Radar & Weekend Queue")
        if radar:
            lines.append(
                "| Track | Artist | Shelf Source | Prior Impressions | Position | Status |"
            )
            lines.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
            for c in radar[:5]:
                status = "✨ New Arrival" if c["is_new"] else "🔁 Recurring"
                lines.append(
                    f"| {c['title']} | {c['artists']} | `{c['shelf']}` | "
                    f"{c['times_recommended']}x | #{c['latest_position']} | {status} |"
                )
        else:
            lines.append("No active recommendations captured.")

    elif cadence == "monthly":
        lines.append(f"# 📜 Monthly Retrospective: {period_label}\n")
        lines.append("## 1. Month in Review")
        lines.append(f"- **Total Plays**: {t['total_tracks']} ({t['total_duration_display']})")
        lines.append(
            f"- **Catalog Breadth**: {t['unique_artists_count']} artists, {t['unique_albums_count']} albums"
        )
        if t.get("catalog_anchor"):
            lines.append(f"- **Catalog Anchor**: {t['catalog_anchor']}")
        lines.append(f"- **Library Growth**: {len(t.get('new_likes', []))} new likes recorded\n")

        lines.append("## 2. Monthly Field Observations")
        if t["top_artists"]:
            lines.append(
                f"- **Monthly Core**: {t['top_artists'][0]['artist']} led overall volume ({t['top_artists'][0]['count']} plays)."
            )
        lines.append(
            f"- **Exploration Index**: {t['unique_artists_count']} distinct artists logged across {t['unique_albums_count']} releases."
        )
        lines.append("")

        lines.append("## 3. Sonic Cartography & Narrative Essay")
        if t["top_artists"]:
            lines.append(
                f"The month unfolded with extensive catalog exploration anchored by **{t['top_artists'][0]['artist']}**, "
                f"accounting for substantial playback time across multiple distinct albums."
            )
        lines.append("")

        lines.append("## 4. Dynamic Monthly Spotlight")
        if t.get("live_track_count", 0) > 0:
            lines.append(
                f"- **Live Archival Trajectory**: Strong engagement with concert bootlegs and live performance recordings ({t['live_track_count']} tracks)."
            )
        else:
            lines.append(
                "- **Production Era Focus**: Concentrated listening through studio catalog masterings."
            )
        lines.append("")

        lines.append("## 5. Algorithmic Suggestions Radar & Curated Archive Mixtape")
        if radar:
            lines.append(
                "| Track | Artist | Shelf Source | Prior Impressions | Position | Status |"
            )
            lines.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
            for c in radar[:8]:
                status = "✨ New Arrival" if c["is_new"] else "🔁 Recurring"
                lines.append(
                    f"| {c['title']} | {c['artists']} | `{c['shelf']}` | "
                    f"{c['times_recommended']}x | #{c['latest_position']} | {status} |"
                )
        else:
            lines.append("No active recommendations captured.")

    return "\n".join(lines).strip() + "\n"
