import random

_TONES_FR = ["mystère", "suspense", "émotion", "thriller", "aventure"]
_TONES_EN = ["mystery", "suspense", "emotion", "thriller", "adventure"]

_RULES_FR = [
    "chaque épisode se termine par un cliffhanger",
    "la tension monte à chaque épisode",
    "un secret est révélé partiellement à chaque épisode",
]
_RULES_EN = [
    "every episode ends on a cliffhanger",
    "tension escalates each episode",
    "one secret is partially revealed per episode",
]

_CHARS_FR = [
    {"name": "Alex", "role": "protagoniste curieux", "flaw": "impulsif"},
    {"name": "L'Ombre", "role": "force inconnue", "flaw": "imprévisible"},
    {"name": "Maya", "role": "alliée secrète", "flaw": "cache quelque chose"},
    {"name": "Le Gardien", "role": "antagoniste ambigu", "flaw": "motivations floues"},
]
_CHARS_EN = [
    {"name": "Alex", "role": "curious protagonist", "flaw": "impulsive"},
    {"name": "The Shadow", "role": "unknown force", "flaw": "unpredictable"},
    {"name": "Maya", "role": "secret ally", "flaw": "hiding something"},
    {"name": "The Keeper", "role": "ambiguous antagonist", "flaw": "unclear motives"},
]


def build_universe(topic: str, language: str = "fr") -> dict:
    tones = _TONES_FR if language == "fr" else _TONES_EN
    rules = _RULES_FR if language == "fr" else _RULES_EN
    chars = _CHARS_FR if language == "fr" else _CHARS_EN

    if language == "fr":
        desc = f"Un univers mystérieux centré sur {topic}, où rien n'est ce qu'il paraît."
    else:
        desc = f"A mysterious universe centered on {topic}, where nothing is as it seems."

    return {
        "description": desc,
        "tone": random.choice(tones),
        "core_mystery": topic,
        "rules": random.sample(rules, 2),
        "characters": random.sample(chars, min(3, len(chars))),
    }
