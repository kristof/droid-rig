#!/usr/bin/env python3
"""
Audio Sync Calibration Tool for DroidRig

This script helps you find the optimal audio offset by playing a beep
and moving a servo simultaneously. Adjust the offset until they match.

Usage:
    uv run python calibrate_audio.py

Requirements:
    - A connected servo on channel 0
    - Speaker connected (WM8960 HAT or other)
    - A test beep sound file (will be created if missing)
"""

import time
import subprocess
import argparse
from pathlib import Path

# Try to import DroidRig modules
try:
    from droidrig.hardware import ServoController
    from droidrig.servo_config import ServoConfigStore
    HAS_HARDWARE = True
except ImportError:
    HAS_HARDWARE = False
    print("⚠ Hardware modules not available - running in simulation mode")


def create_test_beep(filepath: Path):
    """Create a simple beep WAV file using sox or ffmpeg."""
    if filepath.exists():
        return True
    
    print(f"Creating test beep file: {filepath}")
    
    # Try sox first
    try:
        subprocess.run(
            ['sox', '-n', str(filepath), 'synth', '0.1', 'sine', '880'],
            check=True,
            capture_output=True
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    
    # Try ffmpeg
    try:
        subprocess.run(
            ['ffmpeg', '-y', '-f', 'lavfi', '-i', 
             'sine=frequency=880:duration=0.1', str(filepath)],
            check=True,
            capture_output=True
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    
    print("❌ Could not create beep file. Install 'sox' or 'ffmpeg':")
    print("   sudo apt install sox")
    print("   or: sudo apt install ffmpeg")
    return False


def play_beep(filepath: Path):
    """Play the beep sound asynchronously."""
    try:
        return subprocess.Popen(
            ['aplay', '-q', str(filepath)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except FileNotFoundError:
        print("❌ 'aplay' not found")
        return None


def move_servo(servo, channel: int):
    """Quick servo movement: center → max → center."""
    if servo is None:
        print("  [SIMULATED] Servo moves!")
        return
    
    config = servo.get_servo_config(channel)
    center = config.center_pulse
    max_pos = config.max_pulse
    
    # Quick movement
    servo.set_position(channel, max_pos)
    time.sleep(0.15)
    servo.set_position(channel, center)


def run_test(servo, channel: int, offset_ms: int, beep_path: Path):
    """Run a single sync test with the given offset."""
    print(f"\n🎵 Testing with offset: {offset_ms}ms")
    print("   Watch the servo and listen for the beep...")
    
    time.sleep(0.5)  # Brief pause before test
    
    if offset_ms >= 0:
        # Positive offset: start audio, wait, then move servo
        play_beep(beep_path)
        if offset_ms > 0:
            time.sleep(offset_ms / 1000.0)
        move_servo(servo, channel)
    else:
        # Negative offset: move servo, wait, then play audio
        move_servo(servo, channel)
        time.sleep(abs(offset_ms) / 1000.0)
        play_beep(beep_path)
    
    time.sleep(0.5)  # Let audio finish


def main():
    parser = argparse.ArgumentParser(description="Calibrate audio sync offset")
    parser.add_argument("-c", "--channel", type=int, default=0,
                        help="Servo channel to test (default: 0)")
    parser.add_argument("-o", "--offset", type=int, default=150,
                        help="Starting offset in ms (default: 150)")
    args = parser.parse_args()
    
    # Setup
    beep_path = Path(__file__).parent / "test_beep.wav"
    
    if not create_test_beep(beep_path):
        return 1
    
    # Initialize servo
    servo = None
    if HAS_HARDWARE:
        try:
            config_path = Path(__file__).parent / "servo_config.json"
            config_store = ServoConfigStore.load(config_path)
            servo = ServoController(config_store=config_store)
            print(f"✓ Servo controller initialized (channel {args.channel})")
        except Exception as e:
            print(f"⚠ Could not initialize servo: {e}")
            print("  Running in simulation mode")
    
    offset = args.offset
    
    print("\n" + "=" * 50)
    print("  AUDIO SYNC CALIBRATION")
    print("=" * 50)
    print("""
Instructions:
  1. Watch the servo and listen for the beep
  2. They should happen at the SAME time
  3. Adjust the offset based on what you observe:
     
     Servo moves BEFORE beep → Increase offset (+)
     Servo moves AFTER beep  → Decrease offset (-) or go NEGATIVE
     
  Offset meaning:
     +150ms = Servo waits 150ms after audio starts
       0ms  = Both start together  
    -100ms = Servo starts 100ms BEFORE audio
     
Commands:
  Enter     - Run test with current offset
  +50 / -50 - Adjust offset (or any number)
  q         - Quit and show final offset
""")
    
    while True:
        try:
            cmd = input(f"\n[Offset: {offset}ms] Press Enter to test, or +/-N to adjust: ").strip()
            
            if cmd.lower() == 'q':
                break
            elif cmd == '':
                run_test(servo, args.channel, offset, beep_path)
            elif cmd.startswith('+') or cmd.startswith('-') or cmd.lstrip('-').isdigit():
                try:
                    if cmd.startswith('+'):
                        offset += int(cmd[1:] or 25)
                    elif cmd.startswith('-'):
                        offset -= int(cmd[1:] or 25)
                    else:
                        offset = int(cmd)
                    offset = max(-500, min(1000, offset))
                    print(f"   Offset set to {offset}ms")
                except ValueError:
                    print("   Invalid number")
            else:
                print("   Unknown command. Use Enter, +N, -N, or 'q'")
                
        except KeyboardInterrupt:
            break
    
    print(f"\n" + "=" * 50)
    print(f"  CALIBRATION COMPLETE")
    print(f"  Recommended offset: {offset}ms")
    print(f"=" * 50)
    print(f"""
To apply this offset:

1. In the web UI:
   - Load an audio file
   - Set the sync offset to {offset}ms

2. Or via API:
   curl -X POST http://localhost:5000/audio/offset \\
     -H "Content-Type: application/json" \\
     -d '{{"offset_ms": {offset}}}'
""")
    
    # Cleanup
    if beep_path.exists():
        beep_path.unlink()
    
    return 0


if __name__ == "__main__":
    exit(main())

