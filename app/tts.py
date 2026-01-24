# app/tts.py
import asyncio
import threading
import queue
import traceback
import pyttsx3

# 상태(디버그용)
spoken_count = 0
last_error: str | None = None
last_spoken_at: float | None = None

# 전용 TTS 스레드로 보낼 큐
_req_q: "queue.Queue[str]" = queue.Queue()
_thread_started = False
_thread_lock = threading.Lock()

def _tts_thread_main():
    global spoken_count, last_error, last_spoken_at

    engine = pyttsx3.init(driverName="sapi5")
    while True:
        text = _req_q.get()
        try:
            # 상태 꼬임 방지
            engine.stop()
            engine.say(text.strip())
            engine.runAndWait()
            engine.stop()

            spoken_count += 1
            last_spoken_at = asyncio.get_event_loop().time() if asyncio.get_event_loop().is_running() else None
            last_error = None
        except Exception:
            last_error = traceback.format_exc()
            print("[tts] ERROR:", last_error)
        finally:
            _req_q.task_done()

def start_tts():
    global _thread_started
    with _thread_lock:
        if _thread_started:
            return
        t = threading.Thread(target=_tts_thread_main, daemon=True)
        t.start()
        _thread_started = True

async def enqueue_tts(text: str):
    if not _thread_started:
        start_tts()
    _req_q.put(text)
