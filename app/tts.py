# app/tts.py
import asyncio
import pyttsx3

_tts_queue: asyncio.Queue[str] | None = None
_tts_task: asyncio.Task | None = None
_engine = None

def _get_engine():
    global _engine
    if _engine is None:
        _engine = pyttsx3.init("sapi5")
    return _engine

def speak_blocking(text: str):
    e = _get_engine()
    e.say(text)
    e.runAndWait()

async def tts_worker():
    assert _tts_queue is not None
    while True:
        text = await _tts_queue.get()
        try:
            await asyncio.to_thread(speak_blocking, text)
        finally:
            _tts_queue.task_done()

def start_tts():
    global _tts_queue, _tts_task
    if _tts_queue is None:
        _tts_queue = asyncio.Queue()
    if _tts_task is None or _tts_task.done():
        _tts_task = asyncio.create_task(tts_worker())

async def enqueue_tts(text: str):
    if _tts_queue is None:
        start_tts()
    await _tts_queue.put(text)
