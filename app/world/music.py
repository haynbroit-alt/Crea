"""
Procedural music engine for "La Ville qui oublie".

Audio parameters are derived entirely from the world state JSON:
  - collective_sanity + wonder_level → hope score
  - 100 - collective_sanity → panic score
  - len(lost_memories) * 7 → fog level

Mood map:
  panic > 60  → "panic"   (fast, minor, heartbeat layer)
  hope  > 60  → "hope"    (slow, major, gentle)
  else        → "mystery" (slow-mid, minor, box-music layer)

Each episode gets a deterministic seed so music is reproducible.
"""
import os
import random
import struct
import wave

import numpy as np

SR = 44_100  # sample rate

# ── Scales (Hz, A3 root) ─────────────────────────────────────────────────────
_MINOR = [220.0, 246.9, 261.6, 293.7, 329.6, 349.2, 392.0]
_MAJOR = [261.6, 293.7, 329.6, 349.2, 392.0, 440.0, 493.9]
_BOX   = [261.6, 277.2, 311.1, 349.2, 370.0]  # sparse, music-box feel

_MOOD_RULES = {
    "hope":    {"tempo": 80,  "key": "major", "duration": 130},
    "mystery": {"tempo": 65,  "key": "minor", "duration": 130},
    "panic":   {"tempo": 140, "key": "minor", "duration": 130},
}


# ── World-state → music parameters ───────────────────────────────────────────

def derive_music_params(world: dict) -> dict:
    sanity = world.get("collective_sanity", 100)
    wonder = world.get("wonder_level", 100)
    lost   = len(world.get("lost_memories", []))

    hope      = int((sanity + wonder) / 2)
    panic     = 100 - sanity
    fog_level = min(100, lost * 7)

    if panic > 60:
        mood = "panic"
    elif hope > 60:
        mood = "hope"
    else:
        mood = "mystery"

    rules = _MOOD_RULES[mood]
    seed  = hash(f"{world.get('day', 1)}-{world.get('world_name', 'v')}-{lost}") & 0xFFFFFFFF

    return {
        "mood": mood,
        "hope": hope,
        "panic": panic,
        "fog_level": fog_level,
        "tempo": rules["tempo"],
        "key": rules["key"],
        "duration_seconds": rules["duration"],
        "effects": {
            "reverb":      fog_level > 70,
            "heartbeat":   panic > 80,
            "music_box":   lost > 4,
            "low_pitch":   hope < 20,
        },
        "seed": seed,
    }


# ── Synthesis helpers ─────────────────────────────────────────────────────────

def _tone(freq: float, duration: float, volume: float = 0.4, decay: float = 3.0) -> np.ndarray:
    t = np.linspace(0, duration, int(SR * duration), endpoint=False)
    wave_ = np.sin(2 * np.pi * freq * t)
    envelope = np.exp(-decay * t / duration)
    return (wave_ * envelope * volume).astype(np.float32)


def _heartbeat(duration: float, bpm: float = 70, volume: float = 0.15) -> np.ndarray:
    out = np.zeros(int(SR * duration), dtype=np.float32)
    beat_s = 60.0 / bpm
    pos = 0
    while pos < len(out):
        for offset, amp in [(0, volume), (int(0.12 * SR), volume * 0.6)]:
            idx = pos + offset
            if idx < len(out):
                pulse_len = min(int(0.06 * SR), len(out) - idx)
                t_p = np.linspace(0, 1, pulse_len)
                out[idx:idx + pulse_len] += np.sin(np.pi * t_p) * amp
        pos += int(beat_s * SR)
    return out


def _apply_reverb(audio: np.ndarray, delay_samples: int = 4410, decay: float = 0.4) -> np.ndarray:
    out = audio.copy()
    for i in range(1, 5):
        shift = delay_samples * i
        if shift < len(out):
            out[shift:] += audio[:len(out) - shift] * (decay ** i)
    return out / (np.max(np.abs(out)) + 1e-9)


# ── Main generator ────────────────────────────────────────────────────────────

def generate_music(world: dict, output_path: str) -> dict:
    params = derive_music_params(world)
    rng = random.Random(params["seed"])
    np.random.seed(params["seed"] % (2**31))

    scale = _MAJOR if params["key"] == "major" else _MINOR
    if params["effects"]["music_box"]:
        scale = _BOX

    beat_dur = 60.0 / params["tempo"]
    total_samples = int(SR * params["duration_seconds"])
    audio = np.zeros(total_samples, dtype=np.float32)

    # ── Melody layer ──────────────────────────────────────────────────────────
    pos = 0
    while pos < total_samples:
        freq   = rng.choice(scale)
        # occasional octave up for brightness
        if params["key"] == "major" and rng.random() > 0.7:
            freq *= 2
        dur    = beat_dur * rng.choice([0.5, 1.0, 1.5, 2.0])
        silence = rng.random() > 0.75   # rests give breathing room
        if not silence:
            tone   = _tone(freq, dur, volume=0.35, decay=4.0 if params["effects"]["music_box"] else 2.0)
            end    = min(pos + len(tone), total_samples)
            audio[pos:end] += tone[:end - pos]
        pos += int(dur * SR)

    # ── Bass layer (minor/panic moods) ────────────────────────────────────────
    if params["key"] == "minor":
        pos = 0
        bass_scale = [f / 4 for f in scale[:4]]
        while pos < total_samples:
            freq = rng.choice(bass_scale)
            dur  = beat_dur * 2
            tone = _tone(freq, dur, volume=0.2, decay=1.5)
            end  = min(pos + len(tone), total_samples)
            audio[pos:end] += tone[:end - pos]
            pos += int(dur * SR)

    # ── Heartbeat ─────────────────────────────────────────────────────────────
    if params["effects"]["heartbeat"]:
        hb_bpm = 60 + int(params["panic"] * 0.8)
        audio += _heartbeat(params["duration_seconds"], bpm=hb_bpm)

    # ── Reverb (fog) ──────────────────────────────────────────────────────────
    if params["effects"]["reverb"]:
        audio = _apply_reverb(audio, delay_samples=int(SR * 0.08))

    # ── Low-pitch shift (hope < 20) ───────────────────────────────────────────
    if params["effects"]["low_pitch"]:
        # simple decimation for half-speed pitch drop
        audio = np.interp(
            np.linspace(0, len(audio) - 1, len(audio) // 2),
            np.arange(len(audio)),
            audio,
        ).astype(np.float32)
        audio = np.tile(audio, 2)[:total_samples]

    # ── Fade in / out ─────────────────────────────────────────────────────────
    fade = int(SR * 2.5)
    audio[:fade]  *= np.linspace(0, 1, fade)
    audio[-fade:] *= np.linspace(1, 0, fade)

    # ── Normalise & write WAV ─────────────────────────────────────────────────
    peak = np.max(np.abs(audio))
    if peak > 0:
        audio /= peak
    pcm = (audio * 32767).astype(np.int16)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with wave.open(output_path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(pcm.tobytes())

    params["output_path"] = output_path
    return params
