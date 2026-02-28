# *****************************************************************************
# * | File        :   lcd.py
# * | Author      :   Waveshare team (original), modified for BLE Key Agent
# * | Function    :   ST7789 LCD driver
# * | Info        :
# * | Original    :   example/1.3inch_LCD_HAT_python/ST7789.py
# *----------------
# * | This version:   V1.1 (removed ShowImage/numpy dependency)
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

import time

from .hw_config import RaspberryPi


class ST7789(RaspberryPi):
    """ST7789 240x240 LCD driver."""

    width: int = 240
    height: int = 240

    def command(self, cmd: int) -> None:
        self.digital_write(self.GPIO_DC_PIN, False)
        self.spi_writebyte([cmd])

    def data(self, val: int) -> None:
        self.digital_write(self.GPIO_DC_PIN, True)
        self.spi_writebyte([val])

    def reset(self) -> None:
        """Reset the display."""
        self.digital_write(self.GPIO_RST_PIN, True)
        time.sleep(0.01)
        self.digital_write(self.GPIO_RST_PIN, False)
        time.sleep(0.01)
        self.digital_write(self.GPIO_RST_PIN, True)
        time.sleep(0.01)

    def Init(self) -> None:
        """Initialize display."""
        self.module_init()
        self.reset()

        self.command(0x36)
        self.data(0x70)

        self.command(0x11)

        time.sleep(0.12)

        self.command(0x36)
        self.data(0x00)

        self.command(0x3A)
        self.data(0x05)

        self.command(0xB2)
        self.data(0x0C)
        self.data(0x0C)
        self.data(0x00)
        self.data(0x33)
        self.data(0x33)

        self.command(0xB7)
        self.data(0x00)

        self.command(0xBB)
        self.data(0x3F)

        self.command(0xC0)
        self.data(0x2C)

        self.command(0xC2)
        self.data(0x01)

        self.command(0xC3)
        self.data(0x0D)

        self.command(0xC6)
        self.data(0x0F)

        self.command(0xD0)
        self.data(0xA7)

        self.command(0xD0)
        self.data(0xA4)
        self.data(0xA1)

        self.command(0xD6)
        self.data(0xA1)

        self.command(0xE0)
        self.data(0xF0)
        self.data(0x00)
        self.data(0x02)
        self.data(0x01)
        self.data(0x00)
        self.data(0x00)
        self.data(0x27)
        self.data(0x43)
        self.data(0x3F)
        self.data(0x33)
        self.data(0x0E)
        self.data(0x0E)
        self.data(0x26)
        self.data(0x2E)

        self.command(0xE1)
        self.data(0xF0)
        self.data(0x07)
        self.data(0x0D)
        self.data(0x0D)
        self.data(0x0B)
        self.data(0x16)
        self.data(0x26)
        self.data(0x43)
        self.data(0x3E)
        self.data(0x3F)
        self.data(0x19)
        self.data(0x19)
        self.data(0x31)
        self.data(0x3A)

        self.command(0x21)

        self.command(0x29)

    def SetWindows(
        self, Xstart: int, Ystart: int, Xend: int, Yend: int
    ) -> None:
        """Set the display window for pixel data."""
        # Set the X coordinates
        self.command(0x2A)
        self.data(0x00)
        self.data(Xstart & 0xFF)
        self.data(0x00)
        self.data((Xend - 1) & 0xFF)

        # Set the Y coordinates
        self.command(0x2B)
        self.data(0x00)
        self.data(Ystart & 0xFF)
        self.data(0x00)
        self.data((Yend - 1) & 0xFF)

        self.command(0x2C)

    def clear(self) -> None:
        """Clear contents of image buffer."""
        _buffer = [0xFF] * (self.width * self.height * 2)
        self.SetWindows(0, 0, self.width, self.height)
        self.digital_write(self.GPIO_DC_PIN, True)
        for i in range(0, len(_buffer), 4096):
            self.spi_writebyte(_buffer[i : i + 4096])
