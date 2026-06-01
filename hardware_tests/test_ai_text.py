import sys
from pathlib import Path

# 프로젝트 루트 경로를 Python이 찾을 수 있게 추가
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from src.emotion_ai import classify_emotion

# =========================
# Text Input → AI Emotion Test
# =========================

print("=================================")
print("Cloud Mood Lamp AI Emotion Test")
print("---------------------------------")
print("문장을 입력하면 AI가 감정을 판단합니다.")
print("아직 LED는 켜지지 않습니다.")
print("종료하려면 quit 입력")
print("=================================")

while True:
    text = input("\n문장 입력 > ").strip()

    if text.lower() in ["quit", "exit", "종료"]:
        print("테스트 종료")
        break

    if not text:
        print("문장을 입력해주세요.")
        continue

    try:
        emotion = classify_emotion(text)
        print(f"AI 감정 판단 결과: {emotion}")

    except Exception as e:
        print("AI 감정 판단 중 에러가 발생했습니다.")
        print("에러 내용:")
        print(e)