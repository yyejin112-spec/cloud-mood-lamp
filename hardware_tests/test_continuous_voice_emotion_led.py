import sys
from pathlib import Path
import subprocess
import time
import threading
import random
import math
import wave
import queue
import array
from collections import deque

from rpi_ws281x import PixelStrip, Color
import RPi.GPIO as GPIO

# 프로젝트 루트 경로를 Python이 찾을 수 있게 추가
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from src.emotion_ai import classify_emotion
from src.speech_to_text import transcribe_audio


# =========================
# Cloud Mood Lamp
# Continuous Voice → STT → AI Emotion → Background LED/Vibration
# =========================

# Microphone settings
AUDIO_DEVICE = "plughw:3"       # arecord -l에서 card 3으로 잡힌 상태
SAMPLE_RATE = 48000
CHANNELS = 1
SAMPLE_WIDTH = 4                # S32_LE = 4 bytes
CHUNK_FRAMES = 2048             # 약 0.043초 단위
CHUNK_BYTES = CHUNK_FRAMES * SAMPLE_WIDTH

# Voice activity detection settings
CALIBRATE_SECONDS = 1.2         # 시작할 때 주변 소음 측정 시간
MIN_RECORD_SECONDS = 0.6        # 너무 짧은 소리는 무시
MAX_RECORD_SECONDS = 7.0        # 한 문장 최대 녹음 길이
SILENCE_SECONDS = 0.75          # 이 시간만큼 조용하면 말이 끝났다고 판단
PRE_ROLL_CHUNKS = 8             # 말 시작 직전 소리도 조금 포함
START_CHUNKS_REQUIRED = 1       # 소리가 연속으로 몇 번 커져야 말 시작으로 볼지

# 민감도 기본값
# 너무 자주 혼자 녹음되면 MIN_START_THRESHOLD를 올려.
# 말을 해도 녹음이 안 시작되면 MIN_START_THRESHOLD를 내려.
MIN_START_THRESHOLD = 0.0015
MIN_STOP_THRESHOLD = 0.0008

# Audio file output
AUDIO_DIR = PROJECT_ROOT / "state" / "voice_segments"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

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

# Queue: 녹음된 파일을 STT/AI 처리 스레드로 넘기기
audio_queue = queue.Queue()
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
    """
    LED 효과 중 새 감정이 들어오면 빨리 멈출 수 있게 하는 sleep.
    """
    end_time = time.time() + seconds
    while time.time() < end_time:
        if stop_event.is_set() or shutdown_event.is_set():
            return False
        time.sleep(0.01)
    return True


def set_idle_light():
    """
    아무 감정 효과가 없을 때 무드등이 켜져 있는 기본 상태.
    아주 은은한 차가운 흰빛/하늘빛.
    """
    set_all_scaled(120, 180, 255, 12)


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
# Background Effect Controller
# =========================

class EffectController:
    """
    LED/진동 효과를 백그라운드에서 실행하고,
    새 감정이 들어오면 이전 효과를 멈추고 새 효과로 바꾼다.
    """

    def __init__(self):
        self.lock = threading.Lock()
        self.stop_event = None
        self.thread = None
        self.current_emotion = None

    def start(self, emotion):
        with self.lock:
            self.stop_current_locked()

            self.stop_event = threading.Event()
            self.current_emotion = emotion

            self.thread = threading.Thread(
                target=self._run_effect,
                args=(emotion, self.stop_event),
                daemon=True
            )
            self.thread.start()

    def stop_current_locked(self):
        if self.stop_event:
            self.stop_event.set()

        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=0.2)

        stop_vibration()

    def stop(self):
        with self.lock:
            self.stop_current_locked()
            self.stop_event = None
            self.thread = None
            self.current_emotion = None
            clear_leds()

    def _run_effect(self, emotion, stop_event):
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

            # 새 감정 때문에 중단된 게 아니라 자연스럽게 끝났다면 기본 무드등 상태로 복귀
            if not stop_event.is_set() and not shutdown_event.is_set():
                set_idle_light()

            print(f"[Effect] 감정 효과 종료: {emotion}")


effect_controller = EffectController()


# =========================
# Audio recording / VAD
# =========================

def audio_level(chunk):
    """
    raw S32_LE 오디오 청크의 대략적인 음량을 계산한다.
    반환값은 0.0~1.0 근처의 작은 값.
    """
    if not chunk:
        return 0.0

    samples = array.array("i")
    samples.frombytes(chunk)

    if sys.byteorder != "little":
        samples.byteswap()

    if not samples:
        return 0.0

    # 계산량 줄이기 위해 일부 샘플만 사용
    step = max(1, len(samples) // 512)
    total = 0
    count = 0

    for i in range(0, len(samples), step):
        total += abs(samples[i])
        count += 1

    if count == 0:
        return 0.0

    return (total / count) / 2147483648.0


def save_wav(chunks, path):
    """
    raw S32_LE chunks를 wav 파일로 저장.
    """
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(b"".join(chunks))


def start_arecord_process():
    """
    arecord를 raw stream 모드로 실행.
    """
    cmd = [
        "arecord",
        "-D", AUDIO_DEVICE,
        "-c1",
        "-r", str(SAMPLE_RATE),
        "-f", "S32_LE",
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
    시작할 때 주변 소음 레벨을 측정해서 임계값을 자동 설정.
    """
    print()
    print("=================================")
    print("주변 소음 측정 중...")
    print(f"{CALIBRATE_SECONDS}초 동안 조용히 있어주세요.")
    print("=================================")

    levels = []
    chunks_to_read = int(CALIBRATE_SECONDS / (CHUNK_FRAMES / SAMPLE_RATE))

    for _ in range(chunks_to_read):
        chunk = proc.stdout.read(CHUNK_BYTES)
        level = audio_level(chunk)
        levels.append(level)

    noise = sum(levels) / max(1, len(levels))

    start_threshold = max(noise * 3.5, MIN_START_THRESHOLD)
    stop_threshold = max(noise * 2.0, MIN_STOP_THRESHOLD)

    print(f"주변 소음 레벨: {noise:.6f}")
    print(f"말 시작 기준값: {start_threshold:.6f}")
    print(f"말 종료 기준값: {stop_threshold:.6f}")

    return start_threshold, stop_threshold


def continuous_listen_loop():
    """
    계속 듣다가 말소리를 감지하면 자동 녹음하고,
    말이 끝나면 wav 파일로 저장해 queue에 넣는다.
    """
    proc = start_arecord_process()

    try:
        start_threshold, stop_threshold = calibrate_noise(proc)

        print()
        print("=================================")
        print("계속 듣는 중입니다.")
        print("이제 Enter 없이 말하면 됩니다.")
        print("종료하려면 Ctrl + C")
        print("=================================")

        pre_roll = deque(maxlen=PRE_ROLL_CHUNKS)
        is_recording = False
        recorded_chunks = []
        speech_start_time = None
        last_loud_time = None
        loud_chunk_count = 0
        segment_count = 0

        while not shutdown_event.is_set():
            chunk = proc.stdout.read(CHUNK_BYTES)

            if not chunk:
                continue

            level = audio_level(chunk)
            now = time.time()
            print(f"[Level] {level:.6f}", end="\r")

            if not is_recording:
                pre_roll.append(chunk)

                if level > start_threshold:
                    loud_chunk_count += 1
                else:
                    loud_chunk_count = 0

                if loud_chunk_count >= START_CHUNKS_REQUIRED:
                    is_recording = True
                    speech_start_time = now
                    last_loud_time = now
                    recorded_chunks = list(pre_roll)

                    print()
                    print("[Listen] 말소리 감지 → 녹음 시작")

            else:
                recorded_chunks.append(chunk)

                if level > stop_threshold:
                    last_loud_time = now

                record_duration = now - speech_start_time
                silence_duration = now - last_loud_time

                should_stop_by_silence = (
                    record_duration >= MIN_RECORD_SECONDS
                    and silence_duration >= SILENCE_SECONDS
                )
                should_stop_by_max = record_duration >= MAX_RECORD_SECONDS

                if should_stop_by_silence or should_stop_by_max:
                    is_recording = False
                    loud_chunk_count = 0
                    segment_count += 1

                    timestamp = int(time.time())
                    audio_path = AUDIO_DIR / f"voice_{timestamp}_{segment_count}.wav"
                    save_wav(recorded_chunks, audio_path)

                    print(f"[Listen] 녹음 종료 → {audio_path.name}")
                    audio_queue.put(audio_path)

                    recorded_chunks = []
                    pre_roll.clear()

    finally:
        if proc:
            proc.terminate()
            try:
                proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                proc.kill()


# =========================
# STT + AI worker
# =========================

def process_audio_worker():
    """
    녹음 파일이 생길 때마다 STT → AI 감정 판단 → LED/진동 효과 실행.
    이 작업은 백그라운드에서 돌아가므로 듣기는 계속된다.
    """
    while not shutdown_event.is_set():
        try:
            audio_path = audio_queue.get(timeout=0.2)
        except queue.Empty:
            continue

        if audio_path is None:
            break

        try:
            print()
            print(f"[Process] STT 변환 시작: {audio_path.name}")
            text = transcribe_audio(audio_path)

            print(f"[Process] STT 결과: {text}")

            if not text or len(text.strip()) < 2:
                print("[Process] 텍스트가 너무 짧아서 무시합니다.")
                continue

            print("[Process] AI 감정 판단 중...")
            emotion = classify_emotion(text)

            print(f"[Process] AI 감정 판단 결과: {emotion}")
            effect_controller.start(emotion)

        except Exception as e:
            print()
            print("[Process] 처리 중 에러 발생")
            print(e)

        finally:
            audio_queue.task_done()


# =========================
# Main
# =========================

def main():
    print()
    print("=================================")
    print("Cloud Mood Lamp Continuous Voice Mode")
    print("---------------------------------")
    print("무드등이 계속 듣다가,")
    print("한 문장이 끝나면 자동으로 감정을 판단하고")
    print("LED + 진동으로 공감합니다.")
    print()
    print("종료: Ctrl + C")
    print("=================================")

    set_idle_light()

    worker = threading.Thread(target=process_audio_worker, daemon=True)
    worker.start()

    try:
        continuous_listen_loop()

    except KeyboardInterrupt:
        print()
        print("사용자가 종료했습니다.")

    finally:
        shutdown_event.set()
        audio_queue.put(None)

        effect_controller.stop()
        clear_leds()
        stop_vibration()

        vib_pwm.stop()
        GPIO.cleanup()

        print("Cleaned up. LED off. Vibration off.")


if __name__ == "__main__":
    main()