#OUTPUT_VIDEO = "labeled_output_with_drowsiness.mp4"              # 출력 비디오 파일명
#OUTPUT_CSV = "per_frame_with_drowsiness.csv"              # 출력 CSV 파일명

CALIB_SECONDS = 2.0       # 초기 캘리브레이션 구간(초)
FPS_FALLBACK = 30.0       # FPS 정보가 없을 때 기본값
SMOOTH_WIN = 5            # EAR/MAR 이동평균 윈도우
BLINK_MAX_FRAMES = 8      # blink로 볼 수 있는 최대 닫힘 프레임 길이
YAWN_MIN_FRAMES = 30      # 하품으로 간주할 최소 프레임 길이
HAND_MOUTH_DIST_PX = 80   # 손가락 포인트와 입 중심 간 근접 판정 거리(픽셀)

# 상태 머신 임계치 비율 (캘리브레이션 결과에 곱해 사용)
EYE_CLOSE_RATIO = 0.85    # 눈감김 임계치: EAR_low = median(EAR_calib)*EYE_CLOSE_RATIO
EYE_OPEN_RATIO  = 1.05    # 눈뜸 임계치: EAR_high = median(EAR_calib)*EYE_OPEN_RATIO
MOUTH_YAWN_RATIO = 1.25   # 하품 임계치: MAR_high = median(MAR_calib)*MOUTH_YAWN_RATIO

# 졸림 지표 윈도우(초)
PERCLOS_WIN_SEC = 10.0
RATE_WIN_SEC = 20.0

# 졸림 임계값(튜닝 가능)
PERCLOS_T1, PERCLOS_T2, PERCLOS_T3 = 0.20, 0.40, 0.60
YAWN_T1, YAWN_T2, YAWN_T3 = 2.0, 4.0, 6.0           # per minute
BLINK_DUR_T1, BLINK_DUR_T2, BLINK_DUR_T3 = 0.25, 0.35, 0.50  # seconds
LONG_EC_T1, LONG_EC_T2, LONG_EC_T3 = 0.5, 0.8, 1.0            # seconds

# FaceMesh / Hands 초기화
mp_face = mp.solutions.face_mesh
mp_hands = mp.solutions.hands
mp_draw = mp.solutions.drawing_utils
mp_styles = mp.solutions.drawing_styles

# FaceMesh 눈/입 계산용 랜드마크 인덱스 (MediaPipe FaceMesh)
# EAR: (상하 거리 합) / (좌우 거리)  -- 관례적 정의
LEFT_EYE = [33, 160, 158, 133, 153, 144]   # [left, top1, top2, right, bottom1, bottom2]
RIGHT_EYE = [362, 385, 387, 263, 373, 380]
# MAR: (상하 거리) / (좌우 거리)
MOUTH_HORZ = (61, 291)    # 좌우 외측 입꼬리
MOUTH_VERT = (13, 14)     # 상하(안쪽 입술 중앙)

# 상태 관련 버퍼
ear_buf = deque(maxlen=SMOOTH_WIN)
mar_buf = deque(maxlen=SMOOTH_WIN)

# 상태 머신 상수 (눈 + 하품)
EYE_OPEN, EYE_CLOSE, EYE_OPENING, EYE_CLOSING, EYE_BLINK = range(5)
YAWN_NONE, YAWN_WITH_HAND, YAWN_WITHOUT_HAND = 0, 1, 2

eye_state = EYE_OPEN    # 초기 가정
close_count = 0         # 연속 닫힘 프레임 수(블링크 판정용)
yawn_state = YAWN_NONE
yawn_count = 0

# 캘리브레이션 샘플
EAR_LOW, EAR_HIGH = 0.18, 0.26
MAR_HIGH = 0.60
ear_samples = []
mar_samples = []

# 졸림 지표 계산용 슬라이딩 버퍼 (초 단위 시간축)
closed_flags = deque()   # (t, 0/1) — 눈감김 여부
blink_events = deque()   # (t, duration_sec)
yawn_events  = deque()   # (t,)
active_close_start = None  # 현재 진행 중인 eye-closure 시작시간
active_blink_start = None  # blink용(짧은 닫힘)

# 졸음 단계 색상 팔레트
LEVEL_COLOR = {
    0: (0, 220, 0),     # alert - green
    1: (0, 200, 255),   # mild - orange
    2: (0, 128, 255),   # moderate - darker orange
    3: (0, 0, 255)      # severe - red
}

    # Mild
# 미리 저장된 영상을 사용
video_path = target_files[2]
cap = cv2.VideoCapture(video_path)

OUTPUT_VIDEO = os.path.basename(video_path)              # 출력 비디오 파일명
OUTPUT_VIDEO =  os.path.splitext(OUTPUT_VIDEO)[0] + "-label.mp4"              # 출력 비디오 파일명
OUTPUT_CSV = os.path.splitext(OUTPUT_VIDEO)[0]  + ".csv"            # 출력 CSV 파일명

print(OUTPUT_VIDEO)
print(OUTPUT_CSV)

def get_output_files(video_path):
    """
    주어진 비디오 경로에서 출력 비디오 및 CSV 파일명을 생성합니다.
    """
    base_name = os.path.basename(video_path)
    output_video = os.path.splitext(base_name)[0] + "-label.mp4"
    output_csv = os.path.splitext(output_video)[0] + ".csv"
    return output_video, output_csv

from confluent_kafka import Producer

conf = {
    'bootstrap.servers': 'kafka.dongango.com:9094'
}

# 메시지 전송 후 호출될 콜백 함수 정의
def delivery_report(err, msg):
    """
    Kafka에 메시지를 전송한 뒤, 브로커에서 ACK(확인 응답)를 받으면 호출되는 콜백 함수.
    - err: 전송 실패 시 에러 객체 (None 이면 성공)
    - msg: 전송된 메시지 객체
    """
    if err is not None:
        # 메시지 전송 실패 시 에러 출력
        print(f"Delivery failed: {err}")
    else:
        # 메시지 전송 성공 시, 메시지가 저장된 토픽/파티션/오프셋 정보 출력
        print(f"Message delivered to {msg.topic()} [{msg.partition()}] @ {msg.offset()}")

import re

def sub_text(text):
    """
    주어진 텍스트에서 알파벳, 숫자, 밑줄(_), 하이픈(-), 쉼표(,) 및 점(.)을 제외한 모든 문자를 하이픈(-)으로 대체합니다.
    """
    return re.sub(r"[^a-zA-Z0-9,_\-.]", "-", text)

def label_video(video_path):

    # FaceMesh / Hands 초기화
    mp_face = mp.solutions.face_mesh
    mp_hands = mp.solutions.hands
    mp_draw = mp.solutions.drawing_utils
    mp_styles = mp.solutions.drawing_styles

    # FaceMesh 눈/입 계산용 랜드마크 인덱스 (MediaPipe FaceMesh)
    # EAR: (상하 거리 합) / (좌우 거리)  -- 관례적 정의
    LEFT_EYE = [33, 160, 158, 133, 153, 144]   # [left, top1, top2, right, bottom1, bottom2]
    RIGHT_EYE = [362, 385, 387, 263, 373, 380]
    # MAR: (상하 거리) / (좌우 거리)
    MOUTH_HORZ = (61, 291)    # 좌우 외측 입꼬리
    MOUTH_VERT = (13, 14)     # 상하(안쪽 입술 중앙)

    # 상태 관련 버퍼
    ear_buf = deque(maxlen=SMOOTH_WIN)
    mar_buf = deque(maxlen=SMOOTH_WIN)

    # 상태 머신 상수 (눈 + 하품)
    EYE_OPEN, EYE_CLOSE, EYE_OPENING, EYE_CLOSING, EYE_BLINK = range(5)
    YAWN_NONE, YAWN_WITH_HAND, YAWN_WITHOUT_HAND = 0, 1, 2

    eye_state = EYE_OPEN    # 초기 가정
    close_count = 0         # 연속 닫힘 프레임 수(블링크 판정용)
    yawn_state = YAWN_NONE
    yawn_count = 0

    # 캘리브레이션 샘플
    EAR_LOW, EAR_HIGH = 0.18, 0.26
    MAR_HIGH = 0.60
    ear_samples = []
    mar_samples = []

    # 졸림 지표 계산용 슬라이딩 버퍼 (초 단위 시간축)
    closed_flags = deque()   # (t, 0/1) — 눈감김 여부
    blink_events = deque()   # (t, duration_sec)
    yawn_events  = deque()   # (t,)
    active_close_start = None  # 현재 진행 중인 eye-closure 시작시간
    active_blink_start = None  # blink용(짧은 닫힘)

    # 졸음 단계 색상 팔레트
    LEVEL_COLOR = {
        0: (0, 220, 0),     # alert - green
        1: (0, 200, 255),   # mild - orange
        2: (0, 128, 255),   # moderate - darker orange
        3: (0, 0, 255)      # severe - red
    }

    # 미리 저장된 영상을 사용
    cap = cv2.VideoCapture(video_path)
    output_video, output_csv = get_output_files(video_path)

    # 컴퓨터 연결 카메라 사용, 실시간 웹캠 등
    #cap = cv2.VideoCapture(CAM_INDEX)   

    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 1e-2: fps = FPS_FALLBACK
    width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) if cap.get(cv2.CAP_PROP_FRAME_COUNT)>0 else None

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    outfilePath = "./output/" + output_video
    out = cv2.VideoWriter(outfilePath, fourcc, fps, (width, height))

    logs = []

    ## kafka topic 설정
    kafka_producer = Producer(conf)
    kafka_topic = sub_text(output_video)
    kafka_key = "drowniness_indicator"

    # 캘리브 구간 프레임 수
    calib_frames = int(CALIB_SECONDS * fps)

    # EAR 및 MAR 영역 표시 안함 + 행동상태 라벨링 + 졸림 상태 라벨링(기준 지표 포함) 
    start = time.time()
    with mp_face.FaceMesh(
        static_image_mode=False,
        refine_landmarks=True,
        max_num_faces=1,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5
    ) as face_mesh, mp_hands.Hands(
        static_image_mode=False,
        max_num_hands=2,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5
    ) as hands:

        frame_idx = 0
        while True:
            ret, frame = cap.read()
            if not ret: break
            frame_idx += 1
            t_sec = frame_idx / fps

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            face_res = face_mesh.process(rgb)
            hands_res = None  # 조건부로 돌려도 됨(여기선 항상 실행)

            label_id = 0
            label_str = "eyes_state/open"

            if face_res.multi_face_landmarks:
                face_landmarks = face_res.multi_face_landmarks[0].landmark

                # EAR/MAR
                ear_l = eye_aspect_ratio(face_landmarks, LEFT_EYE, width, height)
                ear_r = eye_aspect_ratio(face_landmarks, RIGHT_EYE, width, height)
                ear = (ear_l + ear_r) / 2.0
                mar, mouth_center = mouth_aspect_ratio(face_landmarks, width, height)

                ear_buf.append(ear)
                mar_buf.append(mar)
                ear_s = moving_avg(ear_buf, SMOOTH_WIN)
                mar_s = moving_avg(mar_buf, SMOOTH_WIN)

                # 캘리브레이션 샘플 수집
                if frame_idx <= int(CALIB_SECONDS * fps):
                    ear_samples.append(ear)
                    mar_samples.append(mar)
                    if frame_idx == int(CALIB_SECONDS * fps):
                        if len(ear_samples) >= 5:
                            ear_med = float(np.median(ear_samples))
                            EAR_LOW  = ear_med * EYE_CLOSE_RATIO
                            EAR_HIGH = ear_med * EYE_OPEN_RATIO
                        if len(mar_samples) >= 5:
                            mar_med = float(np.median(mar_samples))
                            MAR_HIGH = mar_med * MOUTH_YAWN_RATIO

                # 손-입 근접
                hands_res = hands.process(rgb)
                hand_near = is_hand_near_mouth(
                    hands_res.multi_hand_landmarks if hands_res else None,
                    mouth_center, HAND_MOUTH_DIST_PX, width, height
                )

                # 눈 상태 머신
                prev_state = eye_state
                if ear_s is None:
                    eye_state = EYE_OPEN
                else:
                    if len(ear_buf) >= 3:
                        ear_deriv = ear_buf[-1] - ear_buf[-3]
                    else:
                        ear_deriv = 0.0

                    is_closed = ear_s < EAR_LOW
                    is_opened = ear_s > EAR_HIGH

                    if is_closed:
                        eye_state = EYE_CLOSE if prev_state == EYE_CLOSE else (EYE_CLOSING if ear_deriv < 0 else EYE_CLOSE)
                        close_count += 1
                    elif is_opened:
                        eye_state = EYE_OPEN if prev_state == EYE_OPEN else (EYE_OPENING if ear_deriv > 0 else EYE_OPEN)
                        # blink 판정
                        if 0 < close_count <= BLINK_MAX_FRAMES:
                            eye_state = EYE_BLINK
                        close_count = 0
                    else:
                        eye_state = EYE_OPENING if ear_deriv > 0 else (EYE_CLOSING if ear_deriv < 0 else prev_state)
                        if prev_state in (EYE_CLOSE, EYE_CLOSING):
                            close_count += 1
                        else:
                            close_count = 0

                # 하품 상태
                if mar_s is not None and mar_s > MAR_HIGH:
                    yawn_count += 1
                    yawn_state = YAWN_WITH_HAND if hand_near else YAWN_WITHOUT_HAND
                else:
                    yawn_state = YAWN_NONE
                    yawn_count = 0

                # 최종 행동 라벨
                if yawn_state != YAWN_NONE and yawn_count >= YAWN_MIN_FRAMES:
                    if yawn_state == YAWN_WITH_HAND:
                        label_id, label_str = 5, "yawning/Yawning with hand"
                    else:
                        label_id, label_str = 6, "yawning/Yawning without hand"
                else:
                    if   eye_state == EYE_OPEN:    label_id, label_str = 0, "eyes_state/open"
                    elif eye_state == EYE_CLOSE:   label_id, label_str = 1, "eyes_state/close"
                    elif eye_state == EYE_OPENING: label_id, label_str = 2, "eyes_state/opening"
                    elif eye_state == EYE_CLOSING: label_id, label_str = 3, "eyes_state/closing"
                    elif eye_state == EYE_BLINK:   label_id, label_str = 4, "blinks/blinking"

                # ====== 졸림 지표 업데이트 ======
                # A) PERCLOS: 최근 PERCLOS_WIN_SEC 동안 '눈감김' 비율
                closed_flag = 1 if ear_s is not None and ear_s < EAR_LOW else 0
                closed_flags.append((t_sec, closed_flag))
                while closed_flags and (t_sec - closed_flags[0][0] > PERCLOS_WIN_SEC):
                    closed_flags.popleft()
                if closed_flags:
                    perclos = sum(f for _, f in closed_flags) / float(len(closed_flags))
                else:
                    perclos = None

                # B) blink 이벤트 기록(짧은 닫힘)
                # blink가 찍히는 순간(eye_state == EYE_BLINK)에서 duration 계산
                # 간단히: 방금 전까지의 close_count를 duration으로 사용
                if eye_state == EYE_BLINK:
                    blink_dur = close_count / fps  # 방금 열림과 함께 close_count가 0으로 초기화되기 전에 계산됨
                    blink_events.append((t_sec, blink_dur))
                # 창구 유지
                while blink_events and (t_sec - blink_events[0][0] > RATE_WIN_SEC):
                    blink_events.popleft()

                if blink_events:
                    blink_rate = len(blink_events) * (60.0 / RATE_WIN_SEC)  # per 20s
                    avg_blink_dur = float(np.mean([d for _, d in blink_events]))
                else:
                    blink_rate = 0.0
                    avg_blink_dur = None

                # C) 긴 eye-closure 감지(연속 close가 길면 이벤트로 기록)
                # close 연속 구간의 시작/끝 추적
                if closed_flag == 1 and active_close_start is None:
                    active_close_start = t_sec
                if closed_flag == 0 and active_close_start is not None:
                    dur = t_sec - active_close_start
                    blink_events.append((t_sec, dur))  # 긴 eye closure도 blink_events에 포함시켜 평균/최대에 반영
                    active_close_start = None
                # longest eye closure (최근 RATE_WIN_SEC)
                if blink_events:
                    longest_ec = max(d for _, d in blink_events)
                else:
                    longest_ec = None

                # D) yawn 이벤트(프레임 지속 충족 시 시점 기록)
                if yawn_state != YAWN_NONE and yawn_count == YAWN_MIN_FRAMES:
                    yawn_events.append((t_sec,))
                while yawn_events and (t_sec - yawn_events[0][0] > RATE_WIN_SEC):
                    yawn_events.popleft()
                yawn_rate = len(yawn_events) * (60.0 / RATE_WIN_SEC) if yawn_events else 0.0

                # ====== 졸림 단계 산출 ======
                d_level, d_label = drowsiness_level(perclos, yawn_rate, avg_blink_dur, longest_ec)

                # ====== 시각화 ======
                cv2.putText(frame, f"Label {label_id}: {label_str}", (20, 40),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 200, 255), 2)
                if ear_s is not None:
                    cv2.putText(frame, f"EAR:{ear_s:.3f} (L:{EAR_LOW:.3f} H:{EAR_HIGH:.3f})",
                                (20, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0), 2)
                if mar_s is not None:
                    cv2.putText(frame, f"MAR:{mar_s:.3f} (Y>{MAR_HIGH:.3f})",
                                (20, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,200,0), 2)

                # 졸림 지표/단계 표시
                c = LEVEL_COLOR[d_level]
                cv2.putText(frame, f"Drowsiness {d_level}: {d_label}", (20, 135),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.9, c, 2)
                cv2.putText(frame, f"PERCLOS:{(perclos if perclos is not None else np.nan):.2f}  "
                                    f"Yawn/min:{yawn_rate:.1f}  "
                                    f"Blink/min:{blink_rate:.1f}  "
                                    f"AvgBlinkDur:{(avg_blink_dur if avg_blink_dur else np.nan):.2f}s  "
                                    f"LongestEC:{(longest_ec if longest_ec else np.nan):.2f}s",
                            (20, 165), cv2.FONT_HERSHEY_SIMPLEX, 0.55, c, 2)

            else:
                # 얼굴 미검출 시
                label_id, label_str = 0, "eyes_state/open"
                d_level, d_label = 0, "alert"
                perclos = None; yawn_rate = 0.0; blink_rate = 0.0; avg_blink_dur = None; longest_ec = None
                cv2.putText(frame, "Face not detected", (20, 40),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)

            drowny_data = json.dumps({
                "frame": frame_idx,
                "time_sec": t_sec,
                "label_id": label_id,
                "label_name": label_str,
                "EAR": float(ear_buf[-1]) if len(ear_buf) > 0 else np.nan,
                "MAR": float(mar_buf[-1]) if len(mar_buf) > 0 else np.nan,
                "yawn_rate_per_min": float(yawn_rate),
                "blink_rate_per_min": float(blink_rate) if face_res.multi_face_landmarks else 0.0,
                "avg_blink_dur_sec": float(avg_blink_dur) if avg_blink_dur is not None else np.nan,
                "longest_eye_closure_sec": float(longest_ec) if longest_ec is not None else np.nan,
                "drowsiness_level": d_level,
                "drowsiness_label": d_label
            }, ensure_ascii=False)

            # ====== 로그 저장 ======
            logs.append({
                "frame": frame_idx,
                "time_sec": t_sec,
                "label_id": label_id,
                "label_name": label_str,
                "EAR": float(ear_buf[-1]) if len(ear_buf)>0 else np.nan,
                "MAR": float(mar_buf[-1]) if len(mar_buf)>0 else np.nan,
                "yawn_rate_per_min": float(yawn_rate),
                "blink_rate_per_min": float(blink_rate) if face_res.multi_face_landmarks else 0.0,
                "avg_blink_dur_sec": float(avg_blink_dur) if avg_blink_dur is not None else np.nan,
                "longest_eye_closure_sec": float(longest_ec) if longest_ec is not None else np.nan,
                "drowsiness_level": d_level,
                "drowsiness_label": d_label
            })

            # Kafka 메시지 전송
            producer.produce(kafka_topic, key=kafka_key, value=drowny_data, callback=delivery_report)
            producer.flush()

            out.write(frame)

    cap.release()
    out.release()
    cv2.destroyAllWindows()

    pd.DataFrame(logs).to_csv("./output/"+output_csv, index=False)
    print(f"Saved video: {output_video}")
    print(f"Saved CSV:   {output_csv}")
    print(f"{time.time()-start:.4f} sec")