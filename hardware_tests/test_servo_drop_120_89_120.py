import RPi.GPIO as GPIO
import time

# =========================
# Cloud Mood Lamp
# Servo Drop Test
# 120도 → 89도 → 바로 120도 복귀
# =========================

# 물리 핀 11번 = BCM GPIO17
SERVO_PIN = 17

# 드롭 동작 각도
READY_ANGLE = 120
DROP_ANGLE = 89

# 서보가 89도까지 실제로 움직일 시간
# 너무 짧으면 89도까지 못 가고, 너무 길면 구슬이 2개 떨어질 수 있음
MOVE_TO_DROP_TIME = 0.15

# 89도에서 따로 멈춰있는 시간
# 딜레이 없이 바로 복귀할 거라 0
HOLD_AT_DROP_TIME = 0.0

# 120도로 돌아오는 시간
RETURN_TIME = 0.18


GPIO.setmode(GPIO.BCM)
GPIO.setup(SERVO_PIN, GPIO.OUT)

# 일반 서보모터는 50Hz PWM 사용
pwm = GPIO.PWM(SERVO_PIN, 50)
pwm.start(0)


def angle_to_duty(angle):
    """
    서보 각도를 PWM duty cycle로 변환.
    대부분의 SG90 / MG90S 계열 서보에서 사용 가능.
    """
    return 2.5 + (angle / 18.0)


def set_angle(angle, move_time):
    """
    서보를 특정 각도로 이동.
    """
    duty = angle_to_duty(angle)

    print(f"서보 이동: {angle}도")
    pwm.ChangeDutyCycle(duty)

    time.sleep(move_time)

    # 신호를 끊어서 서보 떨림 줄이기
    pwm.ChangeDutyCycle(0)


def drop_one_bead():
    """
    구슬 1개 드롭 명령:
    120도 → 89도 → 바로 120도 복귀
    """
    print()
    print("=================================")
    print("구슬 1개 드롭 동작 시작")
    print("---------------------------------")
    print("120도 → 89도 → 바로 120도 복귀")
    print("=================================")

    # 1. 기본 대기 위치 120도
    set_angle(READY_ANGLE, 0.25)

    # 2. 구슬을 떨어뜨리는 위치 89도
    set_angle(DROP_ANGLE, MOVE_TO_DROP_TIME)

    # 3. 89도에서 기다리지 않고 바로 복귀
    if HOLD_AT_DROP_TIME > 0:
        time.sleep(HOLD_AT_DROP_TIME)

    # 4. 다시 120도로 복귀
    set_angle(READY_ANGLE, RETURN_TIME)

    print("구슬 1개 드롭 동작 완료")


try:
    print("Servo Drop Test")
    print("서보 신호선: 물리 핀 11번 / GPIO17")
    print("Enter를 누르면 120도 → 89도 → 120도 동작을 실행합니다.")
    print("종료하려면 q 입력")

    # 시작할 때 120도 기준 위치로 먼저 이동
    print()
    print("초기 위치를 120도로 맞춥니다.")
    set_angle(READY_ANGLE, 0.5)

    while True:
        command = input("\nEnter = 드롭 / q = 종료 > ").strip().lower()

        if command == "q":
            print("테스트 종료")
            break

        drop_one_bead()

except KeyboardInterrupt:
    print()
    print("사용자가 테스트를 중지했습니다.")

finally:
    pwm.stop()
    GPIO.cleanup()
    print("GPIO 정리 완료")