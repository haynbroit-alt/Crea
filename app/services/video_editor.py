from moviepy import ImageClip, AudioFileClip, concatenate_videoclips
from moviepy.video.fx import FadeIn, FadeOut, Resize
import os


def _make_clip(image_path: str, duration: float) -> ImageClip:
    clip = ImageClip(image_path).with_duration(duration)
    # subtle zoom-in over the clip's lifetime
    clip = clip.with_effects([
        Resize(lambda t: 1 + 0.04 * t / duration),
        FadeIn(0.25),
        FadeOut(0.25),
    ])
    return clip


def assemble_video(
    image_paths: list[str],
    durations: list[float],
    voice_path: str | None,
    output_path: str,
) -> str:
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    clips = [_make_clip(p, d) for p, d in zip(image_paths, durations)]
    video = concatenate_videoclips(clips, method="compose")

    if voice_path and os.path.exists(voice_path):
        audio = AudioFileClip(voice_path)
        max_dur = max(video.duration, audio.duration)
        video = video.with_duration(max_dur)
        audio = audio.with_duration(min(audio.duration, max_dur))
        video = video.with_audio(audio)

    video.write_videofile(
        output_path,
        fps=24,
        codec="libx264",
        audio_codec="aac",
        logger=None,
    )
    return output_path
