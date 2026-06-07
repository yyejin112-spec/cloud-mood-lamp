import sys
import subprocess
from pathlib import Path

# 프로젝트 루트 경로 설정
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from src.speech_to_text import transcribe_audio

# =========================
# Microphone Record → STT Test
# =========================

# 너의 arecord -l 결과에서 card 3으로 잡혔으므로 plughw:3 사용
AUDIO_DEVICE = "plughw:2,0"

# 녹음 파일 저장 위치
AUDIO_FILE = PROJECT_ROOT / "state" / "voice_input.wav"

# 녹음 시간
RECORD_SECONDS = 4


def record_audio():
    """
    INMP441 마이크로 짧게 녹음해서 wav 파일로 저장한다.
    """
    AUDIO_FILE.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "arecord",
        "-D", AUDIO_DEVICE,
        "-c1",
        "-r", "48000",
        "-f", "S32_LE",
        "-d", str(RECORD_SECONDS),
        "-t", "wav",
        "-V", "mono",
        str(AUDIO_FILE),
    ]

    print()
    print("=================================")
    print("마이크 녹음 시작")
    print(f"{RECORD_SECONDS}초 동안 말해보세요.")
    print("예: 오늘 발표가 잘 끝나서 너무 기분이 좋아.")
    print("=================================")

    subprocess.run(cmd, check=True)

    print()
    print(f"녹음 완료: {AUDIO_FILE}")


def main():
    print("=================================")
    print("Cloud Mood Lamp Voice STT Test")
    print("---------------------------------")
    print("Enter를 누르면 녹음이 시작됩니다.")
    print("종료하려면 quit 입력")
    print("=================================")

    while True:
        user_input = input("\nEnter = 녹음 시작 / quit = 종료 > ").strip().lower()

        if user_input in ["quit", "exit", "종료"]:
            print("테스트 종료")
            break

        try:
            record_audio()

            print()
            print("STT 변환 중...")
            text = transcribe_audio(AUDIO_FILE)

            print()
            print("=================================")
            print("STT 변환 결과")
            print("---------------------------------")
            print(text)
            print("=================================")

        except Exception as e:
            print()
            print("테스트 중 에러가 발생했습니다.")
            print("에러 내용:")
            print(e)


if __name__ == "__main__":
    main()