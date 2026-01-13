import cv2
from ultralytics import YOLO
import math

# 1. 모델 불러오기
model = YOLO('yolo11n-pose.pt')

# 2. 카메라 켜기
cap = cv2.VideoCapture(0)

# --- [초기 설정 변수] ---
prev_nose_y = 0
frame_counter = 0
fall_detected = False
fall_timer = 0

# ★ 민감도 조절
FALL_THRESHOLD = 30  # (테스트를 위해 50에서 30으로 약간 낮춤)


def calculate_angle(p1, p2):
    x1, y1 = p1
    x2, y2 = p2
    delta_x = x2 - x1
    delta_y = y2 - y1
    angle_rad = math.atan2(abs(delta_y), abs(delta_x))
    angle_deg = math.degrees(angle_rad)
    return angle_deg


while cap.isOpened():
    success, frame = cap.read()
    if not success:
        break

    # 3. AI 추론
    results = model(frame, stream=True, conf=0.5, verbose=False)

    for result in results:
        frame = result.plot()

        if result.keypoints is not None and result.keypoints.xy.numel() > 0:
            keypoints = result.keypoints.xy.cpu().numpy()[0]

            # 주요 관절이 모두 감지되었을 때만 실행
            if (keypoints[0][0] > 0 and keypoints[0][1] > 0 and
                    keypoints[5][0] > 0 and keypoints[6][0] > 0 and
                    keypoints[11][0] > 0 and keypoints[12][0] > 0
            ):
                current_nose_y = keypoints[0][1]

                # --- [수정 1] 속도 계산을 각도 조건문 밖으로 뺐습니다 ---
                falling_speed = 0  # 초기화
                if prev_nose_y != 0:
                    falling_speed = current_nose_y - prev_nose_y

                # 화면에 실시간 속도 표시 (디버깅용)
                cv2.putText(frame, f"Speed: {int(falling_speed)}", (50, 50),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)

                # --- 각도 계산 ---
                shoulder_mid_x = (keypoints[5][0] + keypoints[6][0]) / 2
                shoulder_mid_y = (keypoints[5][1] + keypoints[6][1]) / 2
                hip_mid_x = (keypoints[11][0] + keypoints[12][0]) / 2
                hip_mid_y = (keypoints[11][1] + keypoints[12][1]) / 2

                p_shoulder = (shoulder_mid_x, shoulder_mid_y)
                p_hip = (hip_mid_x, hip_mid_y)

                angle = calculate_angle(p_shoulder, p_hip)

                # 화면에 실시간 각도 표시
                cv2.putText(frame, f"Angle: {int(angle)}", (50, 80),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)

                # --- [수정 2] 복합 낙상 판단 로직 ---
                # 조건: "각도가 낮고(AND) 속도가 빨랐을 때"
                # 또는 "각도가 매우 낮으면(완전히 누움) 조금 덜 빨라도 감지" 등 로직 유연화 가능

                # 여기서는 '동시 충족' 조건을 사용하겠습니다.
                # 주의: 넘어지는 순간 각도는 45도보다 조금 클 수 있으므로 각도 조건을 60도 정도로 완화하거나,
                # 속도와 각도를 각각 체크하는 것이 좋습니다.

                if angle < 50 and falling_speed > FALL_THRESHOLD:
                    fall_detected = True
                    fall_timer = 10

                    # 상태 메시지 업데이트
                if fall_detected or fall_timer > 0:
                    pass  # 아래에서 경고 메시지 출력함
                else:
                    cv2.putText(frame, "Status: Normal", (50, 110),
                                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

                # 현재 위치 업데이트 (다음 프레임 비교용)
                prev_nose_y = current_nose_y

    # --- [경고 메시지 출력 관리] ---
    if fall_timer > 0:
        cv2.putText(frame, "!!! SUDDEN FALL DETECTED !!!", (50, 150),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)
        fall_timer -= 1
    else:
        fall_detected = False

    cv2.imshow("AI Hybrid Fall Detection", frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()