from rpi_ws281x import PixelStrip, Color
import RPi.GPIO as GPIO
import time
import threading
import random

# =========================
# Cloud Mood Lamp
# Emotion LED + Vibration Test
# =========================

# NeoPixel LED settings
LED_COUNT = 60
LED_PIN = 10          # GPIO10 = physical pin 19
LED_FREQ_HZ = 800000
LED_DMA = 10
LED_BRIGHTNESS = 35   # 0~255. 너무 밝으면 20~40 추천
LED_INVERT = False
LED_CHANNEL = 0

# DRV8833 vibration motor settings
VIB_AIN1 = 23         # GPIO23 = physical pin 16
VIB_AIN2 = 24         # GPIO24 = physical pin 18
PWM_FREQ = 100

# LED strip setup
strip = PixelStrip(
    LED_COUNT,
    LED_PIN,
    LED_FREQ_HZ,
    LED_DMA,
    LED_INVERT,
    LED_BRIGHTNESS,
    LED_CHANNEL
)
strip.begin()

# GPIO setup
GPIO.setmode(GPIO.BCM)
GPIO.setup(VIB_AIN1, GPIO.OUT)
GPIO.setup(VIB_AIN2, GPIO.OUT)

# One direction only
GPIO.output(VIB_AIN2, GPIO.LOW)
vib_pwm = GPIO.PWM(VIB_AIN1, PWM_FREQ)
vib_pwm.start(0)


# =========================
# Basic control functions
# =========================

def clear_leds():
    """Turn off all LEDs."""
    for i in range(LED_COUNT):
        strip.setPixelColor(i, Color(0, 0, 0))
    strip.show()


def set_all_leds(color):
    """Set all LEDs to one color."""
    for i in range(LED_COUNT):
        strip.setPixelColor(i, color)
    strip.show()


def make_scaled_color(r, g, b, percent):
    """Make brightness-scaled Color."""
    percent = max(0, min(100, percent)) / 100
    return Color(int(r * percent), int(g * percent), int(b * percent))


def stop_vibration():
    """Stop vibration motor."""
    vib_pwm.ChangeDutyCycle(0)
    GPIO.output(VIB_AIN2, GPIO.LOW)


def vibrate(strength, duration):
    """
    Vibrate motor.
    strength: 0~100
    duration: seconds
    """
    strength = max(0, min(100, strength))
    vib_pwm.ChangeDutyCycle(strength)
    time.sleep(duration)
    vib_pwm.ChangeDutyCycle(0)


def run_together(led_function, vibration_function):
    """Run LED and vibration at the same time."""
    led_thread = threading.Thread(target=led_function)
    vib_thread = threading.Thread(target=vibration_function)

    led_thread.start()
    vib_thread.start()

    led_thread.join()
    vib_thread.join()

    stop_vibration()


# =========================
# LED effect functions
# =========================

def breathe_rgb(r, g, b, cycles=3, delay=0.04):
    """
    One color softly fades in and out.
    구름 무드등처럼 은은하게 숨 쉬는 효과.
    """
    for _ in range(cycles):
        # Fade in
        for brightness in range(0, 101, 4):
            color = make_scaled_color(r, g, b, brightness)
            set_all_leds(color)
            time.sleep(delay)

        # Fade out
        for brightness in range(100, -1, -4):
            color = make_scaled_color(r, g, b, brightness)
            set_all_leds(color)
            time.sleep(delay)


def hold_rgb(r, g, b, duration=3):
    """
    One color stays on.
    """
    set_all_leds(Color(r, g, b))
    time.sleep(duration)


def lightning_effect(duration=4):
    """
    Angry effect:
    random white flashes like lightning.
    """
    clear_leds()
    start = time.time()

    while time.time() - start < duration:
        # 어두운 상태 유지
        clear_leds()
        time.sleep(random.uniform(0.08, 0.35))

        # 무작위 LED 일부만 흰색으로 번쩍
        flash_count = random.randint(5, 20)

        for _ in range(flash_count):
            led_index = random.randint(0, LED_COUNT - 1)
            strip.setPixelColor(led_index, Color(255, 255, 255))

        strip.show()
        time.sleep(random.uniform(0.03, 0.12))

        # 가끔 전체가 짧게 번쩍
        if random.random() < 0.35:
            set_all_leds(Color(255, 255, 255))
            time.sleep(random.uniform(0.03, 0.08))

        clear_leds()


# =========================
# Vibration patterns
# =========================

def vib_soft():
    for _ in range(2):
        vibrate(25, 0.18)
        time.sleep(0.25)


def vib_tap():
    for _ in range(4):
        vibrate(45, 0.12)
        time.sleep(0.14)


def vib_nervous():
    for _ in range(6):
        vibrate(random.randint(25, 55), random.uniform(0.05, 0.18))
        time.sleep(random.uniform(0.06, 0.2))


def vib_strong_short():
    for _ in range(5):
        vibrate(75, 0.1)
        time.sleep(0.08)


def vib_none():
    time.sleep(0.5)


# =========================
# Emotion effects
# =========================

def effect_happy():
    """
    행복:
    살짝 주황빛이 도는 노란색
    """
    def led_part():
        breathe_rgb(255, 180, 25, cycles=3, delay=0.035)

    def vib_part():
        vib_tap()

    run_together(led_part, vib_part)


def effect_sad():
    """
    슬픔:
    파란색
    """
    def led_part():
        breathe_rgb(20, 80, 255, cycles=3, delay=0.055)

    def vib_part():
        vib_soft()

    run_together(led_part, vib_part)


def effect_anxious():
    """
    불안:
    살짝 붉은빛이 도는 주황색
    """
    def led_part():
        breathe_rgb(255, 85, 20, cycles=4, delay=0.035)

    def vib_part():
        vib_nervous()

    run_together(led_part, vib_part)


def effect_angry():
    """
    화남:
    무작위 흰색 번쩍임, 번개 치는 듯한 효과
    """
    def led_part():
        lightning_effect(duration=4)

    def vib_part():
        vib_strong_short()

    run_together(led_part, vib_part)


def effect_shy():
    """
    부끄러움:
    핑크
    """
    def led_part():
        breathe_rgb(255, 70, 150, cycles=3, delay=0.045)

    def vib_part():
        vib_soft()

    run_together(led_part, vib_part)


def effect_bored():
    """
    따분함:
    남색
    """
    def led_part():
        breathe_rgb(10, 20, 120, cycles=3, delay=0.07)

    def vib_part():
        vib_none()

    run_together(led_part, vib_part)


def effect_timid():
    """
    소심함:
    보라
    """
    def led_part():
        breathe_rgb(130, 40, 220, cycles=3, delay=0.055)

    def vib_part():
        vib_soft()

    run_together(led_part, vib_part)


def effect_prickly():
    """
    까칠함:
    초록
    """
    def led_part():
        # 살짝 날카로운 느낌이 나도록 초록색을 짧게 깜빡
        for _ in range(6):
            set_all_leds(Color(0, 180, 60))
            time.sleep(0.18)
            clear_leds()
            time.sleep(0.08)

    def vib_part():
        for _ in range(3):
            vibrate(50, 0.1)
            time.sleep(0.18)

    run_together(led_part, vib_part)


def effect_envy():
    """
    부러움:
    청록
    """
    def led_part():
        breathe_rgb(0, 200, 180, cycles=3, delay=0.045)

    def vib_part():
        vib_soft()

    run_together(led_part, vib_part)


# =========================
# Menu
# =========================

def show_menu():
    print()
    print("=================================")
    print("Cloud Mood Lamp Emotion Test")
    print("---------------------------------")
    print("행복 / happy      : 주황빛 노란색")
    print("슬픔 / sad        : 파란색")
    print("불안 / anxious    : 붉은빛 주황색")
    print("화남 / angry      : 흰색 번개 효과")
    print("부끄러움 / shy    : 핑크")
    print("따분함 / bored    : 남색")
    print("소심함 / timid    : 보라")
    print("까칠함 / prickly  : 초록")
    print("부러움 / envy     : 청록")
    print("---------------------------------")
    print("off               : LED와 진동 끄기")
    print("quit              : 종료")
    print("=================================")


try:
    clear_leds()
    stop_vibration()

    print("Cloud mood lamp emotion test started.")

    while True:
        show_menu()
        emotion = input("Emotion > ").strip().lower()

        if emotion in ["행복", "happy"]:
            effect_happy()

        elif emotion in ["슬픔", "sad"]:
            effect_sad()

        elif emotion in ["불안", "anxious"]:
            effect_anxious()

        elif emotion in ["화남", "angry"]:
            effect_angry()

        elif emotion in ["부끄러움", "shy"]:
            effect_shy()

        elif emotion in ["따분함", "bored"]:
            effect_bored()

        elif emotion in ["소심함", "timid"]:
            effect_timid()

        elif emotion in ["까칠함", "prickly"]:
            effect_prickly()

        elif emotion in ["부러움", "envy"]:
            effect_envy()

        elif emotion == "off":
            clear_leds()
            stop_vibration()
            print("LED and vibration off.")

        elif emotion == "quit":
            print("Exit emotion test.")
            break

        else:
            print("Unknown emotion.")
            print("아래 중 하나를 입력하세요:")
            print("행복, 슬픔, 불안, 화남, 부끄러움, 따분함, 소심함, 까칠함, 부러움")
            print("또는 happy, sad, anxious, angry, shy, bored, timid, prickly, envy")

except KeyboardInterrupt:
    print("\nStopped by user.")

finally:
    clear_leds()
    stop_vibration()
    vib_pwm.stop()
    GPIO.cleanup()
    print("Cleaned up. LED off. Vibration off.")