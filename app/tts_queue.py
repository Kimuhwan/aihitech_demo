# app/tts_queue.py
import asyncio
import traceback

_queue: asyncio.Queue[str] = asyncio.Queue()
_worker_task: asyncio.Task | None = None

# 상태 관측용
last_error: str | None = None
last_spoken_at: float | None = None
spoken_count: int = 0

async def enqueue_tts(text: str):
    await _queue.put(text)

def queue_size() -> int:
    return _queue.qsize()

def start_tts_worker():
    global _worker_task
    if _worker_task and not _worker_task.done():
        return
    _worker_task = asyncio.create_task(_worker_loop())

async def _worker_loop():
    global last_error, last_spoken_at, spoken_count
    while True:
        text = await _queue.get()
        try:
            # 여기서 실제 pyttsx3 speak 실행
            await _speak(text)  # 네가 만든 안전 speak(스레드/직렬 처리)로 연결
            spoken_count += 1
            last_spoken_at = asyncio.get_event_loop().time()
            last_error = None
        except Exception:
            last_error = traceback.format_exc()
        finally:
            _queue.task_done()
