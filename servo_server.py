from flask import Flask, jsonify
import RPi.GPIO as GPIO
import time

app = Flask(__name__)

# =========================
# Cloud Mood Lamp
# Flask Servo Drop Server
# 앱에서 /drop 요청을 받으면
# 120도 → 88도 → 120도 동작 실행
# =========================

# 물리 핀 11번 = BCM GPIO17
SERVO_PIN = 17

# 드롭 동작 각도
READY_ANGLE = 120
DROP_ANGLE = 88

# 서보 이동 시간
MOVE_TO_DROP_TIME = 0.30
HOLD_AT_DROP_TIME = 1.0
RETURN_TIME = 0.30

is_dropping = False

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
    120도 → 88도 → 120도 복귀
    """
    print()
    print("=================================")
    print("구슬 1개 드롭 동작 시작")
    print("---------------------------------")
    print("120도 → 88도 → 120도 복귀")
    print("=================================")

    # 1. 기본 대기 위치 120도
    set_angle(READY_ANGLE, 0.25)

    # 2. 구슬을 떨어뜨리는 위치 88도
    set_angle(DROP_ANGLE, MOVE_TO_DROP_TIME)

    # 3. 88도에서 잠깐 유지
    if HOLD_AT_DROP_TIME > 0:
        time.sleep(HOLD_AT_DROP_TIME)

    # 4. 다시 120도로 복귀
    set_angle(READY_ANGLE, RETURN_TIME)

    print("구슬 1개 드롭 동작 완료")


@app.route("/")
def home():
    return "Cloud Mood Lamp Raspberry Pi Server is running"


@app.route("/drop", methods=["GET", "POST"])
def drop():
    global is_dropping

    if is_dropping:
        return jsonify({
            "status": "busy",
            "message": "already dropping"
        })

    is_dropping = True

    try:
        drop_one_bead()

        return jsonify({
            "status": "ok",
            "message": "drop released",
            "movement": "120 -> 88 -> 120"
        })

    except Exception as e:
        print("서보 오류:", e)

        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

    finally:
        is_dropping = False


if __name__ == "__main__":
    try:
        print("Cloud Mood Lamp Servo Server")
        print("서보 신호선: 물리 핀 11번 / GPIO17")
        print("초기 위치를 120도로 맞춥니다.")
        set_angle(READY_ANGLE, 0.5)

        app.run(host="0.0.0.0", port=5000)

    except KeyboardInterrupt:
        print()
        print("서버가 중지되었습니다.")

    finally:
        pwm.stop()
        GPIO.cleanup()
        print("GPIO 정리 완료")