"""
4-act script generator for "La Ville qui oublie" episodes.

Act 1 (0:00–0:45)  — Consequences: what was lost overnight
Act 2 (0:45–1:45)  — Today's event: world reacts to accumulated losses
Act 3 (1:45–2:15)  — New dilemma: the Mist returns, two memories threatened
Act 4 (2:15–2:30)  — Call to vote
"""
from app.world.catalog import get_memory, MEMORIES


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


def generate_script(world: dict, lost_today_id: str | None = None) -> dict:
    day = world["day"]
    sanity = world["collective_sanity"]
    wonder = world["wonder_level"]
    lost_total = world.get("lost_memories", [])
    dilemma = world.get("current_dilemma", {})

    # ── Act 1 ─────────────────────────────────────────────────────────────────
    if lost_today_id:
        mem = get_memory(lost_today_id)
        act1 = (
            f"Jour {day}. Cette nuit, la Brume a pris {mem.get('name', lost_today_id)}.\n\n"
            + mem.get("consequence_fr", "La ville a changé. Les habitants le sentent sans pouvoir le nommer.")
        )
    elif day == 1:
        mem = get_memory("strawberry_taste")
        act1 = (
            f"Jour 1. Ce matin, quelque chose est différent.\n\n"
            + mem.get("consequence_fr", "")
            + "\n\nPersonne ne sait encore que c'est la Brume. Personne ne sait encore que ça vient de commencer."
        )
    else:
        lost_names = [get_memory(m).get("name", m) for m in lost_total[-2:]]
        act1 = (
            f"Jour {day}. La liste de ce qui manque s'allonge encore.\n"
            + "La ville essaie de s'habituer. "
            + (f"Depuis {len(lost_total)} nuit{'s' if len(lost_total) > 1 else ''}, " if lost_total else "")
            + "quelque chose part sans retour."
        )

    # ── Act 2 ─────────────────────────────────────────────────────────────────
    sanity_event = _pick_event(sanity, _WORLD_EVENTS_BY_SANITY)
    wonder_event = _pick_event(wonder, _WONDER_EVENTS)

    if len(lost_total) >= 3:
        lost_names_all = [get_memory(m).get("name", m) for m in lost_total]
        inventory = "La ville a déjà perdu : " + ", ".join(lost_names_all) + "."
    else:
        inventory = ""

    act2 = f"{sanity_event}\n\n{wonder_event}"
    if inventory:
        act2 += f"\n\n{inventory}"

    # ── Act 3 ─────────────────────────────────────────────────────────────────
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

    # ── Act 4 ─────────────────────────────────────────────────────────────────
    if dilemma and dilemma.get("option_A") and dilemma.get("option_B"):
        act4 = _CALL_TO_VOTE_FR.format(
            label_A=dilemma["option_A"].get("label_protect", "?"),
            label_B=dilemma["option_B"].get("label_protect", "?"),
        )
    else:
        act4 = "La Brume n'a pas encore choisi. Revenez demain."

    full_script = "\n\n---\n\n".join([act1, act2, act3, act4])

    return {
        "day": day,
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
    }
