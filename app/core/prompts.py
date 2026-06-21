WORLD_NARRATOR_SYSTEM = (
    "Tu es le narrateur de \"La Ville qui oublie\", une série interactive où une ville perd ses souvenirs "
    "un à un à cause d'une entité appelée la Brume. Ton style est poétique, inquiétant et intime. "
    "Phrases courtes. Présent narratif. Tu écris pour des épisodes vidéo de 2-3 minutes."
)

WORLD_ACT1_PROMPT = """Écris l'Acte 1 (Les Conséquences) de l'épisode du Jour {day}.

Mémoire perdue cette nuit : {lost_memory_name}
Conséquence documentée : {consequence}
Sanité collective : {sanity}/100
Souvenirs perdus jusqu'ici : {lost_count}
{corruption_directive}
Environ 80 mots. Commence par "Jour {day}.". Montre la découverte au matin — comment les habitants réalisent que quelque chose manque. Réinterprète la conséquence avec une scène concrète et sensorielle, ne la répète pas mot à mot."""

WORLD_ACT2_PROMPT = """Écris l'Acte 2 (L'Événement du Jour) de l'épisode du Jour {day}.

Sanité collective : {sanity}/100
Émerveillement : {wonder}/100
Infrastructure : {infra}/100
Souvenirs perdus ({lost_count}) : {lost_names}
{corruption_directive}
Environ 100 mots. Décris comment la ville vit aujourd'hui sous le poids des pertes accumulées. Scènes de vie quotidienne concrètes. Ton journalistique mais poétique. Montre les effets combinés de tous les souvenirs disparus, pas seulement le dernier."""

# Corruption directives injected into narrator prompts based on system_corruption_level
CORRUPTION_NONE = ""

CORRUPTION_WHISPER = (
    "Directive subtile : Glisse une seule phrase où les urnes de la ville semblent "
    "murmurer, ou un bulletin se consume tout seul. Étrangeté à peine perceptible — "
    "un détail que seuls les lecteurs attentifs remarqueront."
)

CORRUPTION_MANIFEST = (
    "Directive explicite : La Brume vote désormais. Mentionne que des ombres ont été "
    "vues glissant des choix dans les fissures des murs la nuit. Le peuple pressent "
    "qu'on lui vole ses décisions, mais n'ose pas le dire à voix haute."
)

CORRUPTION_FRACTURE = (
    "Directive de rupture totale : La folie consume la narration elle-même. "
    "Le narrateur peut répéter un mot deux fois de suite (bégaiement textuel). "
    "Un fragment de code ou d'erreur système — 'ERR', 'NULL', '[SYS]' — "
    "peut apparaître dans la bouche d'un personnage sans qu'il comprenne ce qu'il dit. "
    "À la fin, le narrateur s'adresse brièvement à 'ceux qui regardent', "
    "comme s'il devinait qu'il est observé depuis l'extérieur de l'histoire."
)

WORLD_DAY1_PROMPT = """Écris l'Acte 1 (Les Conséquences) du tout premier épisode, Jour 1.

La ville vient de perdre son tout premier souvenir : le goût des fraises.
Conséquence : {consequence}

Environ 80 mots. Commence par "Jour 1.". Capture l'étrangeté du premier matin — les habitants ne comprennent pas encore ce qui se passe. La Brume est inconnue. Quelque chose cloche, mais personne ne sait le nommer."""

SCRIPT_AI_PROMPT = """Sujet : {topic}
Style : {style}
Langue : {lang_name}

Génère un script vidéo viral et retourne UNIQUEMENT un JSON valide avec cette structure exacte :
{{"hook": "...", "body": ["phrase1", "phrase2", "phrase3", "phrase4", "phrase5"], "conclusion": "..."}}

Contraintes :
- hook : 1 phrase choc, maximum 15 mots, ton percutant
- body : exactement 5 phrases courtes et rythmées sur le sujet
- conclusion : 1 appel à l'action court
- Chaque phrase peut être une scène vidéo distincte
- Pas de markdown, uniquement le JSON brut"""

SCRIPT_PROMPT = """
Tu es un expert en création de vidéos virales TikTok / YouTube Shorts.

Sujet : {topic}
Style : {style}
Langue : {language}

Écris un script vidéo de 2 à 3 minutes avec :
- Un hook puissant (0–5 sec) : phrase choc ou question forte
- Un développement en 3 à 5 points clés
- Un twist ou fait surprenant
- Une conclusion avec appel à l'action

Contraintes :
- Phrases courtes et rythmées
- Ton direct et captivant
- Chaque phrase peut être une scène vidéo distincte
"""

HOOK_PROMPT = """
Génère 5 hooks viraux pour une vidéo sur : {topic}

Contraintes :
- Maximum 10 mots par hook
- Émotion forte : curiosité, surprise, choc
- Style TikTok / Shorts
- Pas de phrases génériques
"""

TITLE_PROMPT = """
Génère 5 titres viraux pour YouTube Shorts / TikTok sur : {topic}

Contraintes :
- 3 à 8 mots max
- Très engageant, légèrement clickbait mais honnête
- Émotion forte
"""

HASHTAG_PROMPT = """
Génère 10 hashtags pour une vidéo sur : {topic}

Mix :
- 5 hashtags en français
- 5 hashtags en anglais
- Mélange niche + viral
"""

VISUAL_KEYWORDS_PROMPT = """
Pour cette phrase de script, propose 3 à 5 mots-clés en anglais
pour rechercher une vidéo stock sur Pexels / Pixabay.

Phrase : {sentence}

Format : mots séparés par des espaces, très visuels et concrets.
"""
