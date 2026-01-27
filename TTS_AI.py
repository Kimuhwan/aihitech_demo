import torch
from TTS.api import TTS

device = "cuda" if torch.cuda.is_available() else "cpu"
tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)

tts.tts_to_file(
    text="이제 목소리가 좀 더 비슷해졌나요? 설정을 조금 바꾸어 보았습니다.",
    speaker_wav="my_best_sample.wav",
    language="ko",
    file_path="output_tuned.wav",

    # [추가 옵션]
    temperature=0.7,  # (기본값 0.75) 낮을수록 안정적이지만 단조롭고, 높으면 창의적이지만 삑사리가 날 수 있음
    repetition_penalty=2.0,  # (기본값 2.0) 말을 더듬는다면 이 값을 높이세요 (예: 5.0 ~ 10.0)
    speed=1.3  # 속도 조절 (느리게 말하면 더 정확하게 들릴 때가 있음)
)