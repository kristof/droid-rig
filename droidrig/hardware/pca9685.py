"""PCA9685 16-Channel PWM Servo Driver for Raspberry Pi."""

import time
import math
import smbus2 as smbus


class PCA9685:
    """Driver for PCA9685 PWM controller."""

    # Registers
    _MODE1 = 0x00
    _PRESCALE = 0xFE
    _LED0_ON_L = 0x06
    _LED0_ON_H = 0x07
    _LED0_OFF_L = 0x08
    _LED0_OFF_H = 0x09

    def __init__(self, address: int = 0x40, debug: bool = False):
        """Initialize the PCA9685.
        
        Args:
            address: I2C address of the PCA9685 (default 0x40)
            debug: Enable debug output
        """
        self.bus = smbus.SMBus(1)
        self.address = address
        self.debug = debug
        
        if self.debug:
            print("Resetting PCA9685")
        self._write(self._MODE1, 0x00)

    def _write(self, reg: int, value: int) -> None:
        """Write an 8-bit value to the specified register."""
        self.bus.write_byte_data(self.address, reg, value)
        if self.debug:
            print(f"I2C: Write 0x{value:02X} to register 0x{reg:02X}")

    def _read(self, reg: int) -> int:
        """Read an unsigned byte from the I2C device."""
        result = self.bus.read_byte_data(self.address, reg)
        if self.debug:
            print(f"I2C: Device 0x{self.address:02X} returned 0x{result:02X} from reg 0x{reg:02X}")
        return result

    def set_pwm_freq(self, freq: int) -> None:
        """Set the PWM frequency.
        
        Args:
            freq: Frequency in Hz (typically 50 for servos)
        """
        prescaleval = 25000000.0  # 25MHz
        prescaleval /= 4096.0  # 12-bit
        prescaleval /= float(freq)
        prescaleval -= 1.0
        
        if self.debug:
            print(f"Setting PWM frequency to {freq} Hz")
            print(f"Estimated pre-scale: {prescaleval}")
        
        prescale = math.floor(prescaleval + 0.5)
        
        if self.debug:
            print(f"Final pre-scale: {prescale}")

        oldmode = self._read(self._MODE1)
        newmode = (oldmode & 0x7F) | 0x10  # sleep
        self._write(self._MODE1, newmode)  # go to sleep
        self._write(self._PRESCALE, int(math.floor(prescale)))
        self._write(self._MODE1, oldmode)
        time.sleep(0.005)
        self._write(self._MODE1, oldmode | 0x80)

    def set_pwm(self, channel: int, on: int, off: int) -> None:
        """Set a single PWM channel.
        
        Args:
            channel: PWM channel (0-15)
            on: On time (0-4095)
            off: Off time (0-4095)
        """
        self._write(self._LED0_ON_L + 4 * channel, on & 0xFF)
        self._write(self._LED0_ON_H + 4 * channel, on >> 8)
        self._write(self._LED0_OFF_L + 4 * channel, off & 0xFF)
        self._write(self._LED0_OFF_H + 4 * channel, off >> 8)
        
        if self.debug:
            print(f"channel: {channel}  LED_ON: {on} LED_OFF: {off}")

    def set_servo_pulse(self, channel: int, pulse: int) -> None:
        """Set the servo pulse width.
        
        The PWM frequency must be 50Hz for standard servos.
        
        Args:
            channel: PWM channel (0-15)
            pulse: Pulse width in microseconds (typically 500-2500)
        """
        pulse = pulse * 4096 / 20000  # PWM frequency is 50Hz, period is 20000us
        self.set_pwm(channel, 0, int(pulse))

    # Backwards compatibility aliases
    def setPWMFreq(self, freq: int) -> None:
        """Alias for set_pwm_freq (backwards compatibility)."""
        self.set_pwm_freq(freq)

    def setPWM(self, channel: int, on: int, off: int) -> None:
        """Alias for set_pwm (backwards compatibility)."""
        self.set_pwm(channel, on, off)

    def setServoPulse(self, channel: int, pulse: int) -> None:
        """Alias for set_servo_pulse (backwards compatibility)."""
        self.set_servo_pulse(channel, pulse)

