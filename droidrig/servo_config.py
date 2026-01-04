"""Per-servo configuration with persistent storage."""

import json
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict, field

from .config import MIN_PULSE, MAX_PULSE, CENTER_PULSE


# Default colors for servos (vibrant palette)
DEFAULT_COLORS = [
    "#3b9eff", "#ff9f43", "#26de81", "#a55eea",
    "#fed330", "#fd79a8", "#0abde3", "#ff6b6b",
    "#2ed573", "#70a1ff", "#ffa502", "#ff4757",
    "#1dd1a1", "#5f27cd", "#ff9ff3", "#54a0ff",
]


@dataclass
class ServoSettings:
    """Configuration for a single servo."""
    name: str = ""
    min_pulse: int = MIN_PULSE
    max_pulse: int = MAX_PULSE
    center_pulse: int = CENTER_PULSE
    color: str = ""  # Empty means use default color based on index
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ServoSettings":
        return cls(
            name=data.get("name", ""),
            min_pulse=data.get("min_pulse", MIN_PULSE),
            max_pulse=data.get("max_pulse", MAX_PULSE),
            center_pulse=data.get("center_pulse", CENTER_PULSE),
            color=data.get("color", ""),
        )
    
    @staticmethod
    def get_default_color(index: int) -> str:
        """Get the default color for a servo index."""
        return DEFAULT_COLORS[index % len(DEFAULT_COLORS)]


@dataclass 
class ServoConfigStore:
    """Manages persistent servo configuration."""
    
    num_servos: int = 2
    servos: Dict[int, ServoSettings] = field(default_factory=dict)
    audio_offset_ms: int = 150  # Audio sync offset in milliseconds
    current_audio_file: str = ""  # Filename of currently selected audio
    _config_path: Optional[Path] = field(default=None, repr=False)
    
    def __post_init__(self):
        # Ensure all servos have settings
        for i in range(self.num_servos):
            if i not in self.servos:
                self.servos[i] = ServoSettings(name=f"Servo {i}")
    
    def get_servo(self, channel: int) -> ServoSettings:
        """Get settings for a servo, creating defaults if needed."""
        if channel not in self.servos:
            self.servos[channel] = ServoSettings(name=f"Servo {channel}")
        return self.servos[channel]
    
    def set_servo(self, channel: int, settings: ServoSettings) -> None:
        """Update settings for a servo."""
        self.servos[channel] = settings
    
    def set_num_servos(self, count: int) -> None:
        """Change the number of servos."""
        count = max(1, min(16, count))
        self.num_servos = count
        
        # Add missing servos
        for i in range(count):
            if i not in self.servos:
                self.servos[i] = ServoSettings(name=f"Servo {i}")
        
        # Remove extra servos
        for i in list(self.servos.keys()):
            if i >= count:
                del self.servos[i]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "num_servos": self.num_servos,
            "servos": {str(k): v.to_dict() for k, v in self.servos.items()},
            "audio_offset_ms": self.audio_offset_ms,
            "current_audio_file": self.current_audio_file,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ServoConfigStore":
        """Create from dictionary."""
        num_servos = data.get("num_servos", 2)
        servos_data = data.get("servos", {})
        servos = {
            int(k): ServoSettings.from_dict(v) 
            for k, v in servos_data.items()
        }
        audio_offset_ms = data.get("audio_offset_ms", 150)
        current_audio_file = data.get("current_audio_file", "")
        return cls(
            num_servos=num_servos,
            servos=servos,
            audio_offset_ms=audio_offset_ms,
            current_audio_file=current_audio_file,
        )
    
    def save(self, path: Optional[Path] = None) -> None:
        """Save configuration to JSON file."""
        path = path or self._config_path
        if path is None:
            raise ValueError("No config path specified")
        
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
        self._config_path = path
    
    @classmethod
    def load(cls, path: Path) -> "ServoConfigStore":
        """Load configuration from JSON file."""
        if not path.exists():
            config = cls()
            config._config_path = path
            return config
        
        with open(path) as f:
            data = json.load(f)
        
        config = cls.from_dict(data)
        config._config_path = path
        return config

