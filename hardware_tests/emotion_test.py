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
LED_BRIGHTNESS = 35   # 0~255. 처음에는 낮게 테스트
LED_INVERT = False
LED_CHANNEL = 0

# DRV8833 vibration motor settings
VIB_AIN1 = 23         # GPIO23 = physical pin 16
VIB_AIN2 = 24         # GPIO24 = physical pin 18
PWM_FREQ = 100        # vibration PWM frequency

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

# One direction only:
# AIN1 = PWM, AIN2 = LOW
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


# =========================
# LED effect functions
# =========================

def breathe_color(color, cycles=3, delay=0.03):
    """
    LED softly fades in and out with one color.
    """
    for _ in range(cycles):
        # Fade in
        for brightness in range(0, 101, 4):
            for i in range(LED_COUNT):
                strip.setPixelColor(i, scale_color(color, brightness))
            strip.show()
            time.sleep(delay)

        # Fade out
        for brightness in range(100, -1, -4):
            for i in range(LED_COUNT):
                strip.setPixelColor(i, scale_color(color, brightness))
            strip.show()
            time.sleep(delay)


def blink_color(color, times=5, on_time=0.12, off_time=0.08):
    """
    LED quickly blinks.
    """
    for _ in range(times):
        set_all_leds(color)
        time.sleep(on_time)
        clear_leds()
        time.sleep(off_time)


def unstable_flicker(color1, color2, duration=3):
    """
    Irregular flickering effect for anxious emotion.
    """
    start = time.time()
    while time.time() - start < duration:
        chosen = color1 if random.random() > 0.5 else color2
        set_all_leds(chosen)
        time.sleep(random.uniform(0.05, 0.25))
        clear_leds()
        time.sleep(random.uniform(0.03, 0.15))


def soft_wave(color, duration=4):
    """
    Calm soft glowing effect.
    """
    start = time.time()
    while time.time() - start < duration:
        breathe_color(color, cycles=1, delay=0.04)


def scale_color(color, percent):
    """
    Scale Color brightness.
    percent: 0~100
    """
    percent = max(0, min(100, percent)) / 100

    # rpi_ws281x Color object is integer, so extract RGB manually is awkward.
    # Instead, receive color as tuple through make_color functions below.
    return color


def make_scaled_color(r, g, b, percent):
    """
    Make brightness-scaled Color.
    """
    percent = max(0, min(100, percent)) / 100
    return Color(int(r * percent), int(g * percent), int(b * percent))


def breathe_rgb(r, g, b, cycles=3, delay=0.03):
    """
    Fade in/out with RGB values.
    """
    for _ in range(cycles):
        for brightness in range(0, 101, 4):
            color = make_scaled_color(r, g, b, brightness)
            set_all_leds(color)
            time.sleep(delay)

        for brightness in range(100, -1, -4):
            color = make_scaled_color(r, g, b, brightness)
            set_all_leds(color)
            time.sleep(delay)


# =========================
# Emotion effects
# =========================

def effect_happy():
    """
    Happy:
    warm yellow/pink light + short tapping vibration
    """
    def led_part():
        # warm yellow → pink feel
        for _ in range(2):
            breathe_rgb(255, 180, 40, cycles=1, delay=0.02)
            breathe_rgb(255, 80, 120, cycles=1, delay=0.02)

    def vib_part():
        for _ in range(4):
            vibrate(45, 0.12)
            time.sleep(0.15)

    run_together(led_part, vib_part)


def effect_sad():
    """
    Sad:
    slow blue light + weak slow vibration
    """
    def led_part():
        breathe_rgb(30, 80, 255, cycles=3, delay=0.05)

    def vib_part():
        for _ in range(3):
            vibrate(25, 0.35)
            time.sleep(0.45)

    run_together(led_part, vib_part)


def effect_angry():
    """
    Angry:
    red/orange fast blinking + strong short vibration
    """
    def led_part():
        for _ in range(6):
            set_all_leds(Color(255, 0, 0))
            time.sleep(0.1)
            set_all_leds(Color(255, 80, 0))
            time.sleep(0.08)
            clear_leds()
            time.sleep(0.05)

    def vib_part():
        for _ in range(5):
            vibrate(80, 0.12)
            time.sleep(0.08)

    run_together(led_part, vib_part)


def effect_anxious():
    """
    Anxious:
    purple/blue irregular flicker + irregular vibration
    """
    def led_part():
        start = time.time()
        while time.time() - start < 4:
            if random.random() > 0.5:
                set_all_leds(Color(120, 0, 255))
            else:
                set_all_leds(Color(0, 60, 255))
            time.sleep(random.uniform(0.05, 0.25))
            clear_leds()
            time.sleep(random.uniform(0.03, 0.15))

    def vib_part():
        start = time.time()
        while time.time() - start < 4:
            vibrate(random.randint(20, 60), random.uniform(0.05, 0.2))
            time.sleep(random.uniform(0.05, 0.3))

    run_together(led_part, vib_part)


def effect_calm():
    """
    Calm:
    soft sky blue/warm white glow + almost no vibration
    """
    def led_part():
        breathe_rgb(120, 200, 255, cycles=2, delay=0.06)
        breathe_rgb(255, 220, 180, cycles=1, delay=0.06)

    def vib_part():
        # very subtle vibration once
        vibrate(15, 0.15)

    run_together(led_part, vib_part)


def run_together(led_function, vibration_function):
    """
    Run LED effect and vibration pattern at the same time.
    """
    led_thread = threading.Thread(target=led_function)
    vib_thread = threading.Thread(target=vibration_function)

    led_thread.start()
    vib_thread.start()

    led_thread.join()
    vib_thread.join()

    stop_vibration()


# =========================
# Main interactive loop
# =========================

def show_menu():
    print()
    print("=================================")
    print("Emotion Test")
    print("Type one emotion and press Enter.")
    print("---------------------------------")
    print("happy   : yellow/pink + tapping vibration")
    print("sad     : blue + slow weak vibration")
    print("angry   : red/orange + strong short vibration")
    print("anxious : purple/blue + irregular vibration")
    print("calm    : soft sky blue + almost no vibration")
    print("off     : turn off LED and vibration")
    print("quit    : exit")
    print("=================================")


try:
    clear_leds()
    stop_vibration()

    print("Cloud mood lamp emotion test started.")

    while True:
        show_menu()
        emotion = input("Emotion > ").strip().lower()

        if emotion == "happy":
            effect_happy()

        elif emotion == "sad":
            effect_sad()

        elif emotion == "angry":
            effect_angry()

        elif emotion == "anxious":
            effect_anxious()

        elif emotion == "calm":
            effect_calm()

        elif emotion == "off":
            clear_leds()
            stop_vibration()
            print("LED and vibration off.")

        elif emotion == "quit":
            print("Exit emotion test.")
            break

        else:
            print("Unknown emotion.")
            print("Please type: happy, sad, angry, anxious, calm, off, quit")

except KeyboardInterrupt:
    print("\nStopped by user.")

finally:
    clear_leds()
    stop_vibration()
    vib_pwm.stop()
    GPIO.cleanup()
    print("Cleaned up. LED off. Vibration off.")