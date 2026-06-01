from openai import OpenAI

# =========================
# Cloud Mood Lamp
# AI Emotion Classifier
# =========================

client = OpenAI()

# 공식 Responses API 예시에서 사용하는 모델 계열.
# 만약 model not found 에러가 나면 이 줄만 다른 모델명으로 바꾸면 됨.
MODEL = "gpt-4.1"

ALLOWED_EMOTIONS = [
    "행복",
    "슬픔",
    "불안",
    "화남",
    "부끄러움",
    "따분함",
    "까칠함",
    "부러움",
    "미침",
]


def normalize_emotion(raw_text):
    """
    AI 응답에서 감정 이름만 안전하게 뽑아내는 함수.
    """
    text = raw_text.strip()

    for emotion in ALLOWED_EMOTIONS:
        if emotion in text:
            return emotion

    # 혹시 영어로 답했을 때를 대비한 보정
    english_map = {
        "happy": "행복",
        "sad": "슬픔",
        "anxious": "불안",
        "anxiety": "불안",
        "angry": "화남",
        "anger": "화남",
        "shy": "부끄러움",
        "embarrassed": "부끄러움",
        "bored": "따분함",
        "prickly": "까칠함",
        "irritable": "까칠함",
        "envy": "부러움",
        "jealous": "부러움",
        "crazy": "미침",
        "mad": "미침",
    }

    lower_text = text.lower()

    for key, value in english_map.items():
        if key in lower_text:
            return value

    # 그래도 모르겠으면 기본값
    return "따분함"


def classify_emotion(user_text):
    """
    사용자의 문장을 감정 하나로 분류한다.
    결과는 반드시 ALLOWED_EMOTIONS 중 하나로 반환한다.
    """

    prompt = f"""
너는 구름 무드등의 감정 판단 AI야.

사용자의 문장을 읽고, 아래 감정 중 가장 가까운 감정 하나만 골라.

가능한 감정:
{", ".join(ALLOWED_EMOTIONS)}

판단 기준:
- 행복: 기쁨, 만족, 설렘, 좋음, 신남, 기대됨
- 슬픔: 우울함, 속상함, 외로움, 지침, 눈물, 상실감
- 불안: 걱정, 초조, 긴장, 무서움, 마음이 불편함
- 화남: 분노, 짜증, 억울함, 폭발할 것 같음
- 부끄러움: 민망함, 쑥스러움, 얼굴이 빨개질 것 같음
- 따분함: 심심함, 지루함, 무기력함, 아무것도 하기 싫음
- 까칠함: 예민함, 날카로움, 퉁명스러움, 사소한 게 거슬림
- 부러움: 질투, 시샘, 나도 갖고 싶음, 비교됨
- 미침: 감정이 너무 격해짐, 정신없음, 과하게 흥분됨, 말이 과격함

규칙:
- 설명하지 마.
- 문장으로 답하지 마.
- 감정 이름 하나만 출력해.
- 반드시 가능한 감정 목록 중 하나만 출력해.

사용자 문장:
{user_text}
"""

    response = client.responses.create(
        model=MODEL,
        input=prompt,
    )

    raw_result = response.output_text.strip()
    return normalize_emotion(raw_result)


if __name__ == "__main__":
    print("AI emotion classifier test")
    print("종료하려면 quit 입력")

    while True:
        text = input("\n문장 입력 > ").strip()

        if text.lower() in ["quit", "exit", "종료"]:
            print("종료")
            break

        if not text:
            print("문장을 입력해주세요.")
            continue

        emotion = classify_emotion(text)
        print("AI 감정 판단:", emotion)