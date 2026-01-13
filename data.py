from ultralytics import YOLO
from roboflow import Roboflow

rf = Roboflow(api_key="lNg1MghgSeaYiTi4PjZL")
project = rf.workspace("llllo").project("9.elderly-users-qryyj")
version = project.version(1)
dataset = version.download("yolov11")

# 다운로드가 완료되면 데이터셋이 저장된 경로가 dataset.location에 담깁니다.
print(f"데이터셋 저장 경로: {dataset.location}")
# 1. 모델 불러오기 (nano 버전 예시)
model = YOLO('yolo11n-pose.pt')

# 2. Roboflow 데이터로 학습 실행
# data 인자에 다운로드 받은 데이터셋 경로 내부의 'data.yaml'을 지정합니다.
model.train(
    data=f"{dataset.location}/data.yaml",  # Roboflow가 만들어준 yaml 파일 경로
    epochs=10,
    imgsz=640,
    plots=True,
    task='detect'
)