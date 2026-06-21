import random
from app.models.schemas import SEOData


TITLE_TEMPLATES_FR = [
    "La vérité cachée sur {topic}",
    "Ce que personne ne dit sur {topic}",
    "Tu ignores ça sur {topic}",
    "{topic} : le secret révélé",
    "Pourquoi tout le monde se trompe sur {topic}",
]

TITLE_TEMPLATES_EN = [
    "The hidden truth about {topic}",
    "What nobody tells you about {topic}",
    "You don't know this about {topic}",
    "{topic}: the secret revealed",
    "Why everyone is wrong about {topic}",
]

HASHTAGS_FR = [
    "#pourtoi", "#viral", "#apprendresurtiktok", "#vérité", "#secret",
    "#fyp", "#trending", "#learn", "#facts", "#viral2026",
]

HASHTAGS_EN = [
    "#fyp", "#viral", "#trending", "#facts", "#didyouknow",
    "#learn", "#shorts", "#reels", "#content", "#viral2026",
]

DESCRIPTION_TEMPLATES_FR = (
    "Tu ne savais sûrement pas ça sur {topic}. "
    "Regarde jusqu'à la fin — ça va changer ta façon de voir les choses. "
    "Dis-moi en commentaire ce que tu en penses 👇"
)

DESCRIPTION_TEMPLATES_EN = (
    "You probably didn't know this about {topic}. "
    "Watch until the end — it will change the way you see things. "
    "Let me know in the comments what you think 👇"
)


def generate_seo(topic: str, language: str = "fr") -> SEOData:
    title_pool = TITLE_TEMPLATES_FR if language == "fr" else TITLE_TEMPLATES_EN
    hashtag_pool = HASHTAGS_FR + HASHTAGS_EN
    description_template = DESCRIPTION_TEMPLATES_FR if language == "fr" else DESCRIPTION_TEMPLATES_EN

    titles = [t.format(topic=topic) for t in random.sample(title_pool, min(5, len(title_pool)))]
    hashtags = random.sample(hashtag_pool, min(10, len(hashtag_pool)))
    description = description_template.format(topic=topic)

    return SEOData(titles=titles, description=description, hashtags=hashtags)
