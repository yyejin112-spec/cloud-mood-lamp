import os
import sys
import json
import base64
import asyncio
import subprocess
import time
import wave
import array
import threading
import random
import math
from pathlib import Path
from collections import deque

import websockets
from rpi_ws281x import PixelStrip, Color
import RPi.GPIO as GPIO

# 프로젝트 루트 경로를 Python이 찾을 수 있게 추가
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from src.emotion_ai import classify_emotion


# =========================
# Cloud Mood Lamp
# Realtime STT → Emotion → LED/Vibration Full Debug
# =========================

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

TRANSCRIPTION_MODEL = "gpt-realtime-whisper"
REALTIME_URL = "wss://api.openai.com/v1/realtime?intent=transcription"

# -------------------------
# Microphone settings
# -------------------------

AUDIO_DEVICE = "plughw:3"

MIC_SAMPLE_RATE = 24000
MIC_CHANNELS = 1
SAMPLE_WIDTH = 2              # S16_LE = 2 bytes
CHUNK_FRAMES = 1200           # 약 0.05초
CHUNK_BYTES = CHUNK_FRAMES * SAMPLE_WIDTH

DEBUG_AUDIO_DIR = PROJECT_ROOT / "state" / "debug_realtime_full"
DEBUG_AUDIO_DIR.mkdir(parents=True, exist_ok=True)

# -------------------------
# Local VAD settings
# -------------------------

CALIBRATE_SECONDS = 1.2
MIN_SPEECH_SECONDS = 0.45
MAX_SPEECH_SECONDS = 8.0
SILENCE_SECONDS = 0.65
PRE_ROLL_CHUNKS = 8
START_CHUNKS_REQUIRED = 1

MIN_START_THRESHOLD = 0.006
MIN_STOP_THRESHOLD = 0.003

LEVEL_PRINT_INTERVAL = 0.08
PRINT_LEVEL_BAR = True
PRINT_RAW_EVENTS = True

# 처음 실행하자마자 VAD와 상관없이 무조건 오디오를 보내는 테스트
FORCE_SEND_TEST_SECONDS = 6

# -------------------------
# LED settings
# -------------------------

LED_COUNT = 60
LED_PIN = 10          # GPIO10 = physical pin 19
LED_FREQ_HZ = 800000
LED_DMA = 10
LED_BRIGHTNESS = 35
LED_INVERT = False
LED_CHANNEL = 0

# -------------------------
# Vibration settings
# -------------------------

VIB_AIN1 = 23         # GPIO23 = physical pin 16
VIB_AIN2 = 24         # GPIO24 = physical pin 18
PWM_FREQ = 100

shutdown_event = threading.Event()


# =========================
# Hardware setup
# =========================

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


def sleep_with_stop(stop_event, seconds):
    end_time = time.time() + seconds

    while time.time() < end_time:
        if stop_event.is_set() or shutdown_event.is_set():
            return False
        time.sleep(0.01)

    return True


# =========================
# Vibration functions
# =========================

def stop_vibration():
    vib_pwm.ChangeDutyCycle(0)
    GPIO.output(VIB_AIN2, GPIO.LOW)


def vibrate(strength, duration, stop_event=None):
    if stop_event and stop_event.is_set():
        return

    strength = max(0, min(100, strength))
    vib_pwm.ChangeDutyCycle(strength)

    if stop_event:
        sleep_with_stop(stop_event, duration)
    else:
        time.sleep(duration)

    vib_pwm.ChangeDutyCycle(0)


def vib_none(stop_event):
    sleep_with_stop(stop_event, 0.5)


def vib_soft(stop_event):
    for _ in range(2):
        if stop_event.is_set():
            return
        vibrate(22, 0.18, stop_event)
        sleep_with_stop(stop_event, 0.3)


def vib_happy(stop_event):
    for _ in range(4):
        if stop_event.is_set():
            return
        vibrate(38, 0.1, stop_event)
        sleep_with_stop(stop_event, 0.13)


def vib_anxious(stop_event):
    for _ in range(7):
        if stop_event.is_set():
            return
        vibrate(random.randint(25, 55), random.uniform(0.04, 0.16), stop_event)
        sleep_with_stop(stop_event, random.uniform(0.04, 0.22))


def vib_angry(stop_event):
    for _ in range(6):
        if stop_event.is_set():
            return
        vibrate(random.randint(60, 85), random.uniform(0.06, 0.14), stop_event)
        sleep_with_stop(stop_event, random.uniform(0.04, 0.16))


def vib_prickly(stop_event):
    for _ in range(5):
        if stop_event.is_set():
            return
        vibrate(55, 0.07, stop_event)
        sleep_with_stop(stop_event, 0.09)


def vib_crazy(stop_event):
    start = time.time()

    while time.time() - start < 5:
        if stop_event.is_set():
            return

        strength = random.randint(20, 90)
        duration = random.uniform(0.03, 0.18)
        vibrate(strength, duration, stop_event)
        sleep_with_stop(stop_event, random.uniform(0.02, 0.16))


def run_together(stop_event, led_function, vibration_function):
    led_thread = threading.Thread(target=led_function, args=(stop_event,), daemon=True)
    vib_thread = threading.Thread(target=vibration_function, args=(stop_event,), daemon=True)

    led_thread.start()
    vib_thread.start()

    led_thread.join()
    vib_thread.join()

    stop_vibration()


# =========================
# Idle warm breathing
# =========================

def idle_warm_breathing(stop_event):
    """
    기본 전구색 숨쉬기 무드등 상태.
    """
    step = 0

    while not stop_event.is_set() and not shutdown_event.is_set():
        wave = (math.sin(step * 0.045) + 1) / 2
        percent = 10 + wave * 25

        set_all_scaled(255, 170, 75, percent)

        step += 1
        time.sleep(0.035)


# =========================
# Emotion LED effects
# =========================

def led_happy(stop_event):
    start = time.time()

    while time.time() - start < 4.5:
        if stop_event.is_set():
            return

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

        if not sleep_with_stop(stop_event, random.uniform(0.04, 0.18)):
            return

        if random.random() < 0.45:
            set_all_scaled(255, 180, 20, random.randint(8, 25))
            if not sleep_with_stop(stop_event, random.uniform(0.03, 0.12)):
                return


def led_sad(stop_event):
    for step in range(140):
        if stop_event.is_set():
            return

        clear_leds()

        for i in range(LED_COUNT):
            wave = (math.sin((i * 0.35) + (step * 0.08)) + 1) / 2
            brightness = 15 + wave * 45
            r, g, b = scaled_rgb(20, 80, 255, brightness)
            set_pixel_rgb(i, r, g, b)

        strip.show()

        if not sleep_with_stop(stop_event, 0.045):
            return


def led_anxious(stop_event):
    base = (255, 70, 12)

    for step in range(120):
        if stop_event.is_set():
            return

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

        if not sleep_with_stop(stop_event, 0.035):
            return


def led_angry_lightning(stop_event):
    clear_leds()
    start = time.time()

    while time.time() - start < 5:
        if stop_event.is_set():
            return

        if not sleep_with_stop(stop_event, random.uniform(0.08, 0.55)):
            return

        burst_count = random.choice([2, 2, 3, 4, 5])

        for _ in range(burst_count):
            if stop_event.is_set():
                return

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

            if not sleep_with_stop(stop_event, random.uniform(0.015, 0.13)):
                return

            if random.random() < 0.55:
                afterglow = random.randint(20, 80)
                set_all_scaled(255, 255, 255, afterglow)

                if not sleep_with_stop(stop_event, random.uniform(0.015, 0.08)):
                    return

            clear_leds()

            if not sleep_with_stop(stop_event, random.uniform(0.025, 0.22)):
                return

        clear_leds()

        if not sleep_with_stop(stop_event, random.uniform(0.15, 0.65)):
            return


def led_shy(stop_event):
    for _ in range(3):
        if stop_event.is_set():
            return

        for brightness in range(0, 85, 3):
            if stop_event.is_set():
                return
            set_all_scaled(255, 70, 160, brightness)

            if not sleep_with_stop(stop_event, 0.035):
                return

        if not sleep_with_stop(stop_event, 0.25):
            return

        for brightness in range(85, 5, -3):
            if stop_event.is_set():
                return
            set_all_scaled(255, 70, 160, brightness)

            if not sleep_with_stop(stop_event, 0.035):
                return

        clear_leds()

        if not sleep_with_stop(stop_event, 0.2):
            return


def led_bored(stop_event):
    for step in range(100):
        if stop_event.is_set():
            return

        wave = (math.sin(step * 0.05) + 1) / 2
        percent = 8 + wave * 25
        set_all_scaled(120, 30, 180, percent)

        if not sleep_with_stop(stop_event, 0.08):
            return


def led_prickly(stop_event):
    for _ in range(10):
        if stop_event.is_set():
            return

        clear_leds()

        start_idx = random.randint(0, LED_COUNT - 1)
        width = random.randint(4, 12)

        for n in range(width):
            idx = (start_idx + n) % LED_COUNT
            set_pixel_rgb(idx, 0, 255, 0)

        strip.show()

        if not sleep_with_stop(stop_event, random.uniform(0.05, 0.16)):
            return

        clear_leds()

        if not sleep_with_stop(stop_event, random.uniform(0.04, 0.14)):
            return

    set_all_rgb(0, 255, 0)
    sleep_with_stop(stop_event, 0.18)
    clear_leds()


def led_envy(stop_event):
    for step in range(130):
        if stop_event.is_set():
            return

        clear_leds()

        for i in range(LED_COUNT):
            wave = (math.sin((i * 0.25) - (step * 0.12)) + 1) / 2
            percent = 20 + wave * 70
            r, g, b = scaled_rgb(0, 210, 180, percent)
            set_pixel_rgb(i, r, g, b)

        strip.show()

        if not sleep_with_stop(stop_event, 0.04):
            return


def led_crazy(stop_event):
    start = time.time()
    offset = random.randint(0, 255)

    while time.time() - start < 5:
        if stop_event.is_set():
            return

        mode = random.choice(["spin", "scramble", "confetti", "strobe", "chaos_wave"])

        if mode == "spin":
            for _ in range(random.randint(5, 14)):
                if stop_event.is_set():
                    return

                for i in range(LED_COUNT):
                    r, g, b = rainbow_rgb((i * 256 // LED_COUNT + offset) % 256)
                    set_pixel_rgb(i, r, g, b)

                strip.show()
                offset = (offset + random.randint(8, 28)) % 256

                if not sleep_with_stop(stop_event, random.uniform(0.008, 0.025)):
                    return

        elif mode == "scramble":
            for i in range(LED_COUNT):
                r, g, b = rainbow_rgb(random.randint(0, 255))
                set_pixel_rgb(i, r, g, b)

            strip.show()

            if not sleep_with_stop(stop_event, random.uniform(0.02, 0.08)):
                return

        elif mode == "confetti":
            clear_leds()

            for _ in range(random.randint(10, 35)):
                idx = random.randint(0, LED_COUNT - 1)
                r, g, b = rainbow_rgb(random.randint(0, 255))
                set_pixel_rgb(idx, r, g, b)

            strip.show()

            if not sleep_with_stop(stop_event, random.uniform(0.02, 0.1)):
                return

        elif mode == "strobe":
            r, g, b = rainbow_rgb(random.randint(0, 255))
            set_all_rgb(r, g, b)

            if not sleep_with_stop(stop_event, random.uniform(0.015, 0.06)):
                return

            if random.random() < 0.7:
                clear_leds()

                if not sleep_with_stop(stop_event, random.uniform(0.01, 0.05)):
                    return

        elif mode == "chaos_wave":
            for step in range(random.randint(8, 20)):
                if stop_event.is_set():
                    return

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

                if not sleep_with_stop(stop_event, random.uniform(0.01, 0.04)):
                    return


# =========================
# Effect Controller
# =========================

class EffectController:
    def __init__(self):
        self.lock = threading.RLock()

        self.idle_stop_event = threading.Event()
        self.idle_thread = None

        self.effect_stop_event = None
        self.effect_thread = None

    def start_idle(self):
        with self.lock:
            if self.idle_thread and self.idle_thread.is_alive():
                return

            print("[LED] 기본 전구색 숨쉬기 시작")

            self.idle_stop_event.clear()
            self.idle_thread = threading.Thread(
                target=idle_warm_breathing,
                args=(self.idle_stop_event,),
                daemon=True
            )
            self.idle_thread.start()

    def stop_idle(self):
        self.idle_stop_event.set()

        if self.idle_thread and self.idle_thread.is_alive():
            self.idle_thread.join(timeout=0.3)

        self.idle_thread = None

    def start_emotion(self, emotion):
        with self.lock:
            print()
            print("=================================")
            print("[PIPELINE] LED/진동 효과 실행 요청")
            print(f"감정: {emotion}")
            print("=================================")

            self.stop_idle()
            self.stop_current_effect_locked()

            self.effect_stop_event = threading.Event()
            self.effect_thread = threading.Thread(
                target=self._run_emotion_effect,
                args=(emotion, self.effect_stop_event),
                daemon=True
            )
            self.effect_thread.start()

    def stop_current_effect_locked(self):
        if self.effect_stop_event:
            self.effect_stop_event.set()

        if self.effect_thread and self.effect_thread.is_alive():
            self.effect_thread.join(timeout=0.3)

        stop_vibration()

    def stop_all(self):
        with self.lock:
            self.stop_idle()
            self.stop_current_effect_locked()
            clear_leds()
            stop_vibration()

    def _run_emotion_effect(self, emotion, stop_event):
        print(f"[Effect] 감정 효과 시작: {emotion}")

        try:
            if emotion == "행복":
                print("[Effect Mapping] 행복 → 노란빛 반짝임 + 경쾌한 진동")
                run_together(stop_event, led_happy, vib_happy)

            elif emotion == "슬픔":
                print("[Effect Mapping] 슬픔 → 파란 파동 + 부드러운 진동")
                run_together(stop_event, led_sad, vib_soft)

            elif emotion == "불안":
                print("[Effect Mapping] 불안 → 붉은 주황빛 + 불규칙 진동")
                run_together(stop_event, led_anxious, vib_anxious)

            elif emotion == "화남":
                print("[Effect Mapping] 화남 → 흰색 번개 + 강한 진동")
                run_together(stop_event, led_angry_lightning, vib_angry)

            elif emotion == "부끄러움":
                print("[Effect Mapping] 부끄러움 → 핑크빛 + 부드러운 진동")
                run_together(stop_event, led_shy, vib_soft)

            elif emotion == "따분함":
                print("[Effect Mapping] 따분함 → 보라색 느린 맥박 + 진동 없음")
                run_together(stop_event, led_bored, vib_none)

            elif emotion == "까칠함":
                print("[Effect Mapping] 까칠함 → 초록 스파이크 + 짧은 진동")
                run_together(stop_event, led_prickly, vib_prickly)

            elif emotion == "부러움":
                print("[Effect Mapping] 부러움 → 청록 파동 + 부드러운 진동")
                run_together(stop_event, led_envy, vib_soft)

            elif emotion == "미침":
                print("[Effect Mapping] 미침 → 정신없는 무지개 + 불규칙 진동")
                run_together(stop_event, led_crazy, vib_crazy)

            else:
                print("[Effect Mapping] 알 수 없는 감정 → 따분함 효과로 대체")
                run_together(stop_event, led_bored, vib_none)

        finally:
            stop_vibration()

            if not stop_event.is_set() and not shutdown_event.is_set():
                print(f"[Effect] 감정 효과 종료: {emotion}")
                self.start_idle()


effect_controller = EffectController()


# =========================
# Audio utility
# =========================

def level_bar(level, threshold):
    max_level = max(threshold * 2.0, 0.02)
    ratio = min(level / max_level, 1.0)
    blocks = int(ratio * 30)
    bar = "█" * blocks + "-" * (30 - blocks)
    return f"[{bar}]"


def audio_level(chunk):
    if not chunk:
        return 0.0

    samples = array.array("h")
    samples.frombytes(chunk)

    if sys.byteorder != "little":
        samples.byteswap()

    if not samples:
        return 0.0

    step = max(1, len(samples) // 512)

    total = 0
    count = 0

    for i in range(0, len(samples), step):
        total += abs(samples[i])
        count += 1

    if count == 0:
        return 0.0

    return (total / count) / 32768.0


def save_debug_wav(chunks, filename):
    path = DEBUG_AUDIO_DIR / filename

    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(MIC_CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH)
        wf.setframerate(MIC_SAMPLE_RATE)
        wf.writeframes(b"".join(chunks))

    print(f"\n[Debug WAV 저장] {path}")
    return path


def start_arecord_process():
    cmd = [
        "arecord",
        "-D", AUDIO_DEVICE,
        "-c", str(MIC_CHANNELS),
        "-r", str(MIC_SAMPLE_RATE),
        "-f", "S16_LE",
        "-t", "raw",
        "-q",
    ]

    print()
    print("[arecord 실행 명령]")
    print(" ".join(cmd))

    return subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0
    )


def calibrate_noise(proc):
    print()
    print("=================================")
    print("주변 소음 측정 중")
    print(f"{CALIBRATE_SECONDS}초 동안 말하지 말고 조용히 있어주세요.")
    print("=================================")

    levels = []
    chunks_to_read = int(CALIBRATE_SECONDS / (CHUNK_FRAMES / MIC_SAMPLE_RATE))

    for _ in range(chunks_to_read):
        chunk = proc.stdout.read(CHUNK_BYTES)
        levels.append(audio_level(chunk))

    noise = sum(levels) / max(1, len(levels))

    start_threshold = max(noise * 1.25, noise + 0.004, MIN_START_THRESHOLD)
    stop_threshold = max(noise * 1.10, noise + 0.002, MIN_STOP_THRESHOLD)

    print()
    print("=================================")
    print("마이크 기준값")
    print("---------------------------------")
    print(f"주변 소음 레벨: {noise:.6f}")
    print(f"말 시작 기준값: {start_threshold:.6f}")
    print(f"말 종료 기준값: {stop_threshold:.6f}")
    print("=================================")

    return start_threshold, stop_threshold


# =========================
# Emotion classify + LED trigger
# =========================

async def classify_and_trigger_emotion(transcript):
    if not transcript or len(transcript.strip()) < 2:
        print("[Emotion] transcript가 너무 짧아서 감정 판단을 건너뜁니다.")
        return

    print()
    print("[PIPELINE] 감정 판단 시작")
    print(f"[PIPELINE] 입력 문장: {transcript}")

    try:
        emotion = await asyncio.to_thread(classify_emotion, transcript)

        print()
        print("=================================")
        print("[PIPELINE] 감정 매핑 완료")
        print(f"문장: {transcript}")
        print(f"감정: {emotion}")
        print("=================================")

        effect_controller.start_emotion(emotion)

    except Exception as e:
        print()
        print("=================================")
        print("[Emotion Error]")
        print("감정 판단 중 에러가 발생했습니다.")
        print(e)
        print("=================================")


# =========================
# Realtime API
# =========================

async def realtime_connect():
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "OpenAI-Safety-Identifier": "cloud-mood-lamp-full-pipeline-debug",
    }

    try:
        return await websockets.connect(
            REALTIME_URL,
            additional_headers=headers,
            ping_interval=20,
            ping_timeout=20,
            max_size=None,
        )
    except TypeError:
        return await websockets.connect(
            REALTIME_URL,
            extra_headers=headers,
            ping_interval=20,
            ping_timeout=20,
            max_size=None,
        )


async def send_session_update(ws):
    session_update = {
        "type": "session.update",
        "session": {
            "type": "transcription",
            "audio": {
                "input": {
                    "format": {
                        "type": "audio/pcm",
                        "rate": MIC_SAMPLE_RATE
                    },
                    "transcription": {
                        "model": TRANSCRIPTION_MODEL,
                        "language": "ko",
                        "delay": "minimal"
                    }
                }
            }
        }
    }

    await ws.send(json.dumps(session_update, ensure_ascii=False))
    print("[Realtime] session.update 전송 완료")


async def append_audio_chunk(ws, chunk):
    audio_b64 = base64.b64encode(chunk).decode("utf-8")

    event = {
        "type": "input_audio_buffer.append",
        "audio": audio_b64
    }

    await ws.send(json.dumps(event))


async def commit_audio_buffer(ws):
    await ws.send(json.dumps({"type": "input_audio_buffer.commit"}))


# =========================
# Receive Realtime events
# =========================

async def receive_events_loop(ws):
    print("[Receive] Realtime 이벤트 수신 대기 시작")

    async for message in ws:
        if shutdown_event.is_set():
            break

        try:
            event = json.loads(message)
        except json.JSONDecodeError:
            print()
            print("[Receive] JSON 파싱 실패")
            print(message)
            continue

        event_type = event.get("type", "")

        if PRINT_RAW_EVENTS and event_type not in [
            "conversation.item.input_audio_transcription.delta"
        ]:
            print()
            print(f"[Event] {event_type}")

        if event_type == "session.created":
            print("[Realtime] session.created")

        elif event_type == "session.updated":
            print("[Realtime] session.updated")
            print("이 메시지가 보이면 session.update까지 성공한 것입니다.")

        elif event_type == "error":
            print()
            print("=================================")
            print("[Realtime Error]")
            print(json.dumps(event, ensure_ascii=False, indent=2))
            print("=================================")

        elif event_type == "input_audio_buffer.committed":
            print("[Realtime] input_audio_buffer.committed")

        elif event_type == "conversation.item.input_audio_transcription.delta":
            delta = event.get("delta", "")
            if delta:
                print(delta, end="", flush=True)

        elif event_type == "conversation.item.input_audio_transcription.completed":
            transcript = event.get("transcript", "").strip()

            print()
            print()
            print("=================================")
            print("[PIPELINE] 완성된 문장 Transcript")
            print(transcript if transcript else "(빈 transcript)")
            print("=================================")

            await classify_and_trigger_emotion(transcript)

        elif event_type == "conversation.item.input_audio_transcription.failed":
            print()
            print("=================================")
            print("[Transcription failed]")
            print(json.dumps(event, ensure_ascii=False, indent=2))
            print("=================================")


# =========================
# Force send test
# =========================

async def force_send_test(ws, proc):
    print()
    print("=================================")
    print("강제 전송 + LED/진동 파이프라인 테스트")
    print("---------------------------------")
    print(f"지금부터 {FORCE_SEND_TEST_SECONDS}초 동안 말해보세요.")
    print("이 단계는 VAD 기준과 상관없이 무조건 Realtime으로 오디오를 보냅니다.")
    print("완성된 문장 → 감정 매핑 → LED/진동 실행까지 확인합니다.")
    print("예: 오늘 발표가 잘 끝나서 너무 기분이 좋아.")
    print("=================================")

    chunks = []
    start = time.time()
    sent_count = 0
    last_print = 0

    while time.time() - start < FORCE_SEND_TEST_SECONDS:
        chunk = await asyncio.to_thread(proc.stdout.read, CHUNK_BYTES)

        if not chunk:
            await asyncio.sleep(0.01)
            continue

        chunks.append(chunk)
        await append_audio_chunk(ws, chunk)
        sent_count += 1

        level = audio_level(chunk)
        now = time.time()

        if now - last_print >= LEVEL_PRINT_INTERVAL:
            print(
                f"[Force Level] {level:.6f} "
                f"{level_bar(level, 0.02)} "
                f"sent_chunks={sent_count}",
                end="\r"
            )
            last_print = now

    save_debug_wav(chunks, f"force_send_{int(time.time())}.wav")

    print()
    print("[Force] Realtime buffer commit 전송")
    await commit_audio_buffer(ws)

    print("[Force] transcript → 감정 → LED/진동 결과를 기다립니다.")
    await asyncio.sleep(7)


# =========================
# VAD stream loop
# =========================

async def vad_stream_loop(ws, proc, start_threshold, stop_threshold):
    print()
    print("=================================")
    print("자동 말소리 감지 + 전체 파이프라인 디버깅 시작")
    print("---------------------------------")
    print("이제 그냥 말해보세요.")
    print("Level → VAD → Transcript → Emotion → LED/Vibration 전체가 표시됩니다.")
    print("종료하려면 Ctrl + C")
    print("=================================")

    pre_roll = deque(maxlen=PRE_ROLL_CHUNKS)

    is_speaking = False
    speech_started_at = None
    last_loud_at = None
    loud_chunk_count = 0
    sent_any_audio = False
    sent_count = 0
    segment_chunks = []

    last_print = 0
    segment_index = 0

    while not shutdown_event.is_set():
        chunk = await asyncio.to_thread(proc.stdout.read, CHUNK_BYTES)

        if not chunk:
            await asyncio.sleep(0.01)
            continue

        level = audio_level(chunk)
        now = time.time()

        if now - last_print >= LEVEL_PRINT_INTERVAL:
            status = "REC" if is_speaking else "WAIT"
            print(
                f"[{status}] level={level:.6f} "
                f"start={start_threshold:.6f} stop={stop_threshold:.6f} "
                f"{level_bar(level, start_threshold)}",
                end="\r"
            )
            last_print = now

        if not is_speaking:
            pre_roll.append(chunk)

            if level > start_threshold:
                loud_chunk_count += 1
            else:
                loud_chunk_count = 0

            if loud_chunk_count >= START_CHUNKS_REQUIRED:
                is_speaking = True
                speech_started_at = now
                last_loud_at = now
                sent_any_audio = False
                sent_count = 0
                segment_chunks = list(pre_roll)

                print()
                print("[VAD] 말소리 감지 → Realtime 전송 시작")

                for old_chunk in list(pre_roll):
                    await append_audio_chunk(ws, old_chunk)
                    sent_any_audio = True
                    sent_count += 1

                pre_roll.clear()

                await append_audio_chunk(ws, chunk)
                sent_any_audio = True
                sent_count += 1
                segment_chunks.append(chunk)

        else:
            await append_audio_chunk(ws, chunk)
            sent_any_audio = True
            sent_count += 1
            segment_chunks.append(chunk)

            if level > stop_threshold:
                last_loud_at = now

            speech_duration = now - speech_started_at
            silence_duration = now - last_loud_at

            should_commit_by_silence = (
                speech_duration >= MIN_SPEECH_SECONDS
                and silence_duration >= SILENCE_SECONDS
            )

            should_commit_by_max = speech_duration >= MAX_SPEECH_SECONDS

            if should_commit_by_silence or should_commit_by_max:
                segment_index += 1

                print()
                print("=================================")
                print("[VAD] 문장 끝 감지")
                print(f"녹음 길이: {speech_duration:.2f}초")
                print(f"마지막 큰 소리 이후 침묵: {silence_duration:.2f}초")
                print(f"전송 chunk 수: {sent_count}")
                print("Realtime buffer commit 전송")
                print("=================================")

                save_debug_wav(
                    segment_chunks,
                    f"vad_segment_{int(time.time())}_{segment_index}.wav"
                )

                if sent_any_audio:
                    await commit_audio_buffer(ws)

                is_speaking = False
                speech_started_at = None
                last_loud_at = None
                loud_chunk_count = 0
                sent_any_audio = False
                sent_count = 0
                segment_chunks = []
                pre_roll.clear()

                await asyncio.sleep(0.15)


# =========================
# Main
# =========================

async def main_async():
    if not OPENAI_API_KEY:
        raise RuntimeError(
            "OPENAI_API_KEY가 설정되어 있지 않습니다. "
            "echo $OPENAI_API_KEY 로 먼저 확인하세요."
        )

    print()
    print("=================================")
    print("Cloud Mood Lamp Full Pipeline Debug")
    print("---------------------------------")
    print("목적:")
    print("1. 마이크 레벨 확인")
    print("2. Realtime transcript 확인")
    print("3. 감정 매핑 확인")
    print("4. LED/진동 효과 실행 확인")
    print("---------------------------------")
    print("종료: Ctrl + C")
    print("=================================")

    print(f"Realtime URL: {REALTIME_URL}")
    print(f"Transcription model: {TRANSCRIPTION_MODEL}")
    print(f"Audio device: {AUDIO_DEVICE}")
    print(f"Audio format: S16_LE / {MIC_SAMPLE_RATE}Hz / mono")
    print(f"Debug wav folder: {DEBUG_AUDIO_DIR}")

    print()
    print("[Hardware] LED/진동 초기화")
    clear_leds()
    stop_vibration()
    effect_controller.start_idle()

    print()
    print("[Realtime] WebSocket 연결 중...")

    async with await realtime_connect() as ws:
        print("[Realtime] WebSocket 연결 성공")

        await send_session_update(ws)

        receive_task = asyncio.create_task(receive_events_loop(ws))

        proc = start_arecord_process()

        try:
            # 1단계: VAD 상관없이 강제로 전체 파이프라인 확인
            await force_send_test(ws, proc)

            # 2단계: 자동 말소리 감지 기준 측정
            start_threshold, stop_threshold = calibrate_noise(proc)

            # 3단계: 자동 말소리 감지 + 전체 파이프라인 확인
            await vad_stream_loop(ws, proc, start_threshold, stop_threshold)

        finally:
            shutdown_event.set()

            try:
                proc.terminate()
                proc.wait(timeout=1)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

            receive_task.cancel()

            try:
                await receive_task
            except Exception:
                pass


def main():
    try:
        asyncio.run(main_async())

    except KeyboardInterrupt:
        print()
        print("사용자가 종료했습니다.")

    except Exception as e:
        print()
        print("실행 중 에러가 발생했습니다.")
        print(e)

    finally:
        shutdown_event.set()

        try:
            effect_controller.stop_all()
        except Exception:
            pass

        try:
            vib_pwm.stop()
            GPIO.cleanup()
        except Exception:
            pass

        print()
        print("디버깅 종료. LED off. Vibration off.")


if __name__ == "__main__":
    main()