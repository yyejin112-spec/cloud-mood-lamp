import os
import sys
import json
import base64
import asyncio
import subprocess
import time
import wave
import array
from pathlib import Path
from collections import deque

import websockets

# 프로젝트 루트 경로를 Python이 찾을 수 있게 추가
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from src.emotion_ai import classify_emotion


# =========================
# Cloud Mood Lamp
# Realtime STT + Emotion Mapping Debug Tool
# =========================
#
# 목적:
# 1. 마이크 입력 레벨 확인
# 2. 말소리 감지 확인
# 3. Realtime API로 오디오가 전송되는지 확인
# 4. 실시간 transcript delta 확인
# 5. completed transcript 확인
# 6. completed transcript가 어떤 감정으로 매핑되는지 확인
#
# LED / 진동은 일부러 사용하지 않음.
# 먼저 Realtime STT + 감정 판단만 확실히 확인하기 위한 파일.
# =========================


# -------------------------
# OpenAI Realtime settings
# -------------------------

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

TRANSCRIPTION_MODEL = "gpt-realtime-whisper"

# 네 계정에서는 intent=transcription 방식으로 실행되는 상태
REALTIME_URL = "wss://api.openai.com/v1/realtime?intent=transcription"


# -------------------------
# Microphone settings
# -------------------------

AUDIO_DEVICE = "plughw:3"

# Realtime transcription용 PCM 설정
MIC_SAMPLE_RATE = 24000
MIC_CHANNELS = 1
SAMPLE_WIDTH = 2              # S16_LE = 2 bytes
CHUNK_FRAMES = 1200           # 24000Hz 기준 약 0.05초
CHUNK_BYTES = CHUNK_FRAMES * SAMPLE_WIDTH

# 디버그 wav 저장 폴더
DEBUG_AUDIO_DIR = PROJECT_ROOT / "state" / "debug_realtime"
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

# 주변 소음이 높으면 자동 기준값이 이 값보다 높아짐
MIN_START_THRESHOLD = 0.006
MIN_STOP_THRESHOLD = 0.003

# 터미널 표시 설정
LEVEL_PRINT_INTERVAL = 0.08
PRINT_RAW_EVENTS = True
PRINT_LEVEL_BAR = True

# 처음 실행하자마자 강제로 몇 초 동안 전송하는 테스트
# 이 단계에서 말하면 VAD와 상관없이 Realtime API 자체가 되는지 확인 가능
FORCE_SEND_TEST_SECONDS = 6


shutdown_event = asyncio.Event()


# =========================
# Utility
# =========================

def level_bar(level, threshold):
    """
    터미널에서 보기 쉬운 음량 막대.
    """
    if not PRINT_LEVEL_BAR:
        return ""

    max_level = max(threshold * 2.0, 0.02)
    ratio = min(level / max_level, 1.0)
    blocks = int(ratio * 30)

    bar = "█" * blocks + "-" * (30 - blocks)
    return f"[{bar}]"


def audio_level(chunk):
    """
    S16_LE raw audio chunk의 대략적인 음량을 0~1 사이 값으로 계산.
    """
    if not chunk:
        return 0.0

    samples = array.array("h")
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

    return (total / count) / 32768.0


def save_debug_wav(chunks, filename):
    """
    디버그용 wav 파일 저장.
    나중에 aplay나 sox로 실제 소리가 들어갔는지 확인 가능.
    """
    path = DEBUG_AUDIO_DIR / filename

    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(MIC_CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH)
        wf.setframerate(MIC_SAMPLE_RATE)
        wf.writeframes(b"".join(chunks))

    print(f"\n[Debug WAV 저장] {path}")
    return path


def start_arecord_process():
    """
    INMP441 마이크를 raw PCM stream으로 실행.
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
    """
    시작 시 주변 소음 측정.
    """
    print()
    print("=================================")
    print("주변 소음 측정 중")
    print(f"{CALIBRATE_SECONDS}초 동안 말하지 말고 조용히 있어주세요.")
    print("=================================")

    levels = []
    chunks_to_read = int(CALIBRATE_SECONDS / (CHUNK_FRAMES / MIC_SAMPLE_RATE))

    for _ in range(chunks_to_read):
        chunk = proc.stdout.read(CHUNK_BYTES)
        level = audio_level(chunk)
        levels.append(level)

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


async def classify_and_print_emotion(transcript):
    """
    완성된 transcript를 감정으로 매핑하고 터미널에 출력.
    """
    if not transcript or len(transcript.strip()) < 2:
        print("[Emotion] transcript가 너무 짧아서 감정 판단을 건너뜁니다.")
        return

    print()
    print("[Emotion] 감정 판단 중...")

    try:
        emotion = await asyncio.to_thread(classify_emotion, transcript)

        print()
        print("=================================")
        print("[감정 매핑 결과]")
        print(f"문장: {transcript}")
        print(f"감정: {emotion}")
        print("=================================")

    except Exception as e:
        print()
        print("=================================")
        print("[Emotion Error]")
        print("감정 판단 중 에러가 발생했습니다.")
        print(e)
        print("=================================")


# =========================
# Realtime API helpers
# =========================

async def realtime_connect():
    """
    OpenAI Realtime WebSocket 연결.
    OpenAI-Beta 헤더는 사용하지 않음.
    """
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "OpenAI-Safety-Identifier": "cloud-mood-lamp-realtime-debug",
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
                        "delay": "minimal"
                    }
                }
            }
        }
    }

    await ws.send(json.dumps(session_update, ensure_ascii=False))
    print("[Realtime] session.update 전송 완료")


async def append_audio_chunk(ws, chunk):
    """
    raw PCM chunk를 base64로 변환해서 Realtime API에 전송.
    """
    audio_b64 = base64.b64encode(chunk).decode("utf-8")

    event = {
        "type": "input_audio_buffer.append",
        "audio": audio_b64
    }

    await ws.send(json.dumps(event))


async def commit_audio_buffer(ws):
    """
    현재까지 보낸 audio buffer를 commit.
    """
    await ws.send(json.dumps({"type": "input_audio_buffer.commit"}))


async def clear_audio_buffer(ws):
    """
    오디오 버퍼 비우기.
    """
    await ws.send(json.dumps({"type": "input_audio_buffer.clear"}))


# =========================
# Receive events
# =========================

async def receive_events_loop(ws):
    """
    Realtime API에서 오는 이벤트를 계속 출력.
    completed transcript가 오면 감정 매핑까지 확인.
    """
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

        elif event_type == "input_audio_buffer.cleared":
            print("[Realtime] input_audio_buffer.cleared")

        elif event_type == "conversation.item.input_audio_transcription.delta":
            delta = event.get("delta", "")
            if delta:
                print(delta, end="", flush=True)

        elif event_type == "conversation.item.input_audio_transcription.completed":
            transcript = event.get("transcript", "").strip()

            print()
            print()
            print("=================================")
            print("[완성된 문장 Transcript]")
            print(transcript if transcript else "(빈 transcript)")
            print("=================================")

            await classify_and_print_emotion(transcript)

        elif event_type == "conversation.item.input_audio_transcription.failed":
            print()
            print("=================================")
            print("[Transcription failed]")
            print(json.dumps(event, ensure_ascii=False, indent=2))
            print("=================================")


# =========================
# Forced send test
# =========================

async def force_send_test(ws, proc):
    """
    VAD 문제인지 API 문제인지 분리하기 위한 강제 전송 테스트.
    시작 후 몇 초 동안 무조건 마이크 오디오를 Realtime으로 보낸 뒤 commit한다.
    """
    print()
    print("=================================")
    print("강제 전송 테스트")
    print("---------------------------------")
    print(f"지금부터 {FORCE_SEND_TEST_SECONDS}초 동안 말해보세요.")
    print("이 단계는 말소리 감지 기준과 상관없이 무조건 Realtime으로 오디오를 보냅니다.")
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

    print("[Force] transcript + 감정 매핑 결과를 기다립니다. 잠시 기다려주세요.")
    await asyncio.sleep(4)


# =========================
# Local VAD send loop
# =========================

async def vad_stream_loop(ws, proc, start_threshold, stop_threshold):
    """
    로컬 VAD로 말 시작/끝을 감지해서 Realtime으로 전송.
    """
    print()
    print("=================================")
    print("자동 말소리 감지 디버깅 시작")
    print("---------------------------------")
    print("이제 그냥 말해보세요.")
    print("터미널에 Level 값, 말소리 감지, commit 여부, 감정 매핑 결과가 표시됩니다.")
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
    print("Cloud Mood Lamp Realtime STT + Emotion Debug")
    print("---------------------------------")
    print("목적:")
    print("1. 마이크 레벨 확인")
    print("2. Realtime 오디오 전송 확인")
    print("3. 실시간 transcript 확인")
    print("4. completed transcript 확인")
    print("5. transcript → 감정 매핑 확인")
    print("---------------------------------")
    print("종료: Ctrl + C")
    print("=================================")

    print(f"Realtime URL: {REALTIME_URL}")
    print(f"Transcription model: {TRANSCRIPTION_MODEL}")
    print(f"Audio device: {AUDIO_DEVICE}")
    print(f"Audio format: S16_LE / {MIC_SAMPLE_RATE}Hz / mono")
    print(f"Debug wav folder: {DEBUG_AUDIO_DIR}")

    print()
    print("[Realtime] WebSocket 연결 중...")

    async with await realtime_connect() as ws:
        print("[Realtime] WebSocket 연결 성공")

        await send_session_update(ws)

        receive_task = asyncio.create_task(receive_events_loop(ws))

        proc = start_arecord_process()

        try:
            # 먼저 VAD와 상관없이 강제로 보내서 API/마이크 자체 확인
            await force_send_test(ws, proc)

            # 그 다음 자동 말소리 감지 기준 측정
            start_threshold, stop_threshold = calibrate_noise(proc)

            # 자동 감지 테스트
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
        print()
        print("디버깅 종료")


if __name__ == "__main__":
    main()