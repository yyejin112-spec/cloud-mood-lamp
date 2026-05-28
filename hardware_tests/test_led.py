from rpi_ws281x import PixelStrip, Color
import time

# =========================
# Cloud Mood Lamp
# Smooth Rainbow LED Test
# =========================

LED_COUNT = 60        # LED 개수
LED_PIN = 10          # GPIO10, 물리 핀 19
LED_FREQ_HZ = 800000
LED_DMA = 10
LED_BRIGHTNESS = 35   # 0~255, 처음엔 낮게. 너무 밝으면 20~40 추천
LED_INVERT = False
LED_CHANNEL = 0

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


def wheel(pos):
    """
    0~255 숫자를 무지개 색으로 바꿔주는 함수
    """
    if pos < 85:
        return Color(255 - pos * 3, pos * 3, 0)
    elif pos < 170:
        pos -= 85
        return Color(0, 255 - pos * 3, pos * 3)
    else:
        pos -= 170
        return Color(pos * 3, 0, 255 - pos * 3)


def rainbow_cycle(wait=0.03):
    """
    LED 전체가 무지개빛으로 부드럽게 흐르는 효과
    wait 값이 작을수록 빠르게 움직임
    """
    for j in range(256):
        for i in range(LED_COUNT):
            color_index = (i * 256 // LED_COUNT + j) & 255
            strip.setPixelColor(i, wheel(color_index))
        strip.show()
        time.sleep(wait)


def clear_leds():
    """
    모든 LED 끄기
    """
    for i in range(LED_COUNT):
        strip.setPixelColor(i, Color(0, 0, 0))
    strip.show()


try:
    print("Smooth rainbow LED test start")
    print("Press Ctrl + C to stop")

    while True:
        rainbow_cycle(wait=0.03)

except KeyboardInterrupt:
    print("Stopping LED test...")
    clear_leds()
    print("LED off")