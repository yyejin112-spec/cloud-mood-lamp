import RPi.GPIO as GPIO
import time
import json
from pathlib import Path

# =========================
# Cloud Mood Lamp
# Servo Toggle Drop Test
# =========================
# 구조:
# 1번째 배출: 0도 -> 180도
# 2번째 배출: 180도 -> 0도
# 3번째 배출: 0도 -> 180도
# 이런 식으로 매번 반대 방향으로 180도 회전
# =========================

SERVO_PIN = 17  # GPIO17 = 물리 핀 11번

# 서보 각도 설정
# 실제 구조에서 끝까지 무리하면 0/180 대신 10/170으로 바꿔도 됨
ANGLE_A = 0
ANGLE_B = 180

# 서보가 움직일 시간
MOVE_TIME = 0.8

# 움직인 뒤 신호를 끊기 전 대기 시간
SETTLE_TIME = 0.3

# 현재 서보 위치를 저장할 파일
STATE_FILE = Path("state/servo_state.json")


# =========================
# GPIO setup
# =========================

GPIO.setmode(GPIO.BCM)
GPIO.setup(SERVO_PIN, GPIO.OUT)

# 일반 서보는 50Hz PWM 사용
pwm = GPIO.PWM(SERVO_PIN, 50)
pwm.start(0)


def angle_to_duty(angle):
    """
    각도를 PWM duty 값으로 변환.
    일반적인 SG90/MG90S 서보 기준.
    """
    return 2.5 + (angle / 18.0)


def set_angle(angle):
    """
    서보를 특정 각도로 이동.
    """
    duty = angle_to_duty(angle)

    print(f"서보 이동: {angle}도")
    pwm.ChangeDutyCycle(duty)

    # 서보가 실제로 이동할 시간
    time.sleep(MOVE_TIME)

    # 떨림을 줄이기 위해 PWM 신호 잠깐 끔
    pwm.ChangeDutyCycle(0)

    time.sleep(SETTLE_TIME)


def load_state():
    """
    마지막 서보 위치를 파일에서 불러옴.
    파일이 없으면 ANGLE_A에서 시작.
    """
    if not STATE_FILE.exists():
        return {"current_angle": ANGLE_A, "drop_count": 0}

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if "current_angle" not in data:
            data["current_angle"] = ANGLE_A

        if "drop_count" not in data:
            data["drop_count"] = 0

        return data

    except Exception:
        return {"current_angle": ANGLE_A, "drop_count": 0}


def save_state(state):
    """
    현재 서보 위치를 파일에 저장.
    """
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def get_next_angle(current_angle):
    """
    현재 각도의 반대쪽 각도를 반환.
    """
    if current_angle == ANGLE_A:
        return ANGLE_B
    else:
        return ANGLE_A


def drop_one_bead():
    """
    구슬 하나 배출 테스트.
    현재 위치에서 반대쪽으로 180도 회전.
    """
    state = load_state()

    current_angle = state["current_angle"]
    next_angle = get_next_angle(current_angle)

    print()
    print("=================================")
    print("구슬 1개 배출 테스트")
    print("---------------------------------")
    print(f"현재 위치: {current_angle}도")
    print(f"이동할 위치: {next_angle}도")
    print("=================================")

    set_angle(next_angle)

    state["current_angle"] = next_angle
    state["drop_count"] += 1
    save_state(state)

    print()
    print(f"배출 동작 완료. 총 테스트 횟수: {state['drop_count']}")
    print(f"현재 저장된 서보 위치: {state['current_angle']}도")


def reset_to_angle_a():
    """
    서보 위치를 ANGLE_A로 초기화.
    구조 조립 전에 기준 위치를 맞출 때 사용.
    """
    print()
    print(f"서보를 초기 위치 {ANGLE_A}도로 이동합니다.")
    set_angle(ANGLE_A)

    state = {
        "current_angle": ANGLE_A,
        "drop_count": 0
    }
    save_state(state)

    print("초기화 완료")


def show_menu():
    print()
    print("=================================")
    print("Servo Toggle Drop Test")
    print("---------------------------------")
    print("Enter : 구슬 1개 배출 동작")
    print("r     : 서보 위치를 0도로 초기화")
    print("s     : 현재 저장 상태 확인")
    print("q     : 종료")
    print("=================================")


try:
    print("서보 토글 배출 테스트 시작")
    print("처음 조립 전에는 r을 눌러 0도 기준 위치를 먼저 맞추세요.")

    while True:
        show_menu()
        command = input("입력 > ").strip().lower()

        if command == "":
            drop_one_bead()

        elif command == "r":
            reset_to_angle_a()

        elif command == "s":
            state = load_state()
            print()
            print("현재 저장 상태:")
            print(f"- current_angle: {state['current_angle']}도")
            print(f"- drop_count: {state['drop_count']}회")

        elif command == "q":
            print("테스트 종료")
            break

        else:
            print("알 수 없는 입력입니다.")
            print("Enter, r, s, q 중 하나를 입력하세요.")

except KeyboardInterrupt:
    print()
    print("사용자가 테스트를 중지했습니다.")

finally:
    pwm.stop()
    GPIO.cleanup()
    print("GPIO 정리 완료")