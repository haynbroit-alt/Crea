from moviepy import (
    AudioFileClip,
    CompositeAudioClip,
    ImageClip,
    concatenate_audioclips,
    concatenate_videoclips,
)
from moviepy.audio.fx import AudioFadeIn, AudioFadeOut, MultiplyVolume
from moviepy.video.fx import FadeIn, FadeOut, Resize
import os


def _make_clip(image_path: str, duration: float) -> ImageClip:
    clip = ImageClip(image_path).with_duration(duration)
    clip = clip.with_effects([
        Resize(lambda t: 1 + 0.04 * t / duration),
        FadeIn(0.25),
        FadeOut(0.25),
    ])
    return clip


def _loop_audio(clip: AudioFileClip, duration: float) -> AudioFileClip:
    """Tile an audio clip to exactly fill duration."""
    repeats = int(duration / clip.duration) + 2
    tiled = concatenate_audioclips([clip] * repeats)
    return tiled.with_duration(duration)


def assemble_video(
    image_paths: list[str],
    durations: list[float],
    voice_path: str | None,
    output_path: str,
    music_path: str | None = None,
    music_volume: float = 0.12,
) -> str:
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    clips = [_make_clip(p, d) for p, d in zip(image_paths, durations)]
    video = concatenate_videoclips(clips, method="compose")

    audio_layers: list = []

    if voice_path and os.path.exists(voice_path) and os.path.getsize(voice_path) > 0:
        try:
            voice = AudioFileClip(voice_path)
            max_dur = max(video.duration, voice.duration)
            video = video.with_duration(max_dur)
            voice = voice.with_duration(min(voice.duration, max_dur))
            audio_layers.append(voice)
        except Exception:
            pass

    if music_path and os.path.exists(music_path) and audio_layers:
        try:
            total_dur = audio_layers[0].duration
            music = AudioFileClip(music_path)
            music = _loop_audio(music, total_dur)
            music = music.with_effects([
                MultiplyVolume(music_volume),
                AudioFadeIn(1.0),
                AudioFadeOut(1.5),
            ])
            audio_layers.append(music)
        except Exception:
            pass

    if audio_layers:
        final_audio = (
            CompositeAudioClip(audio_layers) if len(audio_layers) > 1 else audio_layers[0]
        )
        video = video.with_audio(final_audio)

    video.write_videofile(
        output_path,
        fps=24,
        codec="libx264",
        audio_codec="aac",
        threads=1,
        logger=None,
    )
    return output_path
