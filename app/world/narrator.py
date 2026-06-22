"""
4-act script generator for "La Ville qui oublie" episodes.

Act 1 (0:00–0:45)  — Consequences: what was lost overnight
Act 2 (0:45–1:45)  — Today's event: world reacts to accumulated losses
Act 3 (1:45–2:15)  — New dilemma: the Mist returns, two memories threatened
Act 4 (2:15–2:30)  — Call to vote
"""
from app.world.catalog import get_memory, MEMORIES
from app.services.ai_client import generate_text
from app.core.prompts import (
    WORLD_NARRATOR_SYSTEM,
    WORLD_ACT1_PROMPT,
    WORLD_ACT2_PROMPT,
    WORLD_DAY1_PROMPT,
    CORRUPTION_NONE,
    CORRUPTION_WHISPER,
    CORRUPTION_MANIFEST,
    CORRUPTION_FRACTURE,
)


def _corruption_directive(corruption: float) -> str:
    if corruption <= 0.0:
        return CORRUPTION_NONE
    if corruption <= 0.3:
        return CORRUPTION_WHISPER
    if corruption <= 0.6:
        return CORRUPTION_MANIFEST
    return CORRUPTION_FRACTURE


_WORLD_EVENTS_BY_SANITY = [
    (90, "La place du marché bourdonne comme d'habitude. Quelque chose flotte dans l'air, indéfinissable."),
    (75, "Les anciens se réunissent en cercle. Ils parlent à voix basse. Ils ont commencé à noter ce qui manque."),
    (60, "Des familles quittent la ville avec leurs affaires. D'autres arrivent — attirés par quoi, ils ne sauraient le dire."),
    (45, "Le médecin a affiché une liste sur sa porte. Elle s'allonge chaque jour. La ville commence à trembler."),
    (25, "Le Conseil se réunit en urgence. La Brume n'avance plus seulement la nuit. Elle effleure les murs en plein jour."),
    (0,  "La ville tient encore. Mais à peine. Les habitants marchent les yeux vides, cherchant quelque chose qu'ils ne peuvent plus nommer."),
]

_WONDER_EVENTS = [
    (90, "Les enfants jouent encore dans les rues. Le monde a encore des couleurs, même si certaines ont disparu."),
    (70, "Les artistes de la ville peignent des choses étranges — comme s'ils essayaient de capturer ce qui s'efface."),
    (50, "La bibliothèque est pleine. Les habitants lisent pour ne pas oublier ce qui reste."),
    (20, "La ville est belle encore, mais d'une beauté froide — comme une fleur sans parfum."),
]

_CALL_TO_VOTE_FR = (
    "La Brume revient cette nuit. Le Conseil n'a qu'un seul choix à faire.\n\n"
    "Vote A : Protéger {label_A}.\n"
    "Vote B : Protéger {label_B}.\n\n"
    "L'autre disparaîtra à l'aube.\n"
    "Commente A ou B. C'est toi qui décides."
)


def _pick_event(scale: int, table: list[tuple]) -> str:
    for threshold, text in table:
        if scale >= threshold:
            return text
    return table[-1][1]


def _sanity_label(sanity: int) -> str:
    if sanity >= 80:
        return "stable"
    if sanity >= 60:
        return "fragile"
    if sanity >= 40:
        return "en crise"
    return "effondrée"


def _wonder_label(wonder: int) -> str:
    if wonder >= 70:
        return "vivant"
    if wonder >= 40:
        return "s'effaçant"
    return "éteint"


def _act1_template(world: dict, lost_today_id: str | None, day: int) -> str:
    lost_total = world.get("lost_memories", [])
    if lost_today_id:
        mem = get_memory(lost_today_id)
        return (
            f"Jour {day}. Cette nuit, la Brume a pris {mem.get('name', lost_today_id)}.\n\n"
            + mem.get("consequence_fr", "La ville a changé. Les habitants le sentent sans pouvoir le nommer.")
        )
    if day == 1:
        mem = get_memory("strawberry_taste")
        return (
            "Jour 1. Ce matin, quelque chose est différent.\n\n"
            + mem.get("consequence_fr", "")
            + "\n\nPersonne ne sait encore que c'est la Brume. Personne ne sait encore que ça vient de commencer."
        )
    lost_names = [get_memory(m).get("name", m) for m in lost_total[-2:]]
    return (
        f"Jour {day}. La liste de ce qui manque s'allonge encore.\n"
        "La ville essaie de s'habituer. "
        + (f"Depuis {len(lost_total)} nuit{'s' if len(lost_total) > 1 else ''}, " if lost_total else "")
        + "quelque chose part sans retour."
    )


def _act2_template(world: dict) -> str:
    sanity = world["collective_sanity"]
    wonder = world["wonder_level"]
    lost_total = world.get("lost_memories", [])
    sanity_event = _pick_event(sanity, _WORLD_EVENTS_BY_SANITY)
    wonder_event = _pick_event(wonder, _WONDER_EVENTS)
    result = f"{sanity_event}\n\n{wonder_event}"
    if len(lost_total) >= 3:
        lost_names_all = [get_memory(m).get("name", m) for m in lost_total]
        result += "\n\nLa ville a déjà perdu : " + ", ".join(lost_names_all) + "."
    return result


def _generate_act1(world: dict, lost_today_id: str | None, day: int) -> str:
    sanity = world["collective_sanity"]
    lost_total = world.get("lost_memories", [])
    corruption = world.get("system_corruption_level", 0.0)
    directive = _corruption_directive(corruption)

    if day == 1:
        mem = get_memory("strawberry_taste")
        ai_text = generate_text(
            WORLD_DAY1_PROMPT.format(consequence=mem.get("consequence_fr", "")),
            system=WORLD_NARRATOR_SYSTEM,
            max_tokens=200,
        )
    elif lost_today_id:
        mem = get_memory(lost_today_id)
        ai_text = generate_text(
            WORLD_ACT1_PROMPT.format(
                day=day,
                lost_memory_name=mem.get("name", lost_today_id),
                consequence=mem.get("consequence_fr", ""),
                sanity=sanity,
                lost_count=len(lost_total),
                corruption_directive=directive,
            ),
            system=WORLD_NARRATOR_SYSTEM,
            max_tokens=250,
        )
    else:
        ai_text = None

    return ai_text or _act1_template(world, lost_today_id, day)


def _generate_act2(world: dict, day: int) -> str:
    sanity = world["collective_sanity"]
    wonder = world["wonder_level"]
    infra = world.get("infrastructure_level", 100)
    lost_total = world.get("lost_memories", [])
    lost_names = ", ".join(get_memory(m).get("name", m) for m in lost_total) or "aucun encore"
    corruption = world.get("system_corruption_level", 0.0)
    directive = _corruption_directive(corruption)

    ai_text = generate_text(
        WORLD_ACT2_PROMPT.format(
            day=day,
            sanity=sanity,
            wonder=wonder,
            infra=infra,
            lost_count=len(lost_total),
            lost_names=lost_names,
            corruption_directive=directive,
        ),
        system=WORLD_NARRATOR_SYSTEM,
        max_tokens=300,
    )
    return ai_text or _act2_template(world)


def generate_script(world: dict, lost_today_id: str | None = None) -> dict:
    day = world["day"]
    sanity = world["collective_sanity"]
    wonder = world["wonder_level"]
    lost_total = world.get("lost_memories", [])
    dilemma = world.get("current_dilemma", {})

    act1 = _generate_act1(world, lost_today_id, day)
    act2 = _generate_act2(world, day)

    # ── Act 3 — always template (exact vote options required) ────────────────
    if dilemma:
        opt_a = dilemma.get("option_A", {})
        opt_b = dilemma.get("option_B", {})
        name_a = opt_a.get("label_protect", "?")
        name_b = opt_b.get("label_protect", "?")
        sacrifice_a = opt_a.get("label_sacrifice", "?")
        sacrifice_b = opt_b.get("label_sacrifice", "?")
        act3 = (
            f"Ce soir, la Brume cible deux souvenirs.\n\n"
            f"Vote A : Vous protégez {name_a}. Mais {sacrifice_a} disparaît.\n"
            f"Vote B : Vous protégez {name_b}. Mais {sacrifice_b} disparaît.\n\n"
            f"{dilemma.get('threat', '')}"
        )
    else:
        act3 = "La Brume hésite ce soir. Le Conseil attend."

    # ── Act 4 — always template (call to vote) ───────────────────────────────
    if dilemma and dilemma.get("option_A") and dilemma.get("option_B"):
        act4 = _CALL_TO_VOTE_FR.format(
            label_A=dilemma["option_A"].get("label_protect", "?"),
            label_B=dilemma["option_B"].get("label_protect", "?"),
        )
    else:
        act4 = "La Brume n'a pas encore choisi. Revenez demain."

    full_script = "\n\n---\n\n".join([act1, act2, act3, act4])

    # Zero-RAM visual: a Pollinations URL string the client renders directly.
    # The server never downloads or stores an image — the CRT player in
    # /godmode points an <img> straight at this URL.
    from app.services.image_generator import pollinations_url
    image_prompt = act1 or act2 or full_script
    image_url = pollinations_url(image_prompt)

    return {
        "day": day,
        "narrative_text": full_script,
        "image_url": image_url,
        "acts": {
            "act1": {"timecode": "0:00–0:45", "title": "Les Conséquences", "text": act1},
            "act2": {"timecode": "0:45–1:45", "title": "L'Événement du Jour", "text": act2},
            "act3": {"timecode": "1:45–2:15", "title": "Le Dilemme", "text": act3},
            "act4": {"timecode": "2:15–2:30", "title": "L'Appel au Vote", "text": act4},
        },
        "full_script": full_script,
        "stats": {
            "collective_sanity": sanity,
            "wonder_level": wonder,
            "infrastructure_level": world.get("infrastructure_level", 100),
            "lost_count": len(lost_total),
        },
        "music_cue": {
            "0:00": "piano mystérieux",
            "0:30": "montée émotionnelle légère",
            "1:30": "ambiance inquiétante",
            "2:15": "note suspendue",
        },
        "music_params": _music_params(world),
        "ai_generated": _is_ai_available(),
    }


def _music_params(world: dict) -> dict:
    from app.world.music import derive_music_params
    return derive_music_params(world)


def _is_ai_available() -> bool:
    from app.services.ai_client import is_available
    return is_available()
