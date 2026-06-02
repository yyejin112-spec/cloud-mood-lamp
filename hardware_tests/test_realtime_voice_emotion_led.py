import sys
from pathlib import Path
import os
import json
import base64
import asyncio
import subprocess
import time
import threading
import random
import math
import array
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
# Realtime Voice → Transcript → AI Emotion → LED + Vibration
# =========================

# -------------------------
# OpenAI Realtime settings
# -------------------------

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# WebSocket 연결용 Realtime 모델
# 만약 model not found가 뜨면 "gpt-realtime-1.5" 또는 네 계정에서 가능한 Realtime 모델로 바꿔.
REALTIME_MODEL = "gpt-realtime-2"

# 실시간 전사용 모델
TRANSCRIPTION_MODEL = "gpt-realtime-whisper"

REALTIME_URL = f"wss://api.openai.com/v1/realtime?model={REALTIME_MODEL}"


# -------------------------
# Microphone settings
# -------------------------

# 네 INMP441이 arecord -l에서 card 3으로 잡혔던 상태 기준
AUDIO_DEVICE = "plughw:3"

# Realtime transcription 문서 기준으로 audio/pcm은 24kHz mono PCM 사용
MIC_SAMPLE_RATE = 24000
MIC_CHANNELS = 1
SAMPLE_WIDTH = 2              # S16_LE = 2 bytes
CHUNK_FRAMES = 1200           # 24000Hz 기준 0.05초
CHUNK_BYTES = CHUNK_FRAMES * SAMPLE_WIDTH

# 로컬 말 시작/끝 감지값
# 마이크 환경에 따라 아래 값은 조정 가능
CALIBRATE_SECONDS = 1.2
MIN_SPEECH_SECONDS = 0.45
MAX_SPEECH_SECONDS = 8.0
SILENCE_SECONDS = 0.55
PRE_ROLL_CHUNKS = 6
START_CHUNKS_REQUIRED = 1

# 너무 둔하면 낮추고, 혼자 반응하면 올리기
MIN_START_THRESHOLD = 0.010
MIN_STOP_THRESHOLD = 0.006

# 말소리 레벨을 터미널에 표시할지 여부
DEBUG_LEVEL = True
LEVEL_PRINT_INTERVAL = 0.25


# -------------------------
# NeoPixel LED settings
# -------------------------

LED_COUNT = 60
LED_PIN = 10          # GPIO10 = physical pin 19
LED_FREQ_HZ = 800000
LED_DMA = 10
LED_BRIGHTNESS = 35   # 너무 밝으면 20~40 추천
LED_INVERT = False
LED_CHANNEL = 0


# -------------------------
# DRV8833 vibration motor settings
# -------------------------

VIB_AIN1 = 23         # GPIO23 = physical pin 16
VIB_AIN2 = 24         # GPIO24 = physical pin 18
PWM_FREQ = 100


# -------------------------
# Runtime state
# -------------------------

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
# Idle warm breathing mood lamp
# =========================

def idle_warm_breathing(stop_event):
    """
    기본 무드등 상태:
    전구색이 숨쉬듯 부드럽게 밝아졌다 어두워지는 효과.
    """
    step = 0

    while not stop_event.is_set() and not shutdown_event.is_set():
        wave = (math.sin(step * 0.045) + 1) / 2

        # 10% ~ 35% 사이에서 숨쉬듯 변화
        percent = 10 + wave * 25

        # 전구색
        set_all_scaled(255, 170, 75, percent)

        step += 1
        time.sleep(0.035)


# =========================
# Emotion LED Effects
# =========================

def led_happy(stop_event):
    """
    행복:
    주황빛 노란색 + 불규칙한 반짝임
    """
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
    """
    슬픔:
    파란색 + 천천히 가라앉는 파동
    """
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
    """
    불안:
    붉은 주황색 + 부드러운 반짝임
    """
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
    """
    화남:
    실제 천둥번개처럼 엇박으로 번쩍이는 흰색 플래시
    """
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
    """
    부끄러움:
    핑크 + 천천히 붉어짐
    """
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
    """
    따분함:
    보라색 + 아주 느린 맥박
    """
    for step in range(100):
        if stop_event.is_set():
            return

        wave = (math.sin(step * 0.05) + 1) / 2
        percent = 8 + wave * 25
        set_all_scaled(120, 30, 180, percent)

        if not sleep_with_stop(stop_event, 0.08):
            return


def led_prickly(stop_event):
    """
    까칠함:
    완전 초록색 + 날카로운 스파이크
    """
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
    """
    부러움:
    청록 + 흐르는 파동
    """
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
    """
    미침:
    정신없는 무지개빛 LED 효과
    """
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
    """
    기본 전구색 숨쉬기 상태와 감정 효과 상태를 관리한다.
    """

    def __init__(self):
        self.lock = threading.Lock()

        self.idle_stop_event = threading.Event()
        self.idle_thread = None

        self.effect_stop_event = None
        self.effect_thread = None

    def start_idle(self):
        with self.lock:
            if self.idle_thread and self.idle_thread.is_alive():
                return

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
            print(f"[Effect] 감정 효과 요청: {emotion}")

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
                run_together(stop_event, led_happy, vib_happy)

            elif emotion == "슬픔":
                run_together(stop_event, led_sad, vib_soft)

            elif emotion == "불안":
                run_together(stop_event, led_anxious, vib_anxious)

            elif emotion == "화남":
                run_together(stop_event, led_angry_lightning, vib_angry)

            elif emotion == "부끄러움":
                run_together(stop_event, led_shy, vib_soft)

            elif emotion == "따분함":
                run_together(stop_event, led_bored, vib_none)

            elif emotion == "까칠함":
                run_together(stop_event, led_prickly, vib_prickly)

            elif emotion == "부러움":
                run_together(stop_event, led_envy, vib_soft)

            elif emotion == "미침":
                run_together(stop_event, led_crazy, vib_crazy)

            else:
                run_together(stop_event, led_bored, vib_none)

        finally:
            stop_vibration()

            if not stop_event.is_set() and not shutdown_event.is_set():
                print(f"[Effect] 감정 효과 종료: {emotion}")
                self.start_idle()


effect_controller = EffectController()


# =========================
# Audio helpers
# =========================

def audio_level(chunk):
    """
    S16_LE raw audio chunk의 대략적인 음량 계산.
    """
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


def start_arecord_process():
    """
    INMP441 마이크를 raw PCM stream으로 실행.
    파일 저장 없이 stdout으로 오디오 chunk를 계속 읽는다.
    """
    cmd = [
        "arecord",
        "-D", AUDIO_DEVICE,
        "-c", str(MIC_CHANNELS),
        "-r", str(MIC_SAMPLE_RATE),
        "-f", "S16_LE",
        "-t", "raw",
        "-q",
    ]

    return subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0
    )


def calibrate_noise(proc):
    """
    시작할 때 주변 소음 레벨 측정.
    """
    print()
    print("=================================")
    print("주변 소음 측정 중...")
    print(f"{CALIBRATE_SECONDS}초 동안 조용히 있어주세요.")
    print("=================================")

    levels = []
    chunks_to_read = int(CALIBRATE_SECONDS / (CHUNK_FRAMES / MIC_SAMPLE_RATE))

    for _ in range(chunks_to_read):
        chunk = proc.stdout.read(CHUNK_BYTES)
        levels.append(audio_level(chunk))

    noise = sum(levels) / max(1, len(levels))

    # 이전에 네 환경에서 기준값이 너무 높게 잡혔으므로
    # 보수적 배수 대신 noise + 작은 여유값 방식 사용
    start_threshold = max(noise * 1.25, noise + 0.004, MIN_START_THRESHOLD)
    stop_threshold = max(noise * 1.10, noise + 0.002, MIN_STOP_THRESHOLD)

    print(f"주변 소음 레벨: {noise:.6f}")
    print(f"말 시작 기준값: {start_threshold:.6f}")
    print(f"말 종료 기준값: {stop_threshold:.6f}")

    return start_threshold, stop_threshold


async def realtime_connect():
    """
    websockets 버전에 따라 headers 인자명이 달라질 수 있어서 둘 다 대응.
    """
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "OpenAI-Safety-Identifier": "cloud-mood-lamp-prototype",
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
    """
    Realtime transcription session 설정.
    """
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
                        "delay": "low"
                    }
                }
            }
        }
    }

    await ws.send(json.dumps(session_update, ensure_ascii=False))
    print("[Realtime] transcription session.update 전송 완료")


async def append_audio_chunk(ws, chunk):
    """
    raw PCM chunk를 base64로 바꿔 Realtime API에 전송.
    """
    audio_b64 = base64.b64encode(chunk).decode("utf-8")

    event = {
        "type": "input_audio_buffer.append",
        "audio": audio_b64
    }

    await ws.send(json.dumps(event))


async def commit_audio_buffer(ws):
    """
    현재까지 보낸 오디오 buffer를 문장 하나로 commit.
    """
    await ws.send(json.dumps({"type": "input_audio_buffer.commit"}))


async def clear_audio_buffer(ws):
    """
    문제가 생겼을 때 오디오 buffer 비우기.
    """
    await ws.send(json.dumps({"type": "input_audio_buffer.clear"}))


# =========================
# Realtime send / receive loops
# =========================

async def microphone_stream_loop(ws):
    """
    마이크를 계속 듣다가 말소리가 감지되면
    그 구간의 오디오 chunk를 Realtime API로 전송하고,
    말이 끝나면 commit한다.
    """
    proc = start_arecord_process()
    last_level_print = 0

    try:
        start_threshold, stop_threshold = calibrate_noise(proc)

        print()
        print("=================================")
        print("마이크 실시간 대기 시작")
        print("기본 상태에서는 전구색 숨쉬기 LED가 계속 켜져 있습니다.")
        print("말을 하면 문장 단위로 감정을 분석합니다.")
        print("종료하려면 Ctrl + C")
        print("=================================")

        pre_roll = deque(maxlen=PRE_ROLL_CHUNKS)

        is_speaking = False
        speech_started_at = None
        last_loud_at = None
        loud_chunk_count = 0
        sent_any_audio = False

        while not shutdown_event.is_set():
            chunk = await asyncio.to_thread(proc.stdout.read, CHUNK_BYTES)

            if not chunk:
                await asyncio.sleep(0.01)
                continue

            level = audio_level(chunk)
            now = time.time()

            if DEBUG_LEVEL and now - last_level_print >= LEVEL_PRINT_INTERVAL:
                print(f"[Level] {level:.6f}", end="\r")
                last_level_print = now

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

                    print()
                    print("[Listen] 말소리 감지 → 실시간 전송 시작")

                    # 말 앞부분이 잘리지 않도록 직전 chunk도 같이 보냄
                    for old_chunk in list(pre_roll):
                        await append_audio_chunk(ws, old_chunk)
                        sent_any_audio = True

                    pre_roll.clear()

                    await append_audio_chunk(ws, chunk)
                    sent_any_audio = True

            else:
                await append_audio_chunk(ws, chunk)
                sent_any_audio = True

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
                    print()
                    print("[Listen] 문장 끝 감지 → Realtime buffer commit")

                    if sent_any_audio:
                        await commit_audio_buffer(ws)

                    is_speaking = False
                    speech_started_at = None
                    last_loud_at = None
                    loud_chunk_count = 0
                    sent_any_audio = False
                    pre_roll.clear()

                    # 너무 연속해서 commit되지 않도록 아주 짧게 대기
                    await asyncio.sleep(0.1)

    finally:
        if proc:
            proc.terminate()

            try:
                proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                proc.kill()


async def receive_events_loop(ws):
    """
    Realtime API 이벤트 수신.
    completed transcript가 오면 감정 판단 후 LED/진동 효과 실행.
    """
    async for message in ws:
        if shutdown_event.is_set():
            break

        try:
            event = json.loads(message)
        except json.JSONDecodeError:
            print("[Realtime] JSON 파싱 실패:", message)
            continue

        event_type = event.get("type", "")

        if event_type == "session.created":
            print("[Realtime] session.created")

        elif event_type == "session.updated":
            print("[Realtime] session.updated")

        elif event_type == "error":
            print()
            print("[Realtime Error]")
            print(json.dumps(event, ensure_ascii=False, indent=2))

        elif event_type == "conversation.item.input_audio_transcription.delta":
            delta = event.get("delta", "")
            if delta:
                print(delta, end="", flush=True)

        elif event_type == "conversation.item.input_audio_transcription.completed":
            transcript = event.get("transcript", "").strip()

            print()
            print()
            print("=================================")
            print("[Transcript completed]")
            print(transcript)
            print("=================================")

            if not transcript:
                print("[AI] 빈 transcript라서 무시합니다.")
                continue

            print("[AI] 감정 판단 중...")

            try:
                emotion = await asyncio.to_thread(classify_emotion, transcript)

                print(f"[AI] 감정 판단 결과: {emotion}")
                effect_controller.start_emotion(emotion)

            except Exception as e:
                print("[AI] 감정 판단 중 에러 발생")
                print(e)

        elif event_type in [
            "input_audio_buffer.committed",
            "input_audio_buffer.cleared",
        ]:
            print(f"[Realtime] {event_type}")

        elif event_type in [
            "input_audio_buffer.speech_started",
            "input_audio_buffer.speech_stopped",
        ]:
            # 현재 코드는 로컬 VAD로 commit하므로 이 이벤트가 안 나올 수도 있음
            print(f"[Realtime] {event_type}")


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
    print("Cloud Mood Lamp Realtime Voice Mode")
    print("---------------------------------")
    print("기본 상태: 전구색 숨쉬기 무드등")
    print("말하기: 문장 끝나면 감정 분석 후 LED/진동 반응")
    print("종료: Ctrl + C")
    print("=================================")

    clear_leds()
    stop_vibration()
    effect_controller.start_idle()

    print("[Realtime] WebSocket 연결 중...")

    async with await realtime_connect() as ws:
        print("[Realtime] WebSocket 연결 성공")

        await send_session_update(ws)

        receive_task = asyncio.create_task(receive_events_loop(ws))
        mic_task = asyncio.create_task(microphone_stream_loop(ws))

        done, pending = await asyncio.wait(
            [receive_task, mic_task],
            return_when=asyncio.FIRST_EXCEPTION
        )

        for task in done:
            exc = task.exception()
            if exc:
                raise exc

        for task in pending:
            task.cancel()


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

        print("Cleaned up. LED off. Vibration off.")


if __name__ == "__main__":
    main()