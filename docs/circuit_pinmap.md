# Cloud Mood Lamp Circuit Pinmap

## Raspberry Pi GPIO Pin Map

| Function | GPIO | Physical Pin |
|---|---:|---:|
| NeoPixel LED Data | GPIO10 | Pin 19 |
| Servo Motor Signal | GPIO17 | Pin 11 |
| Vibration Motor AIN1 | GPIO23 | Pin 16 |
| Vibration Motor AIN2 | GPIO24 | Pin 18 |
| INMP441 SCK | GPIO18 | Pin 12 |
| INMP441 WS | GPIO19 | Pin 35 |
| INMP441 SD | GPIO20 | Pin 38 |
| INMP441 VDD | 3.3V | Pin 1 or 17 |
| Common GND | GND | Pin 6 |

## Power Rule

- Raspberry Pi is powered separately through USB-C.
- LED, servo motor, and vibration motor are powered by the external 5V 5A adapter.
- Raspberry Pi GND and external power GND must be connected together.
- INMP441 must use 3.3V, not 5V.