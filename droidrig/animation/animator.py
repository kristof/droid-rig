"""Animation controller for servo sequences."""

import time
import threading
from typing import List, Dict, Any, Callable, Optional, TYPE_CHECKING

from ..config import MIN_PULSE, MAX_PULSE, CENTER_PULSE, STEP, DELAY
from ..hardware.servo import ServoController

if TYPE_CHECKING:
    from ..audio.player import AudioPlayer


class Animator:
    """Handles servo animation sequences."""

    def __init__(
        self,
        servo_controller: ServoController,
        audio_player: Optional["AudioPlayer"] = None,
    ):
        """Initialize the animator.
        
        Args:
            servo_controller: ServoController instance to use
            audio_player: Optional AudioPlayer for synchronized playback
        """
        self.servo = servo_controller
        self.audio_player = audio_player
        self._lock = threading.Lock()
        self._is_animating = False
        self._stop_requested = False

    def set_audio_player(self, audio_player: "AudioPlayer") -> None:
        """Set the audio player for synchronized playback.
        
        Args:
            audio_player: AudioPlayer instance
        """
        self.audio_player = audio_player

    @property
    def is_animating(self) -> bool:
        """Check if an animation is currently running."""
        return self._is_animating

    def stop(self) -> None:
        """Request the current animation to stop."""
        self._stop_requested = True
        # Also stop audio playback
        if self.audio_player:
            self.audio_player.stop()

    def sweep_servo(
        self,
        channel: int,
        start: int,
        end: int,
        step: int = STEP,
        delay: float = DELAY,
    ) -> None:
        """Smoothly sweep a servo from start to end position.
        
        Args:
            channel: Servo channel
            start: Starting pulse width
            end: Ending pulse width
            step: Pulse increment per step
            delay: Delay between steps in seconds
        """
        if start < end:
            positions = range(start, end + 1, step)
        else:
            positions = range(start, end - 1, -step)

        for pos in positions:
            if self._stop_requested:
                return
            self.servo.set_position(channel, pos)
            time.sleep(delay)

    def play_preset(self) -> bool:
        """Play the preset animation sequence.
        
        Returns:
            True if animation completed, False if already animating
        """
        with self._lock:
            if self._is_animating:
                return False
            self._is_animating = True
            self._stop_requested = False

        try:
            print("Starting servo animation sequence...")

            # Servo 0: sweep from center to max, then back
            self.sweep_servo(0, CENTER_PULSE, MAX_PULSE)
            self.sweep_servo(0, MAX_PULSE, CENTER_PULSE)

            if not self._stop_requested:
                time.sleep(0.5)

            # Servo 1: sweep from center to min, then back
            self.sweep_servo(1, CENTER_PULSE, MIN_PULSE)
            self.sweep_servo(1, MIN_PULSE, CENTER_PULSE)

            return True
        finally:
            with self._lock:
                self._is_animating = False

    def play_keyframes(
        self,
        keyframes: List[Dict[str, Any]],
        with_audio: bool = True,
    ) -> bool:
        """Play a custom animation from keyframes.
        
        Args:
            keyframes: List of keyframe dicts with 'servos' and 'duration' keys
            with_audio: Whether to play audio alongside animation (if available)
            
        Returns:
            True if animation completed, False if already animating
        """
        with self._lock:
            if self._is_animating:
                return False
            self._is_animating = True
            self._stop_requested = False

        try:
            # Start audio playback if available and requested
            has_audio = with_audio and self.audio_player and self.audio_player.current_audio_file
            audio_delay_thread = None
            
            if has_audio:
                latency = self.audio_player.get_latency_offset_sec()
                
                if latency >= 0:
                    # Positive offset: start audio first, wait, then start servos
                    self.audio_player.play(wait_for_start=True)
                    if latency > 0:
                        time.sleep(latency)
                else:
                    # Negative offset: start servos first, audio starts later
                    # Schedule audio to start after |latency| seconds
                    def delayed_audio():
                        time.sleep(abs(latency))
                        if not self._stop_requested:
                            self.audio_player.play(wait_for_start=False)
                    
                    audio_delay_thread = threading.Thread(target=delayed_audio, daemon=True)
                    audio_delay_thread.start()
            
            for frame in keyframes:
                if self._stop_requested:
                    break

                duration = frame.get("duration", 500) / 1000.0  # Convert ms to seconds
                raw_targets = frame.get("servos", {})
                
                # Convert string keys to int (JSON sends keys as strings)
                targets = {int(ch): val for ch, val in raw_targets.items()}

                # Calculate steps needed
                steps = max(1, int(duration / DELAY))

                # Get starting positions
                starts = {
                    ch: self.servo.get_position(ch) 
                    for ch in targets
                }

                for step_num in range(steps + 1):
                    if self._stop_requested:
                        break

                    t = step_num / steps  # Progress 0 to 1

                    for channel, target in targets.items():
                        start = starts.get(channel, CENTER_PULSE)
                        pos = int(start + (target - start) * t)
                        pos = max(MIN_PULSE, min(MAX_PULSE, pos))
                        self.servo.set_position(channel, pos)

                    time.sleep(DELAY)

            return True
        finally:
            with self._lock:
                self._is_animating = False

    def play_preset_async(self, callback: Optional[Callable[[], None]] = None) -> bool:
        """Play preset animation in a background thread.
        
        Args:
            callback: Optional function to call when animation completes
            
        Returns:
            True if animation started, False if already animating
        """
        if self._is_animating:
            return False

        def run():
            self.play_preset()
            if callback:
                callback()

        thread = threading.Thread(target=run)
        thread.start()
        return True

    def play_keyframes_async(
        self,
        keyframes: List[Dict[str, Any]],
        callback: Optional[Callable[[], None]] = None,
        with_audio: bool = True,
    ) -> bool:
        """Play keyframe animation in a background thread.
        
        Args:
            keyframes: List of keyframe dicts
            callback: Optional function to call when animation completes
            with_audio: Whether to play audio alongside animation (if available)
            
        Returns:
            True if animation started, False if already animating
        """
        if self._is_animating:
            return False

        def run():
            self.play_keyframes(keyframes, with_audio=with_audio)
            if callback:
                callback()

        thread = threading.Thread(target=run)
        thread.start()
        return True

