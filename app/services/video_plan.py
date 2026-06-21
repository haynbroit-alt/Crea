from app.models.schemas import Script, Scene, SEOData, VideoPlan


def build_video_plan(
    topic: str,
    language: str,
    style: str,
    script: Script,
    scenes: list[Scene],
    seo: SEOData,
) -> VideoPlan:
    total_scenes = len(scenes)
    # rough estimate: hook 3s + body scenes 5s each + conclusion 4s
    estimated_seconds = 3 + (total_scenes - 2) * 5 + 4
    duration_str = f"{estimated_seconds // 60}m{estimated_seconds % 60}s"

    return VideoPlan(
        topic=topic,
        language=language,
        style=style,
        script=script,
        scenes=scenes,
        seo=seo,
        format="9:16 vertical",
        estimated_duration=duration_str,
        status="ready_for_rendering",
    )
