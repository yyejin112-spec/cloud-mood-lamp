from rpi_ws281x import PixelStrip, Color
import time

# =========================
# Smooth Rainbow Keep-On Test
# =========================

LED_COUNT = 60
LED_PIN = 10          # GPIO10 = 물리 핀 19
LED_FREQ_HZ = 800000
LED_DMA = 10
LED_BRIGHTNESS = 35   # 너무 밝으면 20~40 추천
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
    """0~255 값을 무지개 색으로 변환"""
    pos = pos % 256

    if pos < 85:
        return Color(255 - pos * 3, pos * 3, 0)
    elif pos < 170:
        pos -= 85
        return Color(0, 255 - pos * 3, pos * 3)
    else:
        pos -= 170
        return Color(pos * 3, 0, 255 - pos * 3)


def rainbow_step(offset):
    """현재 offset 값에 맞춰 LED 전체를 무지개색으로 세팅"""
    for i in range(LED_COUNT):
        color_index = (i * 256 // LED_COUNT + offset) % 256
        strip.setPixelColor(i, wheel(color_index))
    strip.show()


try:
    print("Rainbow LED keep-on test start")
    print("Press Ctrl + C to stop")

    offset = 0

    while True:
        rainbow_step(offset)
        offset = (offset + 1) % 256
        time.sleep(0.05)  # 숫자가 클수록 천천히 움직임

except KeyboardInterrupt:
    print("Stopped by user")
    print("LED is left on with the last rainbow color")