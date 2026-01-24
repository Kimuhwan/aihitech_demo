import cv2
import time
import math
import numpy as np
from ultralytics import YOLO

# --- [설정값] ---
# 아까 터미널에서 만든 CoreML 모델 경로 (없으면 .pt로 변경)
MODEL_PATH = "yolo11n-pose.mlpackage" 
# MODEL_PATH = "yolo11n-pose.pt" 

FALL_ANGLE_THRESHOLD = 50   # 척추가 50도 이상 기울면 의심
CONFIRMATION_TIME = 2.0     # 2초 이상 유지 시 최종 낙상 확정
PRIVACY_MODE = False        # True로 하면 카메라 화면 대신 검은 화면 출력

# --- 전역 변수 (Safe Zone용) ---
safe_zones = []
current_zone = []
drawing = False

# --- 함수 정의 ---

def draw_safe_zone(event, x, y, flags, param):
    """마우스로 안전 구역(침대 등)을 그리는 함수"""
    global current_zone, drawing, safe_zones
    if event == cv2.EVENT_LBUTTONDOWN:
        drawing = True
        current_zone = [(x, y)]
    elif event == cv2.EVENT_MOUSEMOVE and drawing:
        current_zone.append((x, y))
    elif event == cv2.EVENT_LBUTTONUP:
        drawing = False
        if len(current_zone) > 2:
            safe_zones.append(np.array(current_zone, np.int32))
        current_zone = []

def is_in_safe_zone(point, zones):
    """사람의 중심점이 안전 구역 안에 있는지 확인"""
    for zone in zones:
        if cv2.pointPolygonTest(zone, point, False) >= 0:
            return True
    return False

def calculate_spine_angle(shoulder, hip):
    """척추 벡터와 수직선 사이의 각도 계산 (0~90도)"""
    delta_x = shoulder[0] - hip[0]
    delta_y = shoulder[1] - hip[1]
    if delta_y == 0: return 90 
    angle_rad = math.atan2(abs(delta_x), abs(delta_y))
    return math.degrees(angle_rad)

def send_alert():
    """낙상 발생 시 알림 (콘솔 출력 및 확장 가능)"""
    print("\n🚨 [EMERGENCY] 낙상이 감지되었습니다! 보호자에게 연락합니다.\n")

# --- 메인 실행 ---

print(f"⚡ 모델 로딩 중... ({MODEL_PATH})")
# M4 Neural Engine 사용
model = YOLO(MODEL_PATH) 

# 카메라 번호 (사용자 설정에 맞춰 0or1번으로 설정됨)
cap = cv2.VideoCapture(1)

cv2.namedWindow("M4 Advanced Fall Detection")
cv2.setMouseCallback("M4 Advanced Fall Detection", draw_safe_zone)

# 낙상 타이머 저장소 {track_id: start_time}
fall_timers = {}

print("👉 [시작] 마우스로 침대/소파 구역을 그리면 그곳은 감지에서 제외됩니다.")

while cap.isOpened():
    success, frame = cap.read()
    if not success: break
    
    # 프라이버시 모드 처리
    if PRIVACY_MODE:
        display_frame = np.zeros_like(frame)
    else:
        display_frame = frame.copy()

    # 1. Safe Zone 그리기
    for zone in safe_zones:
        cv2.polylines(display_frame, [zone], True, (0, 255, 0), 2)
        cv2.putText(display_frame, "Safe Zone", tuple(zone[0]), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

    if drawing and len(current_zone) > 1:
        cv2.polylines(display_frame, [np.array(current_zone)], False, (0, 255, 255), 1)

    # 2. 모델 추론 (Tracking)
    results = model.track(frame, persist=True, verbose=False)

    if results[0].boxes.id is not None:
        track_ids = results[0].boxes.id.int().cpu().tolist()
        keypoints = results[0].keypoints.xy.cpu().numpy()
        boxes = results[0].boxes.xyxy.cpu().numpy()

        for box, track_id, kps in zip(boxes, track_ids, keypoints):
            # 필수 관절 확인
            if len(kps) < 13 or np.any(kps[5:7] == 0) or np.any(kps[11:13] == 0): 
                continue

            # 좌표 추출
            shoulder_mid = (kps[5] + kps[6]) / 2
            hip_mid = (kps[11] + kps[12]) / 2
            center_point = (int(hip_mid[0]), int(hip_mid[1])) # 몸의 중심(골반)

            # --- [예외 1] Safe Zone 안에 있는가? ---
            if is_in_safe_zone(center_point, safe_zones):
                cv2.circle(display_frame, center_point, 5, (0, 255, 0), -1)
                cv2.putText(display_frame, "Safe Area", (center_point[0]+10, center_point[1]), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
                # 타이머 리셋
                if track_id in fall_timers: del fall_timers[track_id]
                continue 

            # --- [핵심] 척추 각도 분석 ---
            spine_angle = calculate_spine_angle(shoulder_mid, hip_mid)
            is_fallen = spine_angle > FALL_ANGLE_THRESHOLD

            x1, y1, x2, y2 = map(int, box)

            if is_fallen:
                if track_id not in fall_timers:
                    fall_timers[track_id] = time.time() # 타이머 시작
                
                elapsed = time.time() - fall_timers[track_id]
                
                # 시각화 색상 (경고: 주황 -> 확정: 빨강)
                if elapsed > CONFIRMATION_TIME:
                    color = (0, 0, 255) # Red
                    status = "!!! FALL DETECTED !!!"
                    # 알림 전송 (단발성 트리거 로직 추가 가능)
                    if elapsed < CONFIRMATION_TIME + 0.2: send_alert()
                else:
                    color = (0, 165, 255) # Orange
                    status = f"Warning: {elapsed:.1f}s"

                cv2.rectangle(display_frame, (x1, y1), (x2, y2), color, 3)
                cv2.putText(display_frame, status, (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

            else:
                # 정상이면 타이머 리셋
                if track_id in fall_timers: del fall_timers[track_id]
                
                color = (0, 255, 0) # Green
                cv2.rectangle(display_frame, (x1, y1), (x2, y2), color, 2)
                cv2.putText(display_frame, f"Normal ({int(spine_angle)}deg)", (x1, y1-10), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

            # 척추 선 그리기 (디버깅용)
            s_pt = (int(shoulder_mid[0]), int(shoulder_mid[1]))
            h_pt = (int(hip_mid[0]), int(hip_mid[1]))
            cv2.line(display_frame, s_pt, h_pt, color, 2)

    cv2.imshow("M4 Advanced Fall Detection", display_frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()