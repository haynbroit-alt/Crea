# Memory catalog for "La Ville qui oublie"
# Tier 1 = sensory/minor  Tier 2 = social/emotional  Tier 3 = existential/critical
# Losing higher-tier memories has heavier world-state consequences.

MEMORIES: dict[str, dict] = {
    # ── Tier 1 — sensory / aesthetic ──────────────────────────────────────────
    "strawberry_taste": {
        "id": "strawberry_taste",
        "tier": 1,
        "name": "le goût des fraises",
        "loss_impact": {"collective_sanity": -5, "wonder_level": -8},
        "consequence_fr": (
            "Les habitants croquent leurs fraises du matin. "
            "Quelque chose manque — un goût qui n'a plus de nom. "
            "Les enfants regardent leurs bols vides avec une expression étrange. "
            "Ce n'est pas mauvais. C'est juste... absent."
        ),
    },
    "color_red": {
        "id": "color_red",
        "tier": 1,
        "name": "la couleur rouge",
        "loss_impact": {"collective_sanity": -8, "wonder_level": -12},
        "consequence_fr": (
            "Les marchands remarquent les premières anomalies à l'aube. "
            "Les pommes semblent grises. Les coquelicots, éteints. "
            "Quelqu'un montre du sang sur sa main blessée : il est sombre, presque brun. "
            "La ville ne sait plus nommer cette nuance."
        ),
    },
    "smell_of_rain": {
        "id": "smell_of_rain",
        "tier": 1,
        "name": "l'odeur de la pluie",
        "loss_impact": {"collective_sanity": -6, "wonder_level": -10},
        "consequence_fr": (
            "Il pleut cette nuit, comme souvent. "
            "Mais quand les premiers habitants ouvrent leurs fenêtres, "
            "quelque chose dans l'air ne leur dit plus rien. "
            "L'eau tombe. Elle mouille. Elle ne sent plus rien du tout."
        ),
    },
    "sad_melodies": {
        "id": "sad_melodies",
        "tier": 1,
        "name": "les mélodies tristes",
        "loss_impact": {"collective_sanity": -10, "wonder_level": -15},
        "consequence_fr": (
            "Le musicien de la place joue son air habituel — celui du deuil, du départ. "
            "Les passants s'arrêtent, intrigués. "
            "La musique semble incomplète, comme un mot qu'on ne peut plus prononcer. "
            "Personne ne sait pourquoi elle ne fait plus pleurer."
        ),
    },
    "birdsong": {
        "id": "birdsong",
        "tier": 1,
        "name": "le chant des oiseaux",
        "loss_impact": {"collective_sanity": -7, "wonder_level": -12},
        "consequence_fr": (
            "Les oiseaux chantent comme chaque matin. "
            "Mais pour les habitants, ce son n'est plus qu'un bruit — "
            "agréable peut-être, mais vide de sens. "
            "Personne ne sait plus que cela s'appelle un chant."
        ),
    },

    # ── Tier 2 — social / emotional ───────────────────────────────────────────
    "child_laughter": {
        "id": "child_laughter",
        "tier": 2,
        "name": "le rire des enfants",
        "loss_impact": {"collective_sanity": -20, "wonder_level": -18},
        "consequence_fr": (
            "Les enfants jouent dans les rues, comme avant. "
            "Ils courent, tombent, se relèvent. "
            "Mais ce son léger, ce son haut et libre — "
            "il n'émerge plus de leurs gorges. "
            "Ils ne savent pas ce qui manque. Les adultes, si."
        ),
    },
    "nostalgia": {
        "id": "nostalgia",
        "tier": 2,
        "name": "la nostalgie",
        "loss_impact": {"collective_sanity": -15, "wonder_level": -20},
        "consequence_fr": (
            "Les anciens ouvrent leurs vieux albums de photos. "
            "Ils voient des visages, des lieux, des moments. "
            "Ils savent que c'était important. "
            "Mais la douleur douce de se souvenir — cette chaleur dans la poitrine — "
            "elle n'est plus là. Le passé est devenu neutre."
        ),
    },
    "concept_of_strangers": {
        "id": "concept_of_strangers",
        "tier": 2,
        "name": "la notion d'étranger",
        "loss_impact": {"collective_sanity": -18, "infrastructure_level": -10},
        "consequence_fr": (
            "Les portes de la ville restent ouvertes toute la nuit. "
            "Les habitants accueillent tous ceux qui arrivent — "
            "marchands, voyageurs, inconnus. "
            "La ville est plus vivante. "
            "Et quelqu'un, quelque part, entre sans invitation."
        ),
    },
    "dreams": {
        "id": "dreams",
        "tier": 2,
        "name": "les rêves",
        "loss_impact": {"collective_sanity": -25, "wonder_level": -20},
        "consequence_fr": (
            "Le sommeil reste. Les nuits sont longues et noires. "
            "Mais au réveil, les habitants regardent le plafond avec une expression vide. "
            "Les heures dormies n'ont laissé aucune image, aucune histoire. "
            "Juste un vide propre et inquiétant."
        ),
    },

    # ── Tier 3 — existential / critical ───────────────────────────────────────
    "concept_of_time": {
        "id": "concept_of_time",
        "tier": 3,
        "name": "le concept du temps",
        "loss_impact": {"collective_sanity": -35, "infrastructure_level": -30},
        "consequence_fr": (
            "Les horloges tournent. Les cloches sonnent. "
            "Mais les habitants ne savent plus ce que ces sons signifient. "
            "Hier et demain sont devenus le même mot. "
            "Le boulanger oublie de cuire le pain du matin "
            "parce qu'il ne sait plus ce qu'est 'le matin'."
        ),
    },
    "fear": {
        "id": "fear",
        "tier": 3,
        "name": "la peur",
        "loss_impact": {"collective_sanity": -15, "infrastructure_level": -40},
        "consequence_fr": (
            "Un enfant marche au bord d'une falaise. "
            "Il ne tremble pas. "
            "Les adultes lui crient de reculer. Il ne comprend pas pourquoi. "
            "La ville entière a perdu son instinct de survie. "
            "Ce soir, trois accidents graves sont signalés."
        ),
    },
    "written_language": {
        "id": "written_language",
        "tier": 3,
        "name": "l'écriture",
        "loss_impact": {"collective_sanity": -20, "infrastructure_level": -45},
        "consequence_fr": (
            "Les panneaux de la ville semblent recouverts de symboles étranges. "
            "Les livres sont devenus silencieux. "
            "Le médecin ne peut plus lire ses fiches. "
            "Le juge ne peut plus lire les lois. "
            "Le cordonnier ne peut plus lire sa commande."
        ),
    },
    "faces_of_loved_ones": {
        "id": "faces_of_loved_ones",
        "tier": 3,
        "name": "les visages des êtres chers",
        "loss_impact": {"collective_sanity": -50, "wonder_level": -30},
        "consequence_fr": (
            "Une mère prépare le petit-déjeuner pour ses enfants. "
            "Quand ils descendent, elle les regarde — et ne reconnaît pas leurs visages. "
            "Elle sait que ce sont ses enfants. "
            "Elle ne ressent plus rien en les regardant. "
            "La ville entière pleure des larmes qu'elle ne sait plus pourquoi elle verse."
        ),
    },
}


DILEMMA_SEQUENCE: list[tuple[str, str]] = [
    ("strawberry_taste", "child_laughter"),   # Day 1
    ("smell_of_rain",    "nostalgia"),         # Day 2
    ("color_red",        "birdsong"),          # Day 3
    ("sad_melodies",     "dreams"),            # Day 4
    ("concept_of_strangers", "fear"),          # Day 5
    ("concept_of_time",  "written_language"),  # Day 6
    ("faces_of_loved_ones", "child_laughter"), # Day 7 (if still alive)
]


def get_memory(memory_id: str) -> dict:
    return MEMORIES.get(memory_id, {})


def next_dilemma(day: int, lost: list[str]) -> tuple[str, str] | None:
    for option_a, option_b in DILEMMA_SEQUENCE:
        if option_a not in lost and option_b not in lost:
            return option_a, option_b
    # fallback: any two surviving memories
    alive = [m for m in MEMORIES if m not in lost]
    return (alive[0], alive[1]) if len(alive) >= 2 else None
