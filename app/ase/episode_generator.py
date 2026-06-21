import random

_EVENTS_FR = [
    "un objet impossible apparaît",
    "une voix inconnue prononce son nom",
    "la réalité se fissure légèrement",
    "un souvenir refait surface",
    "quelqu'un trahit la confiance d'Alex",
    "une porte s'ouvre là où il n'y en avait pas",
    "le temps s'arrête une fraction de seconde",
]
_EVENTS_EN = [
    "an impossible object appears",
    "an unknown voice calls their name",
    "reality cracks slightly",
    "a buried memory resurfaces",
    "someone betrays Alex's trust",
    "a door opens where there was none",
    "time stops for a fraction of a second",
]

_CLIFFHANGERS_FR = [
    "Mais ce qu'Alex découvre ensuite change tout...",
    "Et soudain, L'Ombre parle pour la première fois...",
    "Ce que Maya cache est bien pire que prévu...",
    "La vérité est là, à portée de main... mais quelqu'un l'efface.",
    "Le prochain épisode révèle l'impensable.",
]
_CLIFFHANGERS_EN = [
    "But what Alex discovers next changes everything...",
    "And then The Shadow speaks for the first time...",
    "What Maya is hiding is far worse than expected...",
    "The truth is right there... but someone erases it.",
    "The next episode reveals the unthinkable.",
]

_HOOKS_FR = [
    "Personne n'était censé le savoir...",
    "Ce qui suit ne devrait pas être possible...",
    "Tout a commencé par une coïncidence impossible...",
    "Épisode {n} — et ça empire encore.",
    "Si tu pensais que c'était fini, tu avais tort.",
]
_HOOKS_EN = [
    "Nobody was supposed to know...",
    "What follows should not be possible...",
    "It all started with an impossible coincidence...",
    "Episode {n} — and it gets worse.",
    "If you thought it was over, you were wrong.",
]


def generate_episode(story: dict, episode_number: int) -> dict:
    lang = story.get("language", "fr")
    events = _EVENTS_FR if lang == "fr" else _EVENTS_EN
    cliffhangers = _CLIFFHANGERS_FR if lang == "fr" else _CLIFFHANGERS_EN
    hook_pool = _HOOKS_FR if lang == "fr" else _HOOKS_EN
    topic = story.get("topic", "")
    world_state = story.get("world_state", {})
    tension = world_state.get("tension", 0)
    chars = story.get("universe", {}).get("characters", [])
    protagonist = chars[0]["name"] if chars else "Alex"

    hook = random.choice(hook_pool).format(n=episode_number)

    num_events = min(2 + tension // 3, 4)
    selected_events = random.sample(events, min(num_events, len(events)))

    if lang == "fr":
        body = [
            f"{protagonist} affronte {topic} pour la {episode_number}e fois.",
            *selected_events,
            f"La tension monte. Le mystère s'épaissit.",
        ]
    else:
        body = [
            f"{protagonist} faces {topic} for the {episode_number}th time.",
            *selected_events,
            f"Tension rises. The mystery deepens.",
        ]

    cliffhanger = random.choice(cliffhangers)

    return {
        "episode_number": episode_number,
        "hook": hook,
        "body": body,
        "cliffhanger": cliffhanger,
        "world_state_snapshot": dict(world_state),
        "full_script": " ".join([hook] + body + [cliffhanger]),
    }
