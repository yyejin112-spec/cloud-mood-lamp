import RPi.GPIO as GPIO
import time

# =========================
# Servo Motor Test
# =========================

SERVO_PIN = 17  # GPIO17 = 물리 핀 11번

GPIO.setmode(GPIO.BCM)
GPIO.setup(SERVO_PIN, GPIO.OUT)

# 서보모터는 보통 50Hz PWM을 사용
pwm = GPIO.PWM(SERVO_PIN, 50)
pwm.start(0)


def set_angle(angle):
    """
    서보모터 각도를 설정하는 함수
    angle: 0 ~ 180
    """
    # 일반적인 서보모터용 duty 값
    duty = 2.5 + (angle / 18.0)

    print(f"Move to {angle} degrees")
    pwm.ChangeDutyCycle(duty)

    # 서보가 움직일 시간을 줌
    time.sleep(0.8)

    # 떨림을 줄이기 위해 신호를 잠깐 끔
    pwm.ChangeDutyCycle(0)
    time.sleep(0.3)


try:
    print("Servo motor test start")
    print("The servo will move: 0 -> 45 -> 90 -> 0")

    set_angle(0)
    time.sleep(1)

    set_angle(45)
    time.sleep(1)

    set_angle(90)
    time.sleep(1)

    set_angle(0)
    time.sleep(1)

    print("Servo motor test done")

except KeyboardInterrupt:
    print("Servo test stopped by user")

finally:
    pwm.stop()
    GPIO.cleanup()
    print("GPIO cleaned up")