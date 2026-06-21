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
