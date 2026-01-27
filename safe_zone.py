import cv2
import time
import math
import numpy as np
import platform
from ultralytics import YOLO

# --- [설정값] ---
# 카메라 번호 설정 (수동 vs 자동)
# - 특정 번호를 강제하고 싶으면 숫자를 적으세요 (예: 0 또는 1)
# - OS에 맞춰서 알아서 잡게 하려면 None 이라고 적으세요.
TARGET_CAMERA_INDEX = None  
# TARGET_CAMERA_INDEX = 1  <-- 내 컴퓨터에서 1번으로 고정하고 싶을 때

# OS에 따라 모델 파일 자동 선택
SYSTEM_OS = platform.system()
MODEL_PATH = "yolo11n-pose.mlpackage" if SYSTEM_OS == "Darwin" else "yolo11n-pose.pt"

# 감지 민감도 설정

FALL_ANGLE_THRESHOLD = 50   # 척추가 50도 이상 기울면 의심
FALL_SPEED_THRESHOLD = 15.0     # 이전 프레임 대비 코(Nose) 위치 변화량이 이보다 크면 '급작스런 낙상'
CONFIRMATION_TIME = 1.0     # 1초 이상 유지 시 최종 낙상 확정

# 테스트를 위해 10초로 설정했습니다. 실제 서비스에선 3600초(1시간) 등으로 늘리세요.
INACTIVITY_THRESHOLD = 10.0 # 10초 동안 움직임 없으면 경고 - 장기 부동(기절) 감지 시간
PRIVACY_MODE = False       # True로 하면 카메라 화면 대신 검은 화면 출력

# --- 전역 변수 ---
# 사람별 상태 저장소: { track_id: { 'start_time': time, 'prev_nose_y': y, 'status': str } }
track_history = {}

# --- 함수 정의 ---

def calculate_spine_angle(shoulder, hip):
    """척추 각도 계산 (수직=0도, 수평=90도)"""
    delta_x = shoulder[0] - hip[0]
    delta_y = shoulder[1] - hip[1]
    if delta_y == 0: return 90 
    return math.degrees(math.atan2(abs(delta_x), abs(delta_y)))

def send_alert(alert_type, track_id):
    """낙상 발생 시 상황별 알림 전송"""
    if alert_type == "FALL":
        print(f"\n🚨 [EMERGENCY] ID {track_id}: 급성 낙상 감지! 구조 요청 필요.\n")
    elif alert_type == "INACTIVITY":
        print(f"\n⚠️ [WARNING] ID {track_id}: 장시간 움직임 없음(기절/수면 의심). 확인 요망.\n")

# --- 메인 실행 ---

print(f"⚡ AI Model Loading... ({MODEL_PATH})")
model = YOLO(MODEL_PATH)

# --- [핵심] 카메라 선택 로직 ---
final_cam_index = 0

if TARGET_CAMERA_INDEX is not None:
    # 1. 사용자가 숫자를 지정했으면 무조건 그 번호 사용
    print(f"🔒 사용자 수동 설정에 따라 {TARGET_CAMERA_INDEX}번 카메라를 사용합니다.")
    final_cam_index = TARGET_CAMERA_INDEX
else:
    # 2. 지정 안 했으면(None), OS별 국룰 번호 사용
    # Mac(Darwin)은 보통 1번, Windows는 0번이 국룰
    if SYSTEM_OS == "Darwin":
        print(f"Mac OS 감지됨 -> 1번 카메라 우선 시도")
        final_cam_index = 1
    else:
        print(f"Windows 감지됨 -> 0번 카메라 우선 시도")
        final_cam_index = 0

# --- 카메라 열기 (Windows 최적화 포함) ---
print(f"📷 카메라 {final_cam_index}번 연결 시도 중...")

if SYSTEM_OS == "Windows":
    # 윈도우는 CAP_DSHOW를 쓰면 호환성과 속도가 좋아짐
    cap = cv2.VideoCapture(final_cam_index, cv2.CAP_DSHOW)
else:
    # 맥/리눅스는 기본 설정 사용
    cap = cv2.VideoCapture(final_cam_index)

# 만약 선택한 카메라가 안 켜지면? (비상 대책)
if not cap.isOpened():
    print(f"⚠️ {final_cam_index}번 실패. 0번으로 재시도합니다.")
    cap = cv2.VideoCapture(0)

if not cap.isOpened():
    print("❌ 카메라 연결 실패. 설정값을 확인해주세요.")
    exit()

window_name = f"AI Fall Detection (Cam {final_cam_index})"
cv2.namedWindow(window_name)

print(f"👉 [시스템 시작] 감지 중... (종료: q)")

while cap.isOpened():
    success, frame = cap.read()
    if not success: break
    
    # 프라이버시 모드 처리
    display_frame = np.zeros_like(frame) if PRIVACY_MODE else frame.copy()

    # 모델 추론
    results = model.track(frame, persist=True, verbose=False)

    for result in results:
        frame = result.plot()
        track_ids = results[0].boxes.id.int().cpu().tolist()
        keypoints = results[0].keypoints.xy.cpu().numpy()
        boxes = results[0].boxes.xyxy.cpu().numpy()
        active_ids = [] # 현재 프레임에 감지된 ID 목록 (사라진 ID 정리용)
        current_nose_y = keypoints[0][1] # 첫 번째 사람의 코 높이 (낙상 속도 계산용)

        for box, track_id, kps in zip(boxes, track_ids, keypoints):
            active_ids.append(track_id)

            # 관절 데이터 유효성 검사 (코, 어깨, 골반 필수)
            # 0:코, 5:왼어깨, 6:오른어깨, 11:왼골반, 12:오른골반
            if np.any(kps[0] == 0) or np.any(kps[5:7] == 0) or np.any(kps[11:13] == 0): continue

            # 좌표 및 데이터 계산
            nose_y = kps[0][1] # 코의 Y좌표 (속도 계산용)
            shoulder_mid = (kps[5] + kps[6]) / 2
            hip_mid = (kps[11] + kps[12]) / 2
            
            spine_angle = calculate_spine_angle(shoulder_mid, hip_mid)
            is_horizontal = spine_angle > FALL_ANGLE_THRESHOLD # 누워있는가?

            # 히스토리 초기화 (처음 등장한 사람)
            if track_id not in track_history:
                track_history[track_id] = {
                    'start_time': None,       # 누워있기 시작한 시간
                    'prev_nose_y': nose_y,    # 이전 프레임의 코 높이
                    'status': 'Normal'        # 상태
                }

            # 속도 계산 (현재 Y - 이전 Y)
            # 값이 클수록 위에서 아래로 빠르게 떨어짐
            data = track_history[track_id]
            fall_speed = nose_y - data['prev_nose_y']
            data['prev_nose_y'] = nose_y # 업데이트

        # --- [판단 로직] ---
            
            x1, y1, x2, y2 = map(int, box)
            color = (0, 255, 0) # 평소 초록색
            status_text = f"Normal ({int(spine_angle)}deg)"

            if is_horizontal:
                # 누워있는 상태가 처음 감지됨 -> 타이머 시작
                if data['start_time'] is None: data['start_time'] = time.time()
                elapsed = time.time() - data['start_time']

                # 급성 낙상 체크 (누웠는데 + 속도가 엄청 빨랐음)
                # 이미 낙상으로 판정된 경우는 계속 유지
                if data['status'] == 'FALL' or fall_speed > FALL_SPEED_THRESHOLD:
                    data['status'] = 'FALL'
                    color = (0, 0, 255) # 빨강
                    status_text = "!!! CRITICAL FALL !!!"
                    if elapsed > CONFIRMATION_TIME: # 잠깐 삐끗한게 아니라면 알림
                        send_alert("FALL", track_id)

                # 장기 부동 체크 (소파/침대 기절)
                # 속도는 느렸지만(스르륵 누움), 너무 오래 누워있음
                elif elapsed > INACTIVITY_THRESHOLD:
                    data['status'] = 'INACTIVITY'
                    color = (0, 165, 255) # 주황
                    status_text = f"Warning: Inactivity {elapsed:.1f}s"
                    send_alert("INACTIVITY", track_id)
                
                # 그냥 누워있는 중 (아직 시간 안됨)
                else:
                    status_text = f"Lying Down.. {elapsed:.1f}s"
            
            else:
                # 다시 일어남 -> 상태 리셋
                data['start_time'] = None
                data['status'] = 'Normal'

            # 시각화
            cv2.rectangle(display_frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(display_frame, status_text, (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            
            # 속도 정보 표시 (디버깅용)
            # cv2.putText(display_frame, f"Speed: {fall_speed:.1f}", (x1, y2+20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        # 화면에서 사라진 ID 데이터 정리
        for tid in list(track_history.keys()):
            if tid not in active_ids: del track_history[tid]

    cv2.imshow(window_name, display_frame)
    if cv2.waitKey(1) & 0xFF == ord('q'): break

cap.release()
cv2.destroyAllWindows()