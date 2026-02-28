# *****************************************************************************
# * | File        :   hw_config.py
# * | Author      :   Waveshare team (original), modified for BLE Key Agent
# * | Function    :   Hardware underlying interface for ST7789 LCD HAT
# * | Info        :
# * | Original    :   example/1.3inch_LCD_HAT_python/config.py
# *----------------
# * | This version:   V1.1 (stripped numpy, unused pins/methods)
# * | Date        :   2026-02-28
# ******************************************************************************
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documnetation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to  whom the Software is
# furished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS OR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#

import logging
import time

import spidev
from gpiozero import (
    DigitalInputDevice,
    DigitalOutputDevice,
    PWMOutputDevice,
)

# GPIO pin numbers for physical buttons
KEY1_PIN: int = 21
KEY2_PIN: int = 20


class RaspberryPi:
    """Hardware abstraction for Waveshare 1.3inch LCD HAT on Raspberry Pi."""

    def __init__(
        self,
        spi: spidev.SpiDev | None = None,
        spi_freq: int = 40_000_000,
        rst: int = 27,
        dc: int = 25,
        bl: int = 24,
        bl_freq: int = 1000,
    ) -> None:
        if spi is None:
            spi = spidev.SpiDev(0, 0)

        self.SPEED = spi_freq
        self.BL_freq = bl_freq

        # Output GPIO pins
        self.GPIO_RST_PIN = self._gpio_output(rst)
        self.GPIO_DC_PIN = self._gpio_output(dc)
        self.GPIO_BL_PIN = PWMOutputDevice(bl, frequency=bl_freq)
        self.bl_DutyCycle(0)

        # Input GPIO pins (buttons)
        self.GPIO_KEY1_PIN = self._gpio_input(KEY1_PIN)
        self.GPIO_KEY2_PIN = self._gpio_input(KEY2_PIN)

        # Initialize SPI
        self.SPI: spidev.SpiDev | None = spi
        if self.SPI is not None:
            self.SPI.max_speed_hz = spi_freq
            self.SPI.mode = 0b00

    @staticmethod
    def _gpio_output(pin: int) -> DigitalOutputDevice:
        return DigitalOutputDevice(pin, active_high=True, initial_value=False)

    @staticmethod
    def _gpio_input(pin: int) -> DigitalInputDevice:
        return DigitalInputDevice(pin, pull_up=True, active_state=None)

    @staticmethod
    def digital_write(pin: DigitalOutputDevice, value: bool) -> None:
        if value:
            pin.on()
        else:
            pin.off()

    @staticmethod
    def digital_read(pin: DigitalInputDevice) -> bool:
        return pin.value

    def spi_writebyte(self, data: list[int] | bytes) -> None:
        if self.SPI is not None:
            self.SPI.writebytes(data)

    def bl_DutyCycle(self, duty: int) -> None:
        self.GPIO_BL_PIN.value = duty / 100

    def module_init(self) -> int:
        if self.SPI is not None:
            self.SPI.max_speed_hz = self.SPEED
            self.SPI.mode = 0b00
        return 0

    def module_exit(self) -> None:
        logging.debug("spi end")
        if self.SPI is not None:
            self.SPI.close()

        logging.debug("gpio cleanup...")
        self.digital_write(self.GPIO_RST_PIN, True)
        self.digital_write(self.GPIO_DC_PIN, False)
        self.GPIO_BL_PIN.close()
        time.sleep(0.001)
