from rpi_ws281x import PixelStrip, Color
import RPi.GPIO as GPIO
import time
import threading
import random
import math

# =========================
# Cloud Mood Lamp
# Emotion LED + Vibration Test
# =========================

# NeoPixel LED settings
LED_COUNT = 120
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
    """
    0~255 값을 무지개 RGB 값으로 변환.
    """
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
    """
    미침:
    불규칙하고 정신없는 진동.
    """
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
    색은 살짝 주황빛이 도는 노란색 유지.
    효과는 기존 불안처럼 일정하지 않게 반짝이고 튀는 느낌.
    """
    start = time.time()

    while time.time() - start < 4.5:
        # 기본은 주황빛 노란색
        base_brightness = random.randint(25, 75)
        r, g, b = scaled_rgb(255, 180, 20, base_brightness)
        set_all_rgb(r, g, b)

        # 일부 LED가 따뜻하게 톡톡 튐
        for _ in range(random.randint(3, 10)):
            idx = random.randint(0, LED_COUNT - 1)
            set_pixel_rgb(idx, 255, random.randint(190, 240), random.randint(20, 80))

        strip.show()
        time.sleep(random.uniform(0.04, 0.18))

        # 짧게 어두워졌다가 다시 켜지는 반짝임
        if random.random() < 0.45:
            set_all_scaled(255, 180, 20, random.randint(8, 25))
            time.sleep(random.uniform(0.03, 0.12))


def led_sad():
    """
    슬픔:
    파란색.
    천천히 가라앉는 파란 파동.
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
    색은 살짝 붉은빛이 도는 주황색 유지.
    효과는 기존 행복처럼 부드럽게 출렁이고 작은 빛이 반짝임.
    """
    base = (255, 70, 12)

    for step in range(120):
        wave = (math.sin(step * 0.12) + 1) / 2
        percent = 35 + wave * 55
        r, g, b = scaled_rgb(*base, percent)
        set_all_rgb(r, g, b)

        # 붉은 주황색의 작은 반짝임
        for _ in range(3):
            idx = random.randint(0, LED_COUNT - 1)
            set_pixel_rgb(idx, 255, random.randint(80, 130), random.randint(5, 30))

        strip.show()
        time.sleep(0.035)


def led_angry_lightning():
    """
    화남:
    실제 천둥번개처럼 엇박으로 번쩍거리는 흰색 플래시.
    짧은 번쩍임, 긴 번쩍임, 일부 번쩍임, 전체 번쩍임, 잔광을 섞음.
    """
    clear_leds()
    start = time.time()

    while time.time() - start < 5:
        # 번개 전 어두운 대기 시간
        time.sleep(random.uniform(0.08, 0.55))

        # 한 번의 번개는 여러 번의 불규칙한 flash 묶음
        burst_count = random.choice([2, 2, 3, 4, 5])

        for _ in range(burst_count):
            clear_leds()

            flash_type = random.choice(["thin", "branch", "wide", "full"])

            if flash_type == "thin":
                # 가느다란 번개 줄기
                center = random.randint(0, LED_COUNT - 1)
                width = random.randint(2, 6)

                for offset in range(-width, width + 1):
                    idx = (center + offset) % LED_COUNT
                    brightness = random.randint(140, 255)
                    set_pixel_rgb(idx, brightness, brightness, brightness)

            elif flash_type == "branch":
                # 가지처럼 흩어진 흰빛
                for _ in range(random.randint(8, 22)):
                    idx = random.randint(0, LED_COUNT - 1)
                    brightness = random.randint(150, 255)
                    set_pixel_rgb(idx, brightness, brightness, brightness)

            elif flash_type == "wide":
                # 넓은 영역이 순간적으로 번쩍
                start_idx = random.randint(0, LED_COUNT - 1)
                width = random.randint(10, 28)

                for n in range(width):
                    idx = (start_idx + n) % LED_COUNT
                    brightness = random.randint(160, 255)
                    set_pixel_rgb(idx, brightness, brightness, brightness)

            else:
                # 전체가 아주 짧게 번쩍
                set_all_rgb(255, 255, 255)

            strip.show()

            # 번쩍임마다 지속시간이 미세하게 다름
            time.sleep(random.uniform(0.015, 0.13))

            # 잔광
            if random.random() < 0.55:
                afterglow = random.randint(20, 80)
                set_all_scaled(255, 255, 255, afterglow)
                time.sleep(random.uniform(0.015, 0.08))

            clear_leds()

            # 번쩍임 사이 간격도 엇박
            time.sleep(random.uniform(0.025, 0.22))

        # 번개 묶음 뒤 어두운 정적
        clear_leds()
        time.sleep(random.uniform(0.15, 0.65))


def led_shy():
    """
    부끄러움:
    핑크.
    얼굴이 붉어지듯 천천히 올라왔다가 사라지는 느낌.
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
    보라색.
    거의 움직이지 않고, 아주 느리게 희미하게 맥박치는 느낌.
    """
    for step in range(100):
        wave = (math.sin(step * 0.05) + 1) / 2
        percent = 8 + wave * 25
        set_all_scaled(120, 30, 180, percent)
        time.sleep(0.08)


def led_prickly():
    """
    까칠함:
    완전 초록색.
    청록이 아니라 G값만 강한 초록.
    날카롭게 콕콕 찌르는 듯한 초록 스파이크.
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

    # 마지막에 아주 짧게 전체 초록
    set_all_rgb(0, 255, 0)
    time.sleep(0.18)
    clear_leds()


def led_envy():
    """
    부러움:
    청록.
    옆으로 스며드는 듯한 청록 흐름.
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
    정말 미친 듯이 정신없는 무지개빛 LED 효과.
    빠른 무지개 회전, 랜덤 픽셀, 전체 번쩍임, 색 섞임이 계속 바뀜.
    """
    start = time.time()
    offset = random.randint(0, 255)

    while time.time() - start < 5:
        mode = random.choice(["spin", "scramble", "confetti", "strobe", "chaos_wave"])

        if mode == "spin":
            # 무지개가 빠르게 회전
            for _ in range(random.randint(5, 14)):
                for i in range(LED_COUNT):
                    r, g, b = rainbow_rgb((i * 256 // LED_COUNT + offset) % 256)
                    set_pixel_rgb(i, r, g, b)

                strip.show()
                offset = (offset + random.randint(8, 28)) % 256
                time.sleep(random.uniform(0.008, 0.025))

        elif mode == "scramble":
            # 모든 LED가 제각각 다른 무지개색으로 뒤죽박죽
            for i in range(LED_COUNT):
                r, g, b = rainbow_rgb(random.randint(0, 255))
                set_pixel_rgb(i, r, g, b)

            strip.show()
            time.sleep(random.uniform(0.02, 0.08))

        elif mode == "confetti":
            # 어두운 배경 위에 랜덤 무지개 점들이 폭발
            clear_leds()

            for _ in range(random.randint(10, 35)):
                idx = random.randint(0, LED_COUNT - 1)
                r, g, b = rainbow_rgb(random.randint(0, 255))
                set_pixel_rgb(idx, r, g, b)

            strip.show()
            time.sleep(random.uniform(0.02, 0.1))

        elif mode == "strobe":
            # 전체가 무지개색 중 하나로 번쩍
            r, g, b = rainbow_rgb(random.randint(0, 255))
            set_all_rgb(r, g, b)
            time.sleep(random.uniform(0.015, 0.06))

            if random.random() < 0.7:
                clear_leds()
                time.sleep(random.uniform(0.01, 0.05))

        elif mode == "chaos_wave":
            # 규칙적일 듯하다가 흔들리는 이상한 파동
            for step in range(random.randint(8, 20)):
                for i in range(LED_COUNT):
                    weird = int(
                        128
                        + 127 * math.sin(i * random.uniform(0.1, 0.4) + step * random.uniform(0.4, 1.2))
                    )
                    r, g, b = rainbow_rgb((weird + offset + random.randint(0, 40)) % 256)
                    set_pixel_rgb(i, r, g, b)

                strip.show()
                offset = (offset + random.randint(5, 20)) % 256
                time.sleep(random.uniform(0.01, 0.04))


# =========================
# Emotion Effects
# =========================

def effect_happy():
    def led_part():
        led_happy()

    def vib_part():
        vib_happy()

    run_together(led_part, vib_part)


def effect_sad():
    def led_part():
        led_sad()

    def vib_part():
        vib_soft()

    run_together(led_part, vib_part)


def effect_anxious():
    def led_part():
        led_anxious()

    def vib_part():
        vib_anxious()

    run_together(led_part, vib_part)


def effect_angry():
    def led_part():
        led_angry_lightning()

    def vib_part():
        vib_angry()

    run_together(led_part, vib_part)


def effect_shy():
    def led_part():
        led_shy()

    def vib_part():
        vib_soft()

    run_together(led_part, vib_part)


def effect_bored():
    def led_part():
        led_bored()

    def vib_part():
        vib_none()

    run_together(led_part, vib_part)


def effect_prickly():
    def led_part():
        led_prickly()

    def vib_part():
        vib_prickly()

    run_together(led_part, vib_part)


def effect_envy():
    def led_part():
        led_envy()

    def vib_part():
        vib_soft()

    run_together(led_part, vib_part)


def effect_crazy():
    def led_part():
        led_crazy()

    def vib_part():
        vib_crazy()

    run_together(led_part, vib_part)


# =========================
# Menu
# =========================

def show_menu():
    print()
    print("=================================")
    print("Cloud Mood Lamp Emotion Test")
    print("---------------------------------")
    print("행복 / happy      : 주황빛 노란색, 불규칙한 반짝임")
    print("슬픔 / sad        : 파란색, 천천히 가라앉는 파동")
    print("불안 / anxious    : 붉은 주황색, 부드러운 반짝임")
    print("화남 / angry      : 흰색 천둥번개 효과")
    print("부끄러움 / shy    : 핑크, 천천히 붉어짐")
    print("따분함 / bored    : 보라색, 느린 맥박")
    print("까칠함 / prickly  : 완전 초록, 날카로운 스파이크")
    print("부러움 / envy     : 청록, 흐르는 파동")
    print("미침 / crazy      : 정신없는 무지개 효과")
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

        elif emotion in ["까칠함", "prickly"]:
            effect_prickly()

        elif emotion in ["부러움", "envy"]:
            effect_envy()

        elif emotion in ["미침", "crazy", "mad"]:
            effect_crazy()

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
            print("행복, 슬픔, 불안, 화남, 부끄러움, 따분함, 까칠함, 부러움, 미침")
            print("또는 happy, sad, anxious, angry, shy, bored, prickly, envy, crazy")

except KeyboardInterrupt:
    print("\nStopped by user.")

finally:
    clear_leds()
    stop_vibration()
    vib_pwm.stop()
    GPIO.cleanup()
    print("Cleaned up. LED off. Vibration off.")