#!/usr/bin/env python3
"""DroidRig - Servo Choreography Server Entry Point."""

import argparse
from pathlib import Path

from droidrig.config import HOST, PORT
from droidrig.servo_config import ServoConfigStore
from droidrig.hardware import ServoController
from droidrig.animation import Animator
from droidrig.web import create_app

# Default config file location
CONFIG_FILE = Path(__file__).parent / "servo_config.json"


def main():
    """Initialize and run the DroidRig control server."""
    parser = argparse.ArgumentParser(description="DroidRig Servo Choreography Server")
    parser.add_argument(
        "-p", "--port",
        type=int,
        default=PORT,
        help=f"Port to run the server on (default: {PORT})",
    )
    parser.add_argument(
        "-c", "--config",
        type=Path,
        default=CONFIG_FILE,
        help=f"Path to servo config file (default: {CONFIG_FILE})",
    )
    args = parser.parse_args()

    # Load or create config
    print(f"Loading config from {args.config}...")
    config_store = ServoConfigStore.load(args.config)
    
    # Initialize hardware
    print(f"Initializing servo controller with {config_store.num_servos} servos...")
    servo = ServoController(config_store=config_store)
    
    # Initialize animator
    animator = Animator(servo)
    
    # Create Flask app
    app = create_app(servo, animator)
    
    # Print startup info
    print("=" * 50)
    print("  DroidRig - Servo Choreography Server")
    print("=" * 50)
    print(f"  Config: {args.config}")
    print(f"  Servos: {config_store.num_servos}")
    print(f"  Open http://localhost:{args.port} in your browser")
    print("  Or use your Pi's IP address from other devices")
    print("=" * 50)
    
    # Run server
    app.run(host=HOST, port=args.port)


if __name__ == "__main__":
    main()
