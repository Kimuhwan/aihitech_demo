import cv2

print("🔍 연결된 카메라를 찾는 중입니다...")

# 0번부터 4번까지 순서대로 찔러봅니다.
for index in range(5):
    cap = cv2.VideoCapture(index)
    if cap.isOpened():
        print(f"✅ 카메라 발견! 번호: {index}")
        # 잠깐 켰다 끔
        ret, frame = cap.read()
        if ret:
            print(f"✅ [카메라 {index}번] 정상 작동 (해상도: {frame.shape[1]}x{frame.shape[0]})")
        else:
            print(f"⚠️ [카메라 {index}번] 연결은 됐으나 화면이 안 나옴")
        cap.release()
    else:
        print(f"❌ 번호 {index}: 연결된 장치 없음")

print("---------------------------------")
print("👉 '영상 신호 정상'이라고 뜬 번호를 safe_zone.py에 입력하세요.")