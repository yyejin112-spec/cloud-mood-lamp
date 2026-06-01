import sys
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from src.speech_to_text import transcribe_audio
from src.emotion_ai import classify_emotion

AUDIO_DEVICE = "plughw:3"
AUDIO_FILE = PROJECT_ROOT / "state" / "voice_input.wav"
RECORD_SECONDS = 4


def record_audio():
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
    print(f"{RECORD_SECONDS}초 동안 말해보세요.")
    subprocess.run(cmd, check=True)
    print("녹음 완료")


def main():
    print("=================================")
    print("Voice → STT → AI Emotion Test")
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

            print("STT 변환 중...")
            text = transcribe_audio(AUDIO_FILE)
            print(f"STT 결과: {text}")

            print("AI 감정 판단 중...")
            emotion = classify_emotion(text)
            print(f"AI 감정 판단 결과: {emotion}")

        except Exception as e:
            print("에러 발생:")
            print(e)


if __name__ == "__main__":
    main()