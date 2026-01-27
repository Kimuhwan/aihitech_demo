import torch
from TTS.api import TTS

device = "cuda" if torch.cuda.is_available() else "cpu"
tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)

text_input = "어머니 식사하세요."

tts.tts_to_file(
    text=text_input,
    speaker_wav="winter.wav",
    language="ko",
    file_path="output_tuned.wav",

    # --- 튜닝 옵션 ---
    temperature=0.7,
    repetition_penalty=5.0,
    top_k=50,
    top_p=0.85,
    speed=1.0
)