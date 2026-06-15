import RPi.GPIO as GPIO
import time

# =========================
# Servo Hold 90 Degree Test
# 물리 핀 11번 = GPIO17
# =========================

SERVO_PIN = 17
HOLD_ANGLE = 88

GPIO.setmode(GPIO.BCM)
GPIO.setup(SERVO_PIN, GPIO.OUT)

# 일반 서보모터는 50Hz PWM 사용
pwm = GPIO.PWM(SERVO_PIN, 50)
pwm.start(0)


def angle_to_duty(angle):
    """
    서보 각도를 duty cycle로 변환.
    일반적인 SG90/MG90S 서보 기준.
    """
    return 2.5 + (angle / 18.0)


try:
    duty = angle_to_duty(HOLD_ANGLE)

    print("=================================")
    print("서보모터 90도 고정 테스트")
    print("---------------------------------")
    print(f"서보 신호선: 물리 핀 11번 / GPIO{SERVO_PIN}")
    print(f"목표 각도: {HOLD_ANGLE}도")
    print("종료하려면 Ctrl + C")
    print("=================================")

    # 90도로 이동
    pwm.ChangeDutyCycle(duty)
    time.sleep(0.5)

    print("서보가 90도 위치를 유지하는 중...")

    # PWM 신호를 계속 보내서 90도 위치 유지
    while True:
        pwm.ChangeDutyCycle(duty)
        time.sleep(0.1)

except KeyboardInterrupt:
    print()
    print("사용자가 테스트를 종료했습니다.")

finally:
    pwm.ChangeDutyCycle(0)
    pwm.stop()
    GPIO.cleanup()
    print("GPIO 정리 완료")