"""Flask web application for DroidRig."""

from flask import Flask, jsonify, request, render_template

from ..config import CENTER_PULSE, MIN_PULSE, MAX_PULSE
from ..servo_config import ServoSettings
from ..hardware.servo import ServoController
from ..animation.animator import Animator


def create_app(servo: ServoController, animator: Animator) -> Flask:
    """Create and configure the Flask application.
    
    Args:
        servo: ServoController instance
        animator: Animator instance
        
    Returns:
        Configured Flask application
    """
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )

    def get_all_servo_configs():
        """Get configuration for all servos."""
        return {
            i: servo.get_servo_config(i).to_dict()
            for i in range(servo.num_servos)
        }

    @app.route("/")
    def curves():
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

    return app
