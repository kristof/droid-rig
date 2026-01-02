# DroidRig

**Servo Choreography Editor for Animatronic Robots**

DroidRig is a web-based servo control system designed for Raspberry Pi. It allows you to create, edit, and play back smooth servo animations through an intuitive browser interface—perfect for animatronics, puppetry, and robotics projects.

## Features

- 🎛️ **Live Control** — Real-time servo manipulation via sliders
- 🎬 **Timeline Editor** — Build keyframe-based animations visually
- ▶️ **Smooth Playback** — Interpolated transitions between keyframes
- 📤 **Export/Import** — Save and load animations as JSON
- ⚙️ **Per-Servo Config** — Custom names, min/max limits, and center for each servo
- 💾 **Persistent Settings** — Save configuration to the device
- 🌐 **Network Accessible** — Control from any device on your network
- 🔧 **REST API** — Integrate with external tools and scripts

## Hardware Requirements

- Raspberry Pi (any model with I2C support)
- **PCA9685** 16-channel PWM servo driver board
- Servo motors (up to 16 channels supported)
- 5V power supply for servos (do not power servos from the Pi)

### Wiring

Connect the PCA9685 to your Raspberry Pi via I2C:

| PCA9685 | Raspberry Pi |
|---------|--------------|
| VCC     | 3.3V (Pin 1) |
| GND     | GND (Pin 6)  |
| SDA     | SDA (Pin 3)  |
| SCL     | SCL (Pin 5)  |

Connect a separate 5-6V power supply to the PCA9685's V+ terminal block for the servos.

## Installation

### 1. Enable I2C on your Raspberry Pi

```bash
sudo raspi-config
# Navigate to: Interface Options → I2C → Enable
sudo reboot
```

### 2. Install DroidRig

Clone the repository and install dependencies:

```bash
git clone https://github.com/kristof/droid-rig.git
cd droid-rig

# Using uv (recommended)
uv sync

# Or using pip
pip install -e .
```

### 3. Verify I2C Connection

Check that your PCA9685 is detected (default address is `0x40`):

```bash
sudo i2cdetect -y 1
```

## Usage

### Start the Server

```bash
# Using uv
uv run python main.py

# Custom port
uv run python main.py --port 8080

# Custom config file location
uv run python main.py --config /path/to/servo_config.json
```

The server will start on `http://0.0.0.0:5000`. Open your browser and navigate to:

- **Local:** http://localhost:5000
- **Network:** http://[your-pi-ip]:5000

### Web Interface

DroidRig offers two editor modes:

- **Keyframe Editor** (`/`) — Add discrete keyframes with servo positions
- **Curve Editor** (`/curves`) — Draw continuous servo position curves over time

Switch between them using the link in the header.

#### Keyframe Editor

The keyframe editor has three main sections:

#### Live Control
Drag the sliders to move servos in real-time. Click **CENTER ALL** to return servos to their configured center positions.

Each servo has a **⚙ settings button** where you can configure:
- **Name/Alias** — Give your servo a descriptive name (e.g., "Head Pan", "Left Arm")
- **Min/Max Pulse** — Limit the servo's range to protect your mechanism
- **Center Pulse** — Set the neutral position for this servo

Use the **+/−** buttons in the status bar to add or remove servos (1-16 supported).

Click the **💾 save button** in the status bar to persist your configuration to the device. On next startup, your servo count, names, and limits will be restored automatically.

#### Quick Actions
- **PLAY PRESET** — Run a built-in demo animation
- **STOP** — Halt any running animation
- **PLAY TIMELINE** — Play your custom keyframe sequence

#### Animation Timeline
1. Position servos using the Live Control sliders
2. Set the transition duration (in milliseconds)
3. Click **ADD KEYFRAME** to capture the current positions
4. Repeat to build your animation sequence
5. Click **PLAY TIMELINE** to see it in action

Use **EXPORT JSON** to copy your animation to the clipboard, or **IMPORT JSON** to load a saved sequence.

#### Curve Editor

The curve editor provides a visual timeline where you can draw servo positions:

1. Each servo has its own horizontal track
2. Click and drag on a track to draw a position curve
3. The Y-axis represents pulse width (min at bottom, max at top)
4. The X-axis represents time
5. Set the total animation duration in the toolbar
6. Click **PREVIEW** to play the animation
7. Use **SMOOTH** to apply smoothing to jagged curves

## API Reference

All endpoints return JSON responses.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Web-based animation editor |
| `/api` | GET | List all available endpoints |
| `/status` | GET | Current animation state and servo positions |
| `/servo` | POST | Set a single servo position |
| `/servo/<id>/config` | GET | Get servo configuration |
| `/servo/<id>/config` | POST | Update servo configuration |
| `/animate` | POST | Play the preset animation |
| `/play` | POST | Play custom keyframe animation |
| `/center` | POST | Return all servos to their configured centers |
| `/stop` | POST | Stop current animation |
| `/config` | GET | Get global configuration and all servo settings |
| `/config` | POST | Update global configuration (e.g., numServos) |
| `/config/save` | POST | Save configuration to disk |

### Examples

**Set servo position:**
```bash
curl -X POST http://localhost:5000/servo \
  -H "Content-Type: application/json" \
  -d '{"channel": 0, "position": 2000}'
```

**Play custom animation:**
```bash
curl -X POST http://localhost:5000/play \
  -H "Content-Type: application/json" \
  -d '{
    "keyframes": [
      {"servos": {"0": 800, "1": 2500}, "duration": 500},
      {"servos": {"0": 2500, "1": 800}, "duration": 500},
      {"servos": {"0": 1500, "1": 1500}, "duration": 300}
    ]
  }'
```

**Check status:**
```bash
curl http://localhost:5000/status
```

**Configure a servo:**
```bash
curl -X POST http://localhost:5000/servo/0/config \
  -H "Content-Type: application/json" \
  -d '{"name": "Head Pan", "min_pulse": 1000, "max_pulse": 2000, "center_pulse": 1500}'
```

**Save configuration to device:**
```bash
curl -X POST http://localhost:5000/config/save
```

## Configuration

Edit `droidrig/config.py` to customize:

```python
# I2C address for PCA9685 (default: 0x40)
PCA9685_ADDRESS = 0x40

# PWM frequency for servos (Hz)
PWM_FREQUENCY = 50

# Servo pulse range (microseconds)
MIN_PULSE = 800    # Minimum position
MAX_PULSE = 2500   # Maximum position
CENTER_PULSE = 1500  # Neutral position

# Animation settings
STEP = 20          # Pulse increment per step
DELAY = 0.02       # Seconds between steps (20ms)

# Web server settings
HOST = "0.0.0.0"   # Listen on all interfaces
PORT = 5000        # Server port
```

## Troubleshooting

### "No module named 'smbus2'"
The smbus2 library should be installed automatically. If not:
```bash
pip install smbus2
```

### I2C permission denied
Add your user to the `i2c` group:
```bash
sudo usermod -aG i2c $USER
# Log out and back in
```

### Servos not responding
1. Check wiring connections
2. Verify I2C detection with `i2cdetect -y 1`
3. Ensure the servo power supply is connected
4. Check that PWM frequency is set to 50Hz for standard servos

## License

MIT License

