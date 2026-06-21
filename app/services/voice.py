from gtts import gTTS
import os


def generate_voice(text: str, language: str = "fr", output_path: str = "output/voice.mp3") -> str:
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    tts = gTTS(text=text, lang=language, slow=False)
    tts.save(output_path)
    return output_path
