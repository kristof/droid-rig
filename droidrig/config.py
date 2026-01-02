"""Configuration constants for DroidRig."""

# I2C address for PCA9685
PCA9685_ADDRESS = 0x40

# PWM frequency for servos (Hz)
PWM_FREQUENCY = 50

# Servo pulse range (microseconds)
MIN_PULSE = 800
MAX_PULSE = 2500
CENTER_PULSE = 1500

# Animation settings
STEP = 20  # Pulse increment per step
DELAY = 0.02  # Seconds between steps (20ms)

# Web server settings
HOST = "0.0.0.0"
PORT = 5000

