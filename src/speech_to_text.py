from pathlib import Path
from openai import OpenAI

# =========================
# Cloud Mood Lamp
# Speech To Text
# =========================

client = OpenAI()

# 먼저 저렴하고 빠른 모델을 시도하고,
# 만약 계정에서 지원하지 않으면 whisper-1로 다시 시도함.
STT_MODELS = [
    "gpt-4o-mini-transcribe",
    "whisper-1",
]


def transcribe_audio(audio_path):
    """
    녹음된 wav 파일을 텍스트로 변환한다.
    audio_path: wav 파일 경로
    return: 변환된 텍스트
    """

    audio_path = Path(audio_path)

    if not audio_path.exists():
        raise FileNotFoundError(f"오디오 파일을 찾을 수 없습니다: {audio_path}")

    last_error = None

    for model in STT_MODELS:
        try:
            print(f"STT 모델 사용 중: {model}")

            with open(audio_path, "rb") as audio_file:
                result = client.audio.transcriptions.create(
                    model=model,
                    file=audio_file,
                    language="ko",
                    response_format="text",
                )

            # response_format="text"이면 보통 문자열로 반환됨
            if isinstance(result, str):
                return result.strip()

            # 혹시 객체 형태로 반환되는 경우 대비
            if hasattr(result, "text"):
                return result.text.strip()

            return str(result).strip()

        except Exception as e:
            last_error = e
            print(f"{model} 모델로 STT 실패. 다음 모델을 시도합니다.")
            print(e)

    raise RuntimeError(f"모든 STT 모델이 실패했습니다: {last_error}")


if __name__ == "__main__":
    test_file = Path("state/voice_input.wav")
    text = transcribe_audio(test_file)
    print("STT 결과:")
    print(text)