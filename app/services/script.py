import random
from app.models.schemas import Script


HOOKS_FR = [
    "Personne ne te dit ça sur {topic}...",
    "Ce secret sur {topic} va te choquer...",
    "Tu fais sûrement une erreur avec {topic}...",
    "La vérité sur {topic} que tout le monde cache...",
    "3 choses que tu ignores sur {topic}...",
]

HOOKS_EN = [
    "Nobody tells you this about {topic}...",
    "The shocking truth about {topic}...",
    "You're probably doing {topic} wrong...",
    "What they don't want you to know about {topic}...",
    "3 things nobody tells you about {topic}...",
]

BODY_FR = [
    "{topic} est beaucoup plus important que tu ne le penses.",
    "La plupart des gens passent complètement à côté de ça.",
    "Voici ce que tu dois vraiment comprendre.",
    "Et pourtant, presque personne n'en parle.",
    "Mais il y a un détail que tout le monde ignore.",
    "C'est là que tout change.",
    "Et la suite va te surprendre.",
]

BODY_EN = [
    "{topic} is way more important than you think.",
    "Most people completely miss this.",
    "Here's what you really need to understand.",
    "Yet almost nobody talks about this.",
    "But there's one detail everyone ignores.",
    "That's where everything changes.",
    "And what comes next will surprise you.",
]

CONCLUSIONS_FR = [
    "Si tu as appris quelque chose, commente en bas.",
    "Partage cette vidéo si ça t'a surpris.",
    "Maintenant tu connais la vérité. Abonne-toi pour la suite.",
    "Dis-moi en commentaire ce que tu en penses.",
]

CONCLUSIONS_EN = [
    "If you learned something new, drop a comment below.",
    "Share this if it surprised you.",
    "Now you know the truth. Subscribe for more.",
    "Let me know in the comments what you think.",
]


def generate_script(topic: str, language: str = "fr", style: str = "viral") -> Script:
    hooks = HOOKS_FR if language == "fr" else HOOKS_EN
    body_pool = BODY_FR if language == "fr" else BODY_EN
    conclusions = CONCLUSIONS_FR if language == "fr" else CONCLUSIONS_EN

    hook = random.choice(hooks).format(topic=topic)
    body = [s.format(topic=topic) for s in random.sample(body_pool, min(5, len(body_pool)))]
    conclusion = random.choice(conclusions)

    return Script(hook=hook, body=body, conclusion=conclusion)
