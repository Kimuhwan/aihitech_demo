# app/tts_queue.py
import asyncio
import traceback

import pyttsx3

_queue: asyncio.Queue[str] = asyncio.Queue()
_worker_task: asyncio.Task | None = None

last_error: str | None = None
last_spoken_at: float | None = None
spoken_count: int = 0

_engine = None
_engine_lock = asyncio.Lock()

def _get_engine():
    global _engine
    if _engine is None:
        _engine = pyttsx3.init()
        # _engine.setProperty("rate", 180)  # 필요시
    return _engine

def _speak_blocking(text: str):
    eng = _get_engine()
    eng.say(text)
    eng.runAndWait()

def _speak(text: str):
    engine = pyttsx3.init('sapi5')
    engine.say(text)
    engine.runAndWait()
    engine.stop()

async def enqueue_tts(text: str):
    await _queue.put(text)

def queue_size() -> int:
    return _queue.qsize()

def start_tts_worker():
    global _worker_task
    if _worker_task and not _worker_task.done():
        return
    print("[tts] worker starting")
    _worker_task = asyncio.create_task(_worker_loop())

async def _worker_loop():
    global last_error, last_spoken_at, spoken_count
    print("[tts] worker loop started")
    while True:
        text = await _queue.get()
        print("[tts] dequeued:", text)
        try:
            print("[tts] speaking start")
            await asyncio.to_thread(_speak, text)   # 핵심
            print("[tts] speaking done")

            spoken_count += 1
            last_spoken_at = asyncio.get_running_loop().time()
            last_error = None
            print("[tts] count=", spoken_count)
        except Exception:
            last_error = traceback.format_exc()
            print("[tts] ERROR:", last_error)
        finally:
            spoken_count = 0
            _queue.task_done()
