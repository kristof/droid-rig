"""Servo controller with position tracking."""

from typing import Dict, Optional
from .pca9685 import PCA9685
from ..config import (
    PCA9685_ADDRESS,
    PWM_FREQUENCY,
    MIN_PULSE,
    MAX_PULSE,
    CENTER_PULSE,
)
from ..servo_config import ServoConfigStore, ServoSettings


class ServoController:
    """High-level servo controller with position tracking and per-servo config."""

    def __init__(
        self, 
        num_servos: int = 2,
        config_store: Optional[ServoConfigStore] = None,
    ):
        """Initialize the servo controller.
        
        Args:
            num_servos: Number of servos to control (ignored if config_store provided)
            config_store: Optional ServoConfigStore for per-servo settings
        """
        self.pwm = PCA9685(PCA9685_ADDRESS)
        self.pwm.set_pwm_freq(PWM_FREQUENCY)
        self.positions: Dict[int, int] = {}
        
        # Use provided config or create default
        if config_store is not None:
            self.config = config_store
        else:
            self.config = ServoConfigStore(num_servos=num_servos)
        
        # Initialize all servos to their center positions
        self.center_all()

    @property
    def num_servos(self) -> int:
        """Number of servos configured."""
        return self.config.num_servos

    def get_servo_config(self, channel: int) -> ServoSettings:
        """Get configuration for a servo."""
        return self.config.get_servo(channel)

    def set_servo_config(self, channel: int, settings: ServoSettings) -> None:
        """Update configuration for a servo."""
        self.config.set_servo(channel, settings)

    def set_position(self, channel: int, position: int) -> int:
        """Set a servo to a specific position.
        
        Args:
            channel: Servo channel (0-based)
            position: Pulse width in microseconds
            
        Returns:
            The clamped position that was set
        """
        # Get per-servo limits
        servo_config = self.config.get_servo(channel)
        min_pos = servo_config.min_pulse
        max_pos = servo_config.max_pulse
        
        # Clamp position to servo's configured range
        position = max(min_pos, min(max_pos, position))
        
        self.pwm.set_servo_pulse(channel, position)
        self.positions[channel] = position
        
        return position

    def get_position(self, channel: int) -> int:
        """Get the current position of a servo.
        
        Args:
            channel: Servo channel (0-based)
            
        Returns:
            Current pulse width in microseconds
        """
        servo_config = self.config.get_servo(channel)
        return self.positions.get(channel, servo_config.center_pulse)

    def get_all_positions(self) -> Dict[int, int]:
        """Get positions of all servos.
        
        Returns:
            Dictionary mapping channel to position
        """
        return self.positions.copy()

    def center_all(self) -> None:
        """Move all servos to their configured center positions."""
        for i in range(self.num_servos):
            servo_config = self.config.get_servo(i)
            self.set_position(i, servo_config.center_pulse)

    def center_servo(self, channel: int) -> int:
        """Move a single servo to its configured center position."""
        servo_config = self.config.get_servo(channel)
        return self.set_position(channel, servo_config.center_pulse)

    def set_num_servos(self, num_servos: int) -> None:
        """Change the number of servos.
        
        Args:
            num_servos: New number of servos (1-16)
        """
        num_servos = max(1, min(16, num_servos))
        old_count = self.num_servos
        
        self.config.set_num_servos(num_servos)
        
        # Initialize new servos to their center
        for i in range(old_count, num_servos):
            servo_config = self.config.get_servo(i)
            self.set_position(i, servo_config.center_pulse)
        
        # Remove positions for servos that no longer exist
        for i in list(self.positions.keys()):
            if i >= num_servos:
                del self.positions[i]

    def save_config(self) -> None:
        """Save the servo configuration to disk."""
        self.config.save()
