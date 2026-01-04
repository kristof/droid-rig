# DroidRig

**Servo Choreography Editor for Animatronic Robots**

DroidRig is a web-based servo control system designed for Raspberry Pi. It allows you to create, edit, and play back smooth servo animations through an intuitive browser interface—perfect for animatronics, puppetry, and robotics projects.

## Features

- 🎛️ **Live Control** — Real-time servo manipulation via sliders
- 🎬 **Timeline Editor** — Build keyframe-based animations visually
- ▶️ **Smooth Playback** — Interpolated transitions between keyframes
- 🔊 **Audio Sync** — Upload audio files and play them in sync with servo animations
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
- *(Optional)* **Waveshare WM8960 Audio HAT** for synchronized audio playback

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

#### With Audio Support

If you're using the WM8960 Audio HAT for synchronized audio playback:

```bash
# Using uv
uv sync --extra audio

# Or using pip
pip install -e ".[audio]"

# Install system dependencies for audio playback
sudo apt install mpg123  # For MP3 playback
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

#### Audio Sync

The curve editor supports synchronized audio playback with your animations:

1. Click the **upload icon** in the AUDIO row (or drag-and-drop an audio file)
2. Supported formats: WAV, MP3, OGG, FLAC
3. When audio is uploaded, the timeline duration automatically adjusts to match the audio length
4. A waveform visualization appears in the audio track
5. Press **Play** to hear the audio while servos animate
6. Audio plays through the WM8960 HAT on the Pi and previews in your browser
7. Click the **×** button to remove the audio

**Sync Offset Adjustment:**

When audio is loaded, a sync control appears in the audio track (🔄 icon with ms value). This compensates for audio buffering latency:

- **Default:** 150ms delay before servos start (to let audio buffer)
- **If servos move too early:** Increase the value (e.g., 200, 250ms)
- **If servos move too late:** Decrease the value (e.g., 100, 50, or even negative)

The optimal value depends on your hardware and audio file format. WAV files typically have lower latency than MP3.

**Note:** The sync offset is automatically saved to your config file and persists across restarts.

This is perfect for lip-sync animations, musical performances, or any animatronic that needs to move in time with sound.

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
| `/play` | POST | Play custom keyframe animation (with audio if loaded) |
| `/center` | POST | Return all servos to their configured centers |
| `/stop` | POST | Stop current animation and audio |
| `/config` | GET | Get global configuration and all servo settings |
| `/config` | POST | Update global configuration (e.g., numServos) |
| `/config/save` | POST | Save configuration to disk |
| `/audio/upload` | POST | Upload an audio file (WAV, MP3, OGG, FLAC) |
| `/audio/current` | GET | Get current audio info and waveform data |
| `/audio/clear` | POST | Remove the current audio file |
| `/audio/file/<name>` | GET | Stream an audio file for browser playback |
| `/audio/list` | GET | List all uploaded audio files |
| `/audio/offset` | GET | Get current audio sync offset (ms) |
| `/audio/offset` | POST | Set audio sync offset for timing adjustment |

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

**Upload audio file:**
```bash
curl -X POST http://localhost:5000/audio/upload \
  -F "file=@my_audio.wav"
```

**Get current audio info:**
```bash
curl http://localhost:5000/audio/current
```

**Adjust audio sync offset:**
```bash
# Get current offset
curl http://localhost:5000/audio/offset

# Set offset to 200ms (if servos are early)
curl -X POST http://localhost:5000/audio/offset \
  -H "Content-Type: application/json" \
  -d '{"offset_ms": 200}'
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

### Audio not playing
1. Verify the WM8960 HAT is properly installed and configured
2. Check that audio works with `aplay test.wav`
3. For MP3 files, ensure mpg123 is installed: `sudo apt install mpg123`
4. Verify audio device with `aplay -l`

### WM8960 HAT setup
Follow the Waveshare WM8960 setup instructions to configure the audio HAT:
```bash
git clone https://github.com/waveshare/WM8960-Audio-HAT
cd WM8960-Audio-HAT
sudo ./install.sh
sudo reboot
```

## License

MIT License

