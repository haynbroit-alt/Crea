from app.models.schemas import Script, Scene


VISUAL_KEYWORD_MAP = {
    "secret": ["mystery secret dark background"],
    "vérité": ["truth revelation light"],
    "choc": ["explosion shock surprise face"],
    "argent": ["money cash bills finance"],
    "internet": ["computer laptop online network"],
    "erreur": ["mistake error wrong sign"],
    "comprendre": ["person thinking idea lightbulb"],
    "gens": ["crowd people street city"],
    "truth": ["truth revelation light"],
    "money": ["money cash bills finance"],
    "people": ["crowd people street city"],
    "mistake": ["mistake error wrong sign"],
}


def _extract_visual_keywords(sentence: str) -> list[str]:
    words = sentence.lower().split()
    keywords = []
    for word in words:
        clean = word.strip(".,!?…")
        if clean in VISUAL_KEYWORD_MAP:
            keywords.extend(VISUAL_KEYWORD_MAP[clean].copy())
        elif len(clean) > 4:
            keywords.append(clean)
    return (keywords or words[:3])[:5]


def split_scenes(script: Script) -> list[Scene]:
    sentences = [script.hook] + script.body + [script.conclusion]
    scenes = []

    for i, text in enumerate(sentences):
        duration = "3s" if i == 0 else ("5s" if i < len(sentences) - 1 else "4s")
        scenes.append(
            Scene(
                index=i + 1,
                text=text,
                visual_keywords=_extract_visual_keywords(text),
                duration_hint=duration,
            )
        )

    return scenes
