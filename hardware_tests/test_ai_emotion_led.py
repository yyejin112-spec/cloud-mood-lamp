import sys
from pathlib import Path
import time
import threading
import random
import math

from rpi_ws281x import PixelStrip, Color
import RPi.GPIO as GPIO

# 프로젝트 루트 경로를 Python이 찾을 수 있게 추가
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from src.emotion_ai import classify_emotion


# =========================
# Cloud Mood Lamp
# AI Text → Emotion → LED + Vibration Test
# =========================

# NeoPixel LED settings
LED_COUNT = 60
LED_PIN = 10          # GPIO10 = physical pin 19
LED_FREQ_HZ = 800000
LED_DMA = 10
LED_BRIGHTNESS = 35   # 너무 밝으면 20~40 추천
LED_INVERT = False
LED_CHANNEL = 0

# DRV8833 vibration motor settings
VIB_AIN1 = 23         # GPIO23 = physical pin 16
VIB_AIN2 = 24         # GPIO24 = physical pin 18
PWM_FREQ = 100

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

GPIO.setmode(GPIO.BCM)
GPIO.setup(VIB_AIN1, GPIO.OUT)
GPIO.setup(VIB_AIN2, GPIO.OUT)

GPIO.output(VIB_AIN2, GPIO.LOW)
vib_pwm = GPIO.PWM(VIB_AIN1, PWM_FREQ)
vib_pwm.start(0)


# =========================
# Basic LED functions
# =========================

def clear_leds():
    for i in range(LED_COUNT):
        strip.setPixelColor(i, Color(0, 0, 0))
    strip.show()


def set_all_rgb(r, g, b):
    for i in range(LED_COUNT):
        strip.setPixelColor(i, Color(r, g, b))
    strip.show()


def set_pixel_rgb(index, r, g, b):
    if 0 <= index < LED_COUNT:
        strip.setPixelColor(index, Color(r, g, b))


def scaled_rgb(r, g, b, percent):
    percent = max(0, min(100, percent)) / 100
    return int(r * percent), int(g * percent), int(b * percent)


def set_all_scaled(r, g, b, percent):
    sr, sg, sb = scaled_rgb(r, g, b, percent)
    set_all_rgb(sr, sg, sb)


def rainbow_rgb(pos):
    pos = pos % 256

    if pos < 85:
        return 255 - pos * 3, pos * 3, 0
    elif pos < 170:
        pos -= 85
        return 0, 255 - pos * 3, pos * 3
    else:
        pos -= 170
        return pos * 3, 0, 255 - pos * 3


# =========================
# Vibration functions
# =========================

def stop_vibration():
    vib_pwm.ChangeDutyCycle(0)
    GPIO.output(VIB_AIN2, GPIO.LOW)


def vibrate(strength, duration):
    strength = max(0, min(100, strength))
    vib_pwm.ChangeDutyCycle(strength)
    time.sleep(duration)
    vib_pwm.ChangeDutyCycle(0)


def vib_none():
    time.sleep(0.5)


def vib_soft():
    for _ in range(2):
        vibrate(22, 0.18)
        time.sleep(0.3)


def vib_happy():
    for _ in range(4):
        vibrate(38, 0.1)
        time.sleep(0.13)


def vib_anxious():
    for _ in range(7):
        vibrate(random.randint(25, 55), random.uniform(0.04, 0.16))
        time.sleep(random.uniform(0.04, 0.22))


def vib_angry():
    for _ in range(6):
        vibrate(random.randint(60, 85), random.uniform(0.06, 0.14))
        time.sleep(random.uniform(0.04, 0.16))


def vib_prickly():
    for _ in range(5):
        vibrate(55, 0.07)
        time.sleep(0.09)


def vib_crazy():
    start = time.time()

    while time.time() - start < 5:
        strength = random.randint(20, 90)
        duration = random.uniform(0.03, 0.18)
        vibrate(strength, duration)
        time.sleep(random.uniform(0.02, 0.16))


def run_together(led_function, vibration_function):
    led_thread = threading.Thread(target=led_function)
    vib_thread = threading.Thread(target=vibration_function)

    led_thread.start()
    vib_thread.start()

    led_thread.join()
    vib_thread.join()

    stop_vibration()


# =========================
# Emotion LED Effects
# =========================

def led_happy():
    """
    행복:
    주황빛 노란색 + 불규칙한 반짝임
    """
    start = time.time()

    while time.time() - start < 4.5:
        base_brightness = random.randint(25, 75)
        r, g, b = scaled_rgb(255, 180, 20, base_brightness)
        set_all_rgb(r, g, b)

        for _ in range(random.randint(3, 10)):
            idx = random.randint(0, LED_COUNT - 1)
            set_pixel_rgb(
                idx,
                255,
                random.randint(190, 240),
                random.randint(20, 80)
            )

        strip.show()
        time.sleep(random.uniform(0.04, 0.18))

        if random.random() < 0.45:
            set_all_scaled(255, 180, 20, random.randint(8, 25))
            time.sleep(random.uniform(0.03, 0.12))


def led_sad():
    """
    슬픔:
    파란색 + 천천히 가라앉는 파동
    """
    for step in range(140):
        clear_leds()

        for i in range(LED_COUNT):
            wave = (math.sin((i * 0.35) + (step * 0.08)) + 1) / 2
            brightness = 15 + wave * 45
            r, g, b = scaled_rgb(20, 80, 255, brightness)
            set_pixel_rgb(i, r, g, b)

        strip.show()
        time.sleep(0.045)


def led_anxious():
    """
    불안:
    붉은 주황색 + 부드러운 반짝임
    """
    base = (255, 70, 12)

    for step in range(120):
        wave = (math.sin(step * 0.12) + 1) / 2
        percent = 35 + wave * 55
        r, g, b = scaled_rgb(*base, percent)
        set_all_rgb(r, g, b)

        for _ in range(3):
            idx = random.randint(0, LED_COUNT - 1)
            set_pixel_rgb(
                idx,
                255,
                random.randint(80, 130),
                random.randint(5, 30)
            )

        strip.show()
        time.sleep(0.035)


def led_angry_lightning():
    """
    화남:
    실제 천둥번개처럼 엇박으로 번쩍이는 흰색 플래시
    """
    clear_leds()
    start = time.time()

    while time.time() - start < 5:
        time.sleep(random.uniform(0.08, 0.55))

        burst_count = random.choice([2, 2, 3, 4, 5])

        for _ in range(burst_count):
            clear_leds()

            flash_type = random.choice(["thin", "branch", "wide", "full"])

            if flash_type == "thin":
                center = random.randint(0, LED_COUNT - 1)
                width = random.randint(2, 6)

                for offset in range(-width, width + 1):
                    idx = (center + offset) % LED_COUNT
                    brightness = random.randint(140, 255)
                    set_pixel_rgb(idx, brightness, brightness, brightness)

            elif flash_type == "branch":
                for _ in range(random.randint(8, 22)):
                    idx = random.randint(0, LED_COUNT - 1)
                    brightness = random.randint(150, 255)
                    set_pixel_rgb(idx, brightness, brightness, brightness)

            elif flash_type == "wide":
                start_idx = random.randint(0, LED_COUNT - 1)
                width = random.randint(10, 28)

                for n in range(width):
                    idx = (start_idx + n) % LED_COUNT
                    brightness = random.randint(160, 255)
                    set_pixel_rgb(idx, brightness, brightness, brightness)

            else:
                set_all_rgb(255, 255, 255)

            strip.show()

            time.sleep(random.uniform(0.015, 0.13))

            if random.random() < 0.55:
                afterglow = random.randint(20, 80)
                set_all_scaled(255, 255, 255, afterglow)
                time.sleep(random.uniform(0.015, 0.08))

            clear_leds()
            time.sleep(random.uniform(0.025, 0.22))

        clear_leds()
        time.sleep(random.uniform(0.15, 0.65))


def led_shy():
    """
    부끄러움:
    핑크 + 천천히 붉어짐
    """
    for _ in range(3):
        for brightness in range(0, 85, 3):
            set_all_scaled(255, 70, 160, brightness)
            time.sleep(0.035)

        time.sleep(0.25)

        for brightness in range(85, 5, -3):
            set_all_scaled(255, 70, 160, brightness)
            time.sleep(0.035)

        clear_leds()
        time.sleep(0.2)


def led_bored():
    """
    따분함:
    보라색 + 아주 느린 맥박
    """
    for step in range(100):
        wave = (math.sin(step * 0.05) + 1) / 2
        percent = 8 + wave * 25
        set_all_scaled(120, 30, 180, percent)
        time.sleep(0.08)


def led_prickly():
    """
    까칠함:
    완전 초록색 + 날카로운 스파이크
    """
    for _ in range(10):
        clear_leds()

        start_idx = random.randint(0, LED_COUNT - 1)
        width = random.randint(4, 12)

        for n in range(width):
            idx = (start_idx + n) % LED_COUNT
            set_pixel_rgb(idx, 0, 255, 0)

        strip.show()
        time.sleep(random.uniform(0.05, 0.16))

        clear_leds()
        time.sleep(random.uniform(0.04, 0.14))

    set_all_rgb(0, 255, 0)
    time.sleep(0.18)
    clear_leds()


def led_envy():
    """
    부러움:
    청록 + 흐르는 파동
    """
    for step in range(130):
        clear_leds()

        for i in range(LED_COUNT):
            wave = (math.sin((i * 0.25) - (step * 0.12)) + 1) / 2
            percent = 20 + wave * 70
            r, g, b = scaled_rgb(0, 210, 180, percent)
            set_pixel_rgb(i, r, g, b)

        strip.show()
        time.sleep(0.04)


def led_crazy():
    """
    미침:
    정신없는 무지개빛 LED 효과
    """
    start = time.time()
    offset = random.randint(0, 255)

    while time.time() - start < 5:
        mode = random.choice(["spin", "scramble", "confetti", "strobe", "chaos_wave"])

        if mode == "spin":
            for _ in range(random.randint(5, 14)):
                for i in range(LED_COUNT):
                    r, g, b = rainbow_rgb((i * 256 // LED_COUNT + offset) % 256)
                    set_pixel_rgb(i, r, g, b)

                strip.show()
                offset = (offset + random.randint(8, 28)) % 256
                time.sleep(random.uniform(0.008, 0.025))

        elif mode == "scramble":
            for i in range(LED_COUNT):
                r, g, b = rainbow_rgb(random.randint(0, 255))
                set_pixel_rgb(i, r, g, b)

            strip.show()
            time.sleep(random.uniform(0.02, 0.08))

        elif mode == "confetti":
            clear_leds()

            for _ in range(random.randint(10, 35)):
                idx = random.randint(0, LED_COUNT - 1)
                r, g, b = rainbow_rgb(random.randint(0, 255))
                set_pixel_rgb(idx, r, g, b)

            strip.show()
            time.sleep(random.uniform(0.02, 0.1))

        elif mode == "strobe":
            r, g, b = rainbow_rgb(random.randint(0, 255))
            set_all_rgb(r, g, b)
            time.sleep(random.uniform(0.015, 0.06))

            if random.random() < 0.7:
                clear_leds()
                time.sleep(random.uniform(0.01, 0.05))

        elif mode == "chaos_wave":
            for step in range(random.randint(8, 20)):
                for i in range(LED_COUNT):
                    weird = int(
                        128
                        + 127 * math.sin(
                            i * random.uniform(0.1, 0.4)
                            + step * random.uniform(0.4, 1.2)
                        )
                    )
                    r, g, b = rainbow_rgb((weird + offset + random.randint(0, 40)) % 256)
                    set_pixel_rgb(i, r, g, b)

                strip.show()
                offset = (offset + random.randint(5, 20)) % 256
                time.sleep(random.uniform(0.01, 0.04))


# =========================
# Emotion Effect Mapping
# =========================

def effect_happy():
    run_together(led_happy, vib_happy)


def effect_sad():
    run_together(led_sad, vib_soft)


def effect_anxious():
    run_together(led_anxious, vib_anxious)


def effect_angry():
    run_together(led_angry_lightning, vib_angry)


def effect_shy():
    run_together(led_shy, vib_soft)


def effect_bored():
    run_together(led_bored, vib_none)


def effect_prickly():
    run_together(led_prickly, vib_prickly)


def effect_envy():
    run_together(led_envy, vib_soft)


def effect_crazy():
    run_together(led_crazy, vib_crazy)


def run_emotion_effect(emotion):
    """
    AI가 판단한 감정 이름에 맞는 LED + 진동 효과 실행
    """
    if emotion == "행복":
        effect_happy()

    elif emotion == "슬픔":
        effect_sad()

    elif emotion == "불안":
        effect_anxious()

    elif emotion == "화남":
        effect_angry()

    elif emotion == "부끄러움":
        effect_shy()

    elif emotion == "따분함":
        effect_bored()

    elif emotion == "까칠함":
        effect_prickly()

    elif emotion == "부러움":
        effect_envy()

    elif emotion == "미침":
        effect_crazy()

    else:
        print(f"알 수 없는 감정입니다: {emotion}")
        effect_bored()


# =========================
# Main Loop
# =========================

def show_intro():
    print()
    print("=================================")
    print("Cloud Mood Lamp AI + LED Test")
    print("---------------------------------")
    print("문장을 입력하면 AI가 감정을 판단하고,")
    print("그 감정에 맞는 LED + 진동 효과를 실행합니다.")
    print()
    print("종료하려면 quit 입력")
    print("LED와 진동만 끄려면 off 입력")
    print("=================================")


try:
    clear_leds()
    stop_vibration()
    show_intro()

    while True:
        text = input("\n문장 입력 > ").strip()

        if text.lower() in ["quit", "exit", "종료"]:
            print("테스트 종료")
            break

        if text.lower() == "off":
            clear_leds()
            stop_vibration()
            print("LED와 진동을 껐습니다.")
            continue

        if not text:
            print("문장을 입력해주세요.")
            continue

        print("\nAI가 감정을 판단하는 중...")
        emotion = classify_emotion(text)

        print(f"AI 감정 판단 결과: {emotion}")
        print("LED + 진동 효과 실행 중...")

        run_emotion_effect(emotion)

        print("효과 실행 완료")

except KeyboardInterrupt:
    print("\n사용자가 테스트를 중지했습니다.")

finally:
    clear_leds()
    stop_vibration()
    vib_pwm.stop()
    GPIO.cleanup()
    print("Cleaned up. LED off. Vibration off.")