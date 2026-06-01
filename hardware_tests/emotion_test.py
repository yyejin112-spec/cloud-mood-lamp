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


def breathe_rgb(r, g, b, cycles=2, delay=0.04, max_percent=100):
    """
    부드럽게 밝아졌다 어두워지는 기본 숨쉬기 효과.
    """
    for _ in range(cycles):
        for brightness in range(0, max_percent + 1, 4):
            set_all_scaled(r, g, b, brightness)
            time.sleep(delay)

        for brightness in range(max_percent, -1, -4):
            set_all_scaled(r, g, b, brightness)
            time.sleep(delay)


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
    살짝 주황빛이 도는 노란색.
    부드러운 햇빛처럼 전체가 숨 쉬고, 중간중간 작은 빛이 반짝임.
    """
    base = (255, 180, 20)

    for step in range(120):
        # 전체 밝기가 부드럽게 오르내림
        wave = (math.sin(step * 0.12) + 1) / 2
        percent = 35 + wave * 55
        r, g, b = scaled_rgb(*base, percent)
        set_all_rgb(r, g, b)

        # 작은 반짝임 몇 개
        for _ in range(3):
            idx = random.randint(0, LED_COUNT - 1)
            set_pixel_rgb(idx, 255, 220, 80)

        strip.show()
        time.sleep(0.035)


def led_sad():
    """
    슬픔:
    파란색.
    빛이 천천히 아래로 가라앉고 사라지는 느낌.
    """
    for step in range(140):
        clear_leds()

        for i in range(LED_COUNT):
            # 천천히 흐르는 파란 파동
            wave = (math.sin((i * 0.35) + (step * 0.08)) + 1) / 2
            brightness = 15 + wave * 45

            # 전체적으로 어둡고 깊은 파란색
            r, g, b = scaled_rgb(20, 80, 255, brightness)
            set_pixel_rgb(i, r, g, b)

        strip.show()
        time.sleep(0.045)


def led_anxious():
    """
    불안:
    살짝 붉은빛이 도는 주황색.
    일정하지 않게 깜박이고 흔들리는 느낌.
    """
    start = time.time()

    while time.time() - start < 4.5:
        # 기본은 어두운 붉은 주황
        base_brightness = random.randint(20, 65)
        r, g, b = scaled_rgb(255, 70, 12, base_brightness)
        set_all_rgb(r, g, b)

        # 가끔 일부 LED만 더 강하게 튐
        for _ in range(random.randint(3, 10)):
            idx = random.randint(0, LED_COUNT - 1)
            set_pixel_rgb(idx, 255, random.randint(35, 100), 5)

        strip.show()
        time.sleep(random.uniform(0.04, 0.18))

        # 아주 짧게 어두워짐
        if random.random() < 0.5:
            set_all_scaled(255, 70, 12, random.randint(5, 20))
            time.sleep(random.uniform(0.03, 0.12))


def led_angry_lightning():
    """
    화남:
    실제 천둥번개처럼 엇박으로 번쩍거리는 흰색 플래시.
    짧은 번쩍임, 긴 번쩍임, 잔광, 어두운 대기 시간을 섞음.
    """
    clear_leds()
    start = time.time()

    while time.time() - start < 5:
        # 번개가 치기 전 어두운 간격
        time.sleep(random.uniform(0.08, 0.55))

        # 한 번의 번개는 여러 개의 불규칙한 flash 묶음으로 구성
        burst_count = random.choice([2, 2, 3, 4, 5])

        for burst in range(burst_count):
            clear_leds()

            flash_type = random.choice(["thin", "branch", "wide", "full"])

            if flash_type == "thin":
                # 가느다란 번개 줄기처럼 일부만 번쩍
                center = random.randint(0, LED_COUNT - 1)
                width = random.randint(2, 6)

                for offset in range(-width, width + 1):
                    idx = (center + offset) % LED_COUNT
                    brightness = random.randint(120, 255)
                    set_pixel_rgb(idx, brightness, brightness, brightness)

            elif flash_type == "branch":
                # 가지처럼 여기저기 흩어진 흰빛
                for _ in range(random.randint(8, 22)):
                    idx = random.randint(0, LED_COUNT - 1)
                    brightness = random.randint(150, 255)
                    set_pixel_rgb(idx, brightness, brightness, brightness)

            elif flash_type == "wide":
                # 넓은 영역이 번쩍
                start_idx = random.randint(0, LED_COUNT - 1)
                width = random.randint(10, 28)

                for n in range(width):
                    idx = (start_idx + n) % LED_COUNT
                    brightness = random.randint(160, 255)
                    set_pixel_rgb(idx, brightness, brightness, brightness)

            else:
                # 아주 짧게 전체 번쩍
                set_all_rgb(255, 255, 255)

            strip.show()

            # 각 번쩍임의 지속시간이 미세하게 다름
            time.sleep(random.uniform(0.015, 0.13))

            # 잔광: 바로 꺼지지 않고 약하게 남음
            if random.random() < 0.55:
                afterglow = random.randint(20, 80)
                set_all_scaled(255, 255, 255, afterglow)
                time.sleep(random.uniform(0.015, 0.08))

            clear_leds()

            # 번쩍임 사이 간격도 엇박
            time.sleep(random.uniform(0.025, 0.22))

        # 번개 묶음이 끝난 뒤 어두운 정적
        clear_leds()
        time.sleep(random.uniform(0.15, 0.65))


def led_shy():
    """
    부끄러움:
    핑크.
    갑자기 켜지는 게 아니라 얼굴이 붉어지듯 천천히 올라왔다가 사라짐.
    """
    for _ in range(3):
        for brightness in range(0, 85, 3):
            set_all_scaled(255, 70, 160, brightness)
            time.sleep(0.035)

        # 살짝 머무름
        time.sleep(0.25)

        for brightness in range(85, 5, -3):
            set_all_scaled(255, 70, 160, brightness)
            time.sleep(0.035)

        clear_leds()
        time.sleep(0.2)


def led_bored():
    """
    따분함:
    남색.
    거의 움직이지 않고, 아주 느리게 희미하게 맥박치는 느낌.
    """
    for step in range(100):
        wave = (math.sin(step * 0.05) + 1) / 2
        percent = 8 + wave * 22
        set_all_scaled(5, 15, 100, percent)
        time.sleep(0.08)


def led_timid():
    """
    소심함:
    보라.
    켜지려다가 망설이듯 약하게 깜빡이고, 다시 숨는 느낌.
    """
    for _ in range(5):
        max_brightness = random.randint(25, 55)

        for brightness in range(0, max_brightness, 4):
            set_all_scaled(130, 35, 220, brightness)
            time.sleep(0.035)

        time.sleep(random.uniform(0.08, 0.25))

        for brightness in range(max_brightness, 0, -5):
            set_all_scaled(130, 35, 220, brightness)
            time.sleep(0.03)

        clear_leds()
        time.sleep(random.uniform(0.15, 0.45))


def led_prickly():
    """
    까칠함:
    완전 초록색.
    청록이 아니라 G값만 강한 초록.
    날카롭게 콕콕 찌르는 듯한 짧은 초록 스파이크.
    """
    pure_green = (0, 255, 0)

    for _ in range(10):
        clear_leds()

        # 전체가 아니라 일부 구간만 날카롭게 초록색
        start_idx = random.randint(0, LED_COUNT - 1)
        width = random.randint(4, 12)

        for n in range(width):
            idx = (start_idx + n) % LED_COUNT
            set_pixel_rgb(idx, *pure_green)

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
    가만히 있는 색이 아니라, 옆으로 스며드는 듯한 청록 흐름.
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


def effect_timid():
    def led_part():
        led_timid()

    def vib_part():
        vib_soft()

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


# =========================
# Menu
# =========================

def show_menu():
    print()
    print("=================================")
    print("Cloud Mood Lamp Emotion Test")
    print("---------------------------------")
    print("행복 / happy      : 주황빛 노란색, 따뜻한 반짝임")
    print("슬픔 / sad        : 파란색, 천천히 가라앉는 파동")
    print("불안 / anxious    : 붉은 주황색, 불규칙한 흔들림")
    print("화남 / angry      : 흰색 천둥번개 효과")
    print("부끄러움 / shy    : 핑크, 천천히 붉어짐")
    print("따분함 / bored    : 남색, 느린 맥박")
    print("소심함 / timid    : 보라, 망설이는 약한 빛")
    print("까칠함 / prickly  : 완전 초록, 날카로운 스파이크")
    print("부러움 / envy     : 청록, 흐르는 파동")
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