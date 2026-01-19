# app/tts.py
def speak(text: str) -> None:
    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.say(text)
        engine.runAndWait()
    except Exception:
        # 데모 안정성 위해 TTS 실패해도 서버는 안 죽게
        print("[TTS FAILED]", text)
        raise
