"""Audio player for Waveshare WM8960 Audio HAT."""

import os
import subprocess
import threading
from pathlib import Path
from typing import Optional
import wave
import struct

try:
    from pydub import AudioSegment
    HAS_PYDUB = True
except ImportError:
    HAS_PYDUB = False

try:
    from mutagen.mp3 import MP3
    HAS_MUTAGEN = True
except ImportError:
    HAS_MUTAGEN = False


class AudioPlayer:
    """Audio player that uses ALSA for playback on WM8960 HAT."""

    def __init__(self, audio_dir: Optional[Path] = None, config_store=None):
        """Initialize the audio player.
        
        Args:
            audio_dir: Directory to store uploaded audio files
            config_store: ServoConfigStore for persistent settings
        """
        self.audio_dir = audio_dir or Path(__file__).parent.parent.parent / "audio_files"
        self.audio_dir.mkdir(exist_ok=True)
        self._config_store = config_store
        
        # Fallback values if no config store
        self._local_offset_ms = 150
        self._local_current_file: Optional[Path] = None
        
        self._current_process: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._is_playing = False
        self._play_started_event = threading.Event()
        
        # Restore current audio from config on startup
        self._restore_current_audio()

    @property
    def is_playing(self) -> bool:
        """Check if audio is currently playing."""
        return self._is_playing

    @property
    def current_audio_file(self) -> Optional[Path]:
        """Get the path to the current audio file."""
        if self._config_store and self._config_store.current_audio_file:
            path = self.audio_dir / self._config_store.current_audio_file
            if path.exists():
                return path
            # File doesn't exist anymore, clear the config
            self._config_store.current_audio_file = ""
        return self._local_current_file
    
    def _restore_current_audio(self) -> None:
        """Restore current audio file from config on startup."""
        if self._config_store and self._config_store.current_audio_file:
            path = self.audio_dir / self._config_store.current_audio_file
            if path.exists():
                print(f"Restored audio: {self._config_store.current_audio_file}")

    def get_audio_duration_ms(self, filepath: Path) -> int:
        """Get the duration of an audio file in milliseconds.
        
        Args:
            filepath: Path to the audio file
            
        Returns:
            Duration in milliseconds
        """
        suffix = filepath.suffix.lower()
        
        if suffix == '.wav':
            return self._get_wav_duration_ms(filepath)
        elif suffix == '.mp3':
            # Try multiple methods for MP3
            if HAS_MUTAGEN:
                duration = self._get_mp3_duration_mutagen(filepath)
                if duration > 0:
                    return duration
            if HAS_PYDUB:
                try:
                    audio = AudioSegment.from_mp3(filepath)
                    return len(audio)
                except Exception:
                    pass
            # Try ffprobe
            duration = self._get_duration_ffprobe(filepath)
            if duration > 0:
                return duration
            # Last resort: estimate from file size
            return self._estimate_mp3_duration(filepath)
        elif HAS_PYDUB:
            # Try pydub for other formats
            try:
                audio = AudioSegment.from_file(filepath)
                return len(audio)
            except Exception:
                pass
        
        # Fallback: use ffprobe if available
        return self._get_duration_ffprobe(filepath)

    def _get_wav_duration_ms(self, filepath: Path) -> int:
        """Get WAV file duration using wave module."""
        try:
            with wave.open(str(filepath), 'rb') as wav:
                frames = wav.getnframes()
                rate = wav.getframerate()
                return int((frames / rate) * 1000)
        except Exception:
            return 0

    def _get_mp3_duration_mutagen(self, filepath: Path) -> int:
        """Get MP3 duration using mutagen library."""
        try:
            audio = MP3(str(filepath))
            return int(audio.info.length * 1000)
        except Exception:
            return 0

    def _estimate_mp3_duration(self, filepath: Path) -> int:
        """Estimate MP3 duration from file size (rough approximation).
        
        Assumes ~128kbps average bitrate as fallback.
        """
        try:
            file_size = filepath.stat().st_size
            # 128 kbps = 16000 bytes per second
            # This is a rough estimate, actual bitrate varies
            duration_sec = file_size / 16000
            return int(duration_sec * 1000)
        except Exception:
            return 0

    def _get_duration_ffprobe(self, filepath: Path) -> int:
        """Get duration using ffprobe."""
        try:
            result = subprocess.run(
                [
                    'ffprobe', '-v', 'quiet', '-show_entries',
                    'format=duration', '-of', 'csv=p=0', str(filepath)
                ],
                capture_output=True,
                text=True
            )
            duration_sec = float(result.stdout.strip())
            return int(duration_sec * 1000)
        except Exception:
            return 0

    def save_audio(self, file_data: bytes, filename: str) -> Path:
        """Save uploaded audio file.
        
        Args:
            file_data: Raw audio file bytes
            filename: Original filename
            
        Returns:
            Path to saved file
        """
        # Sanitize filename and ensure unique name
        safe_name = "".join(c for c in filename if c.isalnum() or c in "._-")
        filepath = self.audio_dir / safe_name
        
        # Handle duplicates
        counter = 1
        base = filepath.stem
        suffix = filepath.suffix
        while filepath.exists():
            filepath = self.audio_dir / f"{base}_{counter}{suffix}"
            counter += 1
        
        filepath.write_bytes(file_data)
        return filepath

    def set_current_audio(self, filepath: Optional[Path]) -> None:
        """Set the current audio file for playback.
        
        Args:
            filepath: Path to audio file, or None to clear
        """
        self._local_current_file = filepath
        
        # Persist to config
        if self._config_store:
            self._config_store.current_audio_file = filepath.name if filepath else ""
            try:
                self._config_store.save_config()
            except Exception:
                pass

    def get_waveform_data(self, filepath: Path, num_samples: int = 200) -> list:
        """Get normalized waveform data for visualization.
        
        Args:
            filepath: Path to audio file
            num_samples: Number of samples to return
            
        Returns:
            List of normalized amplitude values (0 to 1)
        """
        suffix = filepath.suffix.lower()
        
        try:
            if suffix == '.wav':
                waveform = self._get_wav_waveform(filepath, num_samples)
                if waveform:
                    return waveform
            elif HAS_PYDUB:
                # Use pydub for non-WAV formats
                try:
                    audio = AudioSegment.from_file(filepath)
                    samples = audio.get_array_of_samples()
                    waveform = self._normalize_samples(list(samples), num_samples, audio.max_possible_amplitude)
                    if waveform:
                        return waveform
                except Exception as e:
                    print(f"Pydub waveform extraction failed: {e}")
        except Exception as e:
            print(f"Error getting waveform: {e}")
        
        # Fallback: generate a simple placeholder waveform
        # This shows that audio exists even if we can't analyze it
        return self._generate_placeholder_waveform(num_samples)

    def _generate_placeholder_waveform(self, num_samples: int) -> list:
        """Generate a simple placeholder waveform pattern.
        
        Creates a subtle visual indication that audio exists.
        """
        import math
        waveform = []
        for i in range(num_samples):
            # Create a gentle wave pattern with some variation
            t = i / num_samples
            # Multiple sine waves for a more natural look
            val = 0.3 + 0.2 * math.sin(t * math.pi * 8)
            val += 0.1 * math.sin(t * math.pi * 23)
            val += 0.05 * math.sin(t * math.pi * 47)
            waveform.append(max(0.1, min(0.7, val)))
        return waveform

    def _get_wav_waveform(self, filepath: Path, num_samples: int) -> list:
        """Extract waveform from WAV file."""
        try:
            with wave.open(str(filepath), 'rb') as wav:
                n_channels = wav.getnchannels()
                sample_width = wav.getsampwidth()
                n_frames = wav.getnframes()
                
                # Read all frames
                raw_data = wav.readframes(n_frames)
                
                # Parse samples based on sample width
                if sample_width == 1:
                    fmt = f'{n_frames * n_channels}B'
                    max_val = 255
                elif sample_width == 2:
                    fmt = f'{n_frames * n_channels}h'
                    max_val = 32767
                else:
                    fmt = f'{n_frames * n_channels}i'
                    max_val = 2147483647
                
                samples = list(struct.unpack(fmt, raw_data))
                
                # Mix to mono if stereo
                if n_channels == 2:
                    samples = [(samples[i] + samples[i + 1]) / 2 for i in range(0, len(samples), 2)]
                
                return self._normalize_samples(samples, num_samples, max_val)
        except Exception as e:
            print(f"Error reading WAV: {e}")
            return []

    def _normalize_samples(self, samples: list, num_samples: int, max_val: int) -> list:
        """Normalize and downsample audio samples for visualization."""
        if not samples:
            return []
        
        chunk_size = max(1, len(samples) // num_samples)
        result = []
        
        for i in range(0, len(samples), chunk_size):
            chunk = samples[i:i + chunk_size]
            if chunk:
                # Get peak amplitude in chunk
                peak = max(abs(min(chunk)), abs(max(chunk)))
                result.append(peak / max_val if max_val > 0 else 0)
        
        return result[:num_samples]

    def play(self, wait_for_start: bool = False) -> bool:
        """Start playing the current audio file.
        
        Args:
            wait_for_start: If True, block until audio actually starts playing
        
        Returns:
            True if playback started, False otherwise
        """
        if not self.current_audio_file or not self.current_audio_file.exists():
            return False
        
        with self._lock:
            if self._is_playing:
                return False
            
            self._is_playing = True
            self._play_started_event.clear()
        
        def _play_audio():
            try:
                # Use aplay for WAV, or convert/use mpg123 for MP3
                suffix = self.current_audio_file.suffix.lower()
                
                if suffix == '.wav':
                    # Use lower buffer for less latency
                    cmd = ['aplay', '--buffer-size=2048', str(self.current_audio_file)]
                elif suffix == '.mp3':
                    # mpg123 with lower buffer for less latency
                    cmd = ['mpg123', '-q', '--buffer', '1024', str(self.current_audio_file)]
                else:
                    # Use ffplay as fallback
                    cmd = ['ffplay', '-nodisp', '-autoexit', '-loglevel', 'quiet', str(self.current_audio_file)]
                
                self._current_process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                
                # Signal that the process has started
                self._play_started_event.set()
                
                self._current_process.wait()
            except Exception as e:
                print(f"Audio playback error: {e}")
                self._play_started_event.set()  # Unblock waiter on error
            finally:
                with self._lock:
                    self._is_playing = False
                    self._current_process = None
        
        thread = threading.Thread(target=_play_audio, daemon=True)
        thread.start()
        
        if wait_for_start:
            # Wait for the audio process to start (with timeout)
            self._play_started_event.wait(timeout=1.0)
        
        return True

    @property
    def audio_offset_ms(self) -> int:
        """Get the audio latency offset in milliseconds."""
        if self._config_store:
            return self._config_store.audio_offset_ms
        return self._local_offset_ms
    
    @audio_offset_ms.setter
    def audio_offset_ms(self, value: int) -> None:
        """Set the audio latency offset in milliseconds."""
        value = max(-500, min(1000, value))  # Clamp to valid range
        if self._config_store:
            self._config_store.audio_offset_ms = value
        else:
            self._local_offset_ms = value

    def get_latency_offset_sec(self) -> float:
        """Get the audio latency offset in seconds."""
        return self.audio_offset_ms / 1000.0

    def stop(self) -> None:
        """Stop current audio playback."""
        with self._lock:
            if self._current_process:
                self._current_process.terminate()
                try:
                    self._current_process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    self._current_process.kill()
                self._current_process = None
            self._is_playing = False

    def clear_audio(self) -> None:
        """Clear the current audio file."""
        self.stop()
        self.set_current_audio(None)

    def list_audio_files(self) -> list:
        """List all stored audio files.
        
        Returns:
            List of audio file info dicts
        """
        files = []
        for f in self.audio_dir.iterdir():
            if f.suffix.lower() in ('.wav', '.mp3', '.ogg', '.flac'):
                files.append({
                    'name': f.name,
                    'path': str(f),
                    'duration_ms': self.get_audio_duration_ms(f)
                })
        return files

