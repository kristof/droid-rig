"""Flask web application for DroidRig."""

from pathlib import Path
from flask import Flask, jsonify, request, render_template, send_from_directory

from ..config import CENTER_PULSE, MIN_PULSE, MAX_PULSE
from ..servo_config import ServoSettings
from ..hardware.servo import ServoController
from ..animation.animator import Animator
from ..animation.storage import AnimationStore, SavedAnimation
from ..audio.player import AudioPlayer


def create_app(
    servo: ServoController,
    animator: Animator,
    audio_player: AudioPlayer | None = None,
) -> Flask:
    """Create and configure the Flask application.
    
    Args:
        servo: ServoController instance
        animator: Animator instance
        audio_player: AudioPlayer instance for audio playback
        
    Returns:
        Configured Flask application
    """
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    
    # Create audio player if not provided
    # Pass config_store for persistent audio settings
    if audio_player is None:
        audio_player = AudioPlayer(config_store=servo.config)
    
    # Connect audio player to animator for synchronized playback
    animator.set_audio_player(audio_player)
    
    # Create animation store for saving/loading animations
    animation_store = AnimationStore()

    def get_all_servo_configs():
        """Get configuration for all servos."""
        return {
            i: servo.get_servo_config(i).to_dict()
            for i in range(servo.num_servos)
        }

    @app.route("/")
    def index():
        """Serve the animations overview page."""
        return render_template("animations.html")

    @app.route("/editor")
    def editor():
        """Serve the curve-based animation editor."""
        return render_template(
            "editor.html",
            num_servos=servo.num_servos,
            min_pulse=MIN_PULSE,
            max_pulse=MAX_PULSE,
            center_pulse=CENTER_PULSE,
        )

    @app.route("/api")
    def api_info():
        """Show available API endpoints."""
        return jsonify({
            "endpoints": {
                "/": "GET - Animation editor",
                "/animate": "POST - Trigger preset animation",
                "/play": "POST - Play custom keyframes",
                "/servo": "POST - Set individual servo position",
                "/servo/<id>/config": "GET/POST - Get or set servo configuration",
                "/status": "GET - Check status and positions",
                "/center": "POST - Return servos to center",
                "/stop": "POST - Stop current animation",
                "/config": "GET/POST - Get or set global configuration",
                "/config/save": "POST - Save configuration to disk",
            }
        })

    @app.route("/servo", methods=["POST"])
    def set_servo():
        """Set a single servo position."""
        if animator.is_animating:
            return jsonify({"status": "busy", "message": "Animation in progress"}), 409

        data = request.get_json()
        channel = int(data.get("channel", 0))
        
        # Use servo's configured center as default
        servo_config = servo.get_servo_config(channel)
        position = int(data.get("position", servo_config.center_pulse))

        actual_position = servo.set_position(channel, position)

        return jsonify({
            "status": "ok",
            "channel": channel,
            "position": actual_position,
        })

    @app.route("/servo/<int:channel>/config", methods=["GET", "POST"])
    def servo_config(channel: int):
        """Get or set configuration for a specific servo."""
        if channel < 0 or channel >= servo.num_servos:
            return jsonify({"status": "error", "message": "Invalid channel"}), 400

        if request.method == "GET":
            config = servo.get_servo_config(channel)
            return jsonify({
                "channel": channel,
                **config.to_dict(),
            })

        # POST: update servo config
        if animator.is_animating:
            return jsonify({"status": "busy", "message": "Animation in progress"}), 409

        data = request.get_json()
        current = servo.get_servo_config(channel)
        
        new_settings = ServoSettings(
            name=data.get("name", current.name),
            min_pulse=int(data.get("min_pulse", current.min_pulse)),
            max_pulse=int(data.get("max_pulse", current.max_pulse)),
            center_pulse=int(data.get("center_pulse", current.center_pulse)),
            color=data.get("color", current.color),
        )
        
        # Validate ranges
        if new_settings.min_pulse < MIN_PULSE:
            new_settings.min_pulse = MIN_PULSE
        if new_settings.max_pulse > MAX_PULSE:
            new_settings.max_pulse = MAX_PULSE
        if new_settings.min_pulse >= new_settings.max_pulse:
            return jsonify({"status": "error", "message": "min must be less than max"}), 400
        if not (new_settings.min_pulse <= new_settings.center_pulse <= new_settings.max_pulse):
            new_settings.center_pulse = (new_settings.min_pulse + new_settings.max_pulse) // 2
        
        servo.set_servo_config(channel, new_settings)
        
        # Auto-save to config file
        try:
            servo.save_config()
        except Exception:
            pass  # Don't fail if save doesn't work
        
        return jsonify({
            "status": "ok",
            "channel": channel,
            **new_settings.to_dict(),
        })

    @app.route("/animate", methods=["POST"])
    def trigger_animation():
        """Trigger the preset animation sequence."""
        if animator.is_animating:
            return jsonify({"status": "busy", "message": "Animation already in progress"}), 409

        animator.play_preset_async()
        return jsonify({"status": "started", "message": "Animation sequence started"})

    @app.route("/play", methods=["POST"])
    def play_custom():
        """Play custom keyframe animation."""
        if animator.is_animating:
            return jsonify({"status": "busy", "message": "Animation already in progress"}), 409

        data = request.get_json()
        keyframes_data = data.get("keyframes", [])

        if not keyframes_data:
            return jsonify({"status": "error", "message": "No keyframes provided"}), 400

        animator.play_keyframes_async(keyframes_data)
        return jsonify({
            "status": "started",
            "message": f"Playing {len(keyframes_data)} keyframes",
        })

    @app.route("/stop", methods=["POST"])
    def stop():
        """Stop current animation."""
        animator.stop()
        return jsonify({"status": "ok", "message": "Stop signal sent"})

    @app.route("/status", methods=["GET"])
    def get_status():
        """Get current animation status and servo positions."""
        return jsonify({
            "animating": animator.is_animating,
            "positions": servo.get_all_positions(),
            "servos": get_all_servo_configs(),
        })

    @app.route("/center", methods=["POST"])
    def center_servos():
        """Return all servos to center position."""
        if animator.is_animating:
            return jsonify({"status": "busy", "message": "Animation in progress"}), 409

        servo.center_all()
        return jsonify({"status": "ok", "message": "Servos centered"})

    @app.route("/config", methods=["GET", "POST"])
    def config():
        """Get or set global configuration."""
        if request.method == "GET":
            return jsonify({
                "numServos": servo.num_servos,
                "globalMinPulse": MIN_PULSE,
                "globalMaxPulse": MAX_PULSE,
                "globalCenterPulse": CENTER_PULSE,
                "servos": get_all_servo_configs(),
            })

        # POST: update config
        if animator.is_animating:
            return jsonify({"status": "busy", "message": "Animation in progress"}), 409

        data = request.get_json()
        if "numServos" in data:
            new_count = int(data["numServos"])
            servo.set_num_servos(new_count)
            
            # Auto-save to config file
            try:
                servo.save_config()
            except Exception:
                pass  # Don't fail if save doesn't work

        return jsonify({
            "status": "ok",
            "numServos": servo.num_servos,
            "globalMinPulse": MIN_PULSE,
            "globalMaxPulse": MAX_PULSE,
            "globalCenterPulse": CENTER_PULSE,
            "servos": get_all_servo_configs(),
        })

    @app.route("/config/save", methods=["POST"])
    def save_config():
        """Save current configuration to disk."""
        try:
            servo.save_config()
            return jsonify({"status": "ok", "message": "Configuration saved"})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    # Audio endpoints
    @app.route("/audio/upload", methods=["POST"])
    def upload_audio():
        """Upload an audio file for playback."""
        if "file" not in request.files:
            return jsonify({"status": "error", "message": "No file provided"}), 400
        
        file = request.files["file"]
        if not file.filename:
            return jsonify({"status": "error", "message": "No file selected"}), 400
        
        # Check file extension
        allowed_extensions = {".wav", ".mp3", ".ogg", ".flac"}
        ext = Path(file.filename).suffix.lower()
        if ext not in allowed_extensions:
            return jsonify({
                "status": "error",
                "message": f"Invalid file type. Allowed: {', '.join(allowed_extensions)}"
            }), 400
        
        try:
            # Save the file
            filepath = audio_player.save_audio(file.read(), file.filename)
            
            # Set as current audio
            audio_player.set_current_audio(filepath)
            
            # Get duration
            duration_ms = audio_player.get_audio_duration_ms(filepath)
            
            # Get waveform data for visualization
            waveform = audio_player.get_waveform_data(filepath, num_samples=200)
            
            return jsonify({
                "status": "ok",
                "filename": filepath.name,
                "duration_ms": duration_ms,
                "waveform": waveform,
            })
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route("/audio/current", methods=["GET"])
    def get_current_audio():
        """Get info about the current audio file."""
        if not audio_player.current_audio_file:
            return jsonify({
                "status": "ok",
                "has_audio": False,
            })
        
        filepath = audio_player.current_audio_file
        if not filepath.exists():
            audio_player.clear_audio()
            return jsonify({
                "status": "ok",
                "has_audio": False,
            })
        
        return jsonify({
            "status": "ok",
            "has_audio": True,
            "filename": filepath.name,
            "duration_ms": audio_player.get_audio_duration_ms(filepath),
            "waveform": audio_player.get_waveform_data(filepath, num_samples=200),
        })

    @app.route("/audio/select", methods=["POST"])
    def select_audio():
        """Select an existing audio file by filename."""
        data = request.get_json()
        filename = data.get("filename", "").strip()
        
        if not filename:
            return jsonify({"status": "error", "message": "Filename required"}), 400
        
        filepath = audio_player.audio_dir / filename
        if not filepath.exists():
            return jsonify({"status": "error", "message": "Audio file not found"}), 404
        
        audio_player.set_current_audio(filepath)
        
        return jsonify({
            "status": "ok",
            "filename": filename,
            "duration_ms": audio_player.get_audio_duration_ms(filepath),
        })

    @app.route("/audio/clear", methods=["POST"])
    def clear_audio():
        """Clear the current audio file."""
        audio_player.clear_audio()
        return jsonify({"status": "ok", "message": "Audio cleared"})

    @app.route("/audio/file/<filename>")
    def serve_audio_file(filename: str):
        """Serve an audio file for browser playback."""
        return send_from_directory(audio_player.audio_dir, filename)

    @app.route("/audio/list", methods=["GET"])
    def list_audio_files():
        """List all available audio files."""
        return jsonify({
            "status": "ok",
            "files": audio_player.list_audio_files(),
        })

    @app.route("/audio/offset", methods=["GET", "POST"])
    def audio_offset():
        """Get or set the audio latency offset for sync adjustment."""
        if request.method == "GET":
            return jsonify({
                "status": "ok",
                "offset_ms": audio_player.audio_offset_ms,
            })
        
        # POST: update offset
        data = request.get_json()
        offset = int(data.get("offset_ms", 150))
        audio_player.audio_offset_ms = offset  # Property handles clamping
        
        # Auto-save to config file
        try:
            servo.save_config()
        except Exception:
            pass  # Don't fail if save doesn't work
        
        return jsonify({
            "status": "ok",
            "offset_ms": audio_player.audio_offset_ms,
            "message": f"Audio offset set to {audio_player.audio_offset_ms}ms (saved)"
        })

    # Animation storage endpoints
    @app.route("/animations/list", methods=["GET"])
    def list_animations():
        """List all saved animations."""
        return jsonify({
            "status": "ok",
            "animations": animation_store.list_all(),
        })

    @app.route("/animations/save", methods=["POST"])
    def save_animation():
        """Save an animation."""
        data = request.get_json()
        
        name = data.get("name", "").strip()
        if not name:
            return jsonify({"status": "error", "message": "Name is required"}), 400
        
        # Get current audio file if any
        audio_file = None
        if audio_player.current_audio_file:
            audio_file = audio_player.current_audio_file.name
        
        animation = SavedAnimation(
            name=name,
            duration_ms=data.get("duration_ms", 3000),
            curves=data.get("curves", {}),
            annotations=data.get("annotations", []),
            audio_file=audio_file,
        )
        
        # Check if updating existing
        existing = animation_store.load(name)
        if existing:
            animation.created_at = existing.created_at
        
        filepath = animation_store.save(animation)
        
        return jsonify({
            "status": "ok",
            "message": f"Animation '{name}' saved",
            "filename": filepath.stem,
        })

    @app.route("/animations/load/<filename>", methods=["GET"])
    def load_animation(filename: str):
        """Load an animation by filename."""
        animation = animation_store.load_by_filename(filename)
        
        if not animation:
            return jsonify({"status": "error", "message": "Animation not found"}), 404
        
        return jsonify({
            "status": "ok",
            "animation": animation.to_dict(),
        })

    @app.route("/animations/delete/<filename>", methods=["POST"])
    def delete_animation(filename: str):
        """Delete an animation."""
        # Load first to get the name
        animation = animation_store.load_by_filename(filename)
        if not animation:
            return jsonify({"status": "error", "message": "Animation not found"}), 404
        
        if animation_store.delete(animation.name):
            return jsonify({
                "status": "ok",
                "message": f"Animation '{animation.name}' deleted",
            })
        
        return jsonify({"status": "error", "message": "Failed to delete"}), 500

    @app.route("/animations/play/<filename>", methods=["POST"])
    def play_saved_animation(filename: str):
        """Play a saved animation by filename."""
        if animator.is_animating:
            return jsonify({"status": "busy", "message": "Animation already in progress"}), 409
        
        animation = animation_store.load_by_filename(filename)
        if not animation:
            return jsonify({"status": "error", "message": "Animation not found"}), 404
        
        # Generate keyframes from curves
        keyframes = []
        sample_interval = 50  # ms
        
        for t in range(0, animation.duration_ms + 1, sample_interval):
            servos = {}
            for servo_id, points in animation.curves.items():
                servos[servo_id] = _get_value_at_time(points, t, CENTER_PULSE)
            
            keyframes.append({
                "servos": servos,
                "duration": sample_interval,
            })
        
        if not keyframes:
            return jsonify({"status": "error", "message": "Animation has no data"}), 400
        
        # If animation has audio, set it as current for playback
        with_audio = False
        if animation.audio_file:
            audio_path = audio_player.audio_dir / animation.audio_file
            if audio_path.exists():
                audio_player.set_current_audio(audio_path)
                with_audio = True
        
        animator.play_keyframes_async(keyframes, with_audio=with_audio)
        
        return jsonify({
            "status": "started",
            "message": f"Playing '{animation.name}'",
            "duration_ms": animation.duration_ms,
            "has_audio": with_audio,
        })

    def _get_value_at_time(points: list, time: int, default: int) -> int:
        """Interpolate curve value at a given time."""
        if not points:
            return default
        
        before = None
        after = None
        
        for p in points:
            if p["time"] <= time:
                before = p
            elif after is None:
                after = p
        
        if not before and not after:
            return default
        if not before:
            return after["pulse"]
        if not after:
            return before["pulse"]
        
        # Linear interpolation
        t = (time - before["time"]) / (after["time"] - before["time"])
        return round(before["pulse"] + (after["pulse"] - before["pulse"]) * t)

    return app
