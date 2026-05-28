from rpi_ws281x import PixelStrip, Color
import time

# =========================
# NeoPixel LED Test
# =========================

LED_COUNT = 60        # LED 개수
LED_PIN = 10          # GPIO10, 물리 핀 19
LED_FREQ_HZ = 800000
LED_DMA = 10
LED_BRIGHTNESS = 30   # 0~255, 처음에는 낮게 테스트
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


def clear_leds():
    """모든 LED 끄기"""
    for i in range(LED_COUNT):
        strip.setPixelColor(i, Color(0, 0, 0))
    strip.show()


try:
    print("LED test start")

    clear_leds()
    time.sleep(1)

    print("1번 LED 빨간색")
    strip.setPixelColor(0, Color(255, 0, 0))
    strip.show()
    time.sleep(1)

    clear_leds()
    time.sleep(0.5)

    print("2번 LED 초록색")
    strip.setPixelColor(1, Color(0, 255, 0))
    strip.show()
    time.sleep(1)

    clear_leds()
    time.sleep(0.5)

    print("3번 LED 파란색")
    strip.setPixelColor(2, Color(0, 0, 255))
    strip.show()
    time.sleep(1)

    clear_leds()
    print("LED test done")

except KeyboardInterrupt:
    clear_leds()
    print("LED test stopped")