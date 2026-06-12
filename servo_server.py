from flask import Flask, jsonify
from gpiozero import AngularServo
from time import sleep

app = Flask(__name__)

# GPIO 18 = 라즈베리파이 물리 핀 12번
servo = AngularServo(
    18,
    min_angle=0,
    max_angle=90,
    min_pulse_width=0.0005,
    max_pulse_width=0.0025
)

is_dropping = False


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
        print("드롭 떨어트리기 시작")

        servo.angle = 0
        sleep(0.3)

        servo.angle = 90
        sleep(0.8)

        servo.angle = 0
        sleep(0.5)

        print("드롭 떨어트리기 완료")

        return jsonify({
            "status": "ok",
            "message": "drop released"
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
    app.run(host="0.0.0.0", port=5000)