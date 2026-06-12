import RPi.GPIO as GPIO
import time

# =========================
# Cloud Mood Lamp
# Servo Bead Drop Test
# 물리핀 11번 / GPIO17
# 45도 → 작은 각도만 열기 → 바로 45도 복귀
# =========================

# 물리 핀 11번 = BCM GPIO17
SERVO_PIN = 17

# 기본 대기 각도
READY_ANGLE = 45

# 구슬 배출 각도
# 2개씩 떨어지면 이 값을 줄이기
# 추천 테스트: 60 → 65 → 70 → 75 → 80
DROP_ANGLE = 65

# 45도에서 DROP_ANGLE까지 이동할 시간
# 너무 길면 2개가 떨어질 수 있음
MOVE_TO_DROP_TIME = 0.18

# DROP_ANGLE에서 기다리는 시간
# 딜레이 없이 바로 복귀할 거라 0
HOLD_AT_DROP_TIME = 0.0

# 다시 45도로 돌아오는 시간
RETURN_TIME = 0.22

GPIO.setmode(GPIO.BCM)
GPIO.setup(SERVO_PIN, GPIO.OUT)

# 일반 서보는 50Hz
pwm = GPIO.PWM(SERVO_PIN, 50)
pwm.start(0)


def angle_to_duty(angle):
    """
    각도를 PWM duty cycle로 변환.
    대부분 SG90 / MG90S 서보 기준.
    """
    return 2.5 + (angle / 18.0)


def set_angle(angle, move_time):
    duty = angle_to_duty(angle)

    print(f"서보 이동: {angle}도")
    pwm.ChangeDutyCycle(duty)

    time.sleep(move_time)

    # 서보 떨림 줄이기
    pwm.ChangeDutyCycle(0)


def drop_one_bead():
    print()
    print("=================================")
    print("구슬 1개 드롭 테스트")
    print("---------------------------------")
    print(f"{READY_ANGLE}도 → {DROP_ANGLE}도 → 바로 {READY_ANGLE}도")
    print("=================================")

    # 1. 대기 위치
    set_angle(READY_ANGLE, 0.15)

    # 2. 조금만 열기
    set_angle(DROP_ANGLE, MOVE_TO_DROP_TIME)

    # 3. 딜레이 없이 바로 복귀
    if HOLD_AT_DROP_TIME > 0:
        time.sleep(HOLD_AT_DROP_TIME)

    # 4. 닫기
    set_angle(READY_ANGLE, RETURN_TIME)

    print("드롭 동작 완료")


try:
    print("Servo Bead Drop Test")
    print("서보 신호선: 물리 핀 11번 / GPIO17")
    print()
    print("Enter = 구슬 1개 드롭 테스트")
    print("q = 종료")
    print()
    print("처음에 서보를 45도로 맞춥니다.")

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