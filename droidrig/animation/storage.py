"""Animation storage for saving and loading animations."""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict, field


@dataclass
class SavedAnimation:
    """A saved animation with metadata."""
    
    name: str
    duration_ms: int
    curves: Dict[int, List[Dict[str, Any]]]  # {servo_id: [{time, pulse}, ...]}
    annotations: List[Dict[str, Any]] = field(default_factory=list)  # [{time, text}, ...]
    audio_file: Optional[str] = None  # Filename of associated audio
    created_at: str = ""
    updated_at: str = ""
    
    def __post_init__(self):
        now = datetime.now().isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SavedAnimation":
        # Convert string keys back to int for curves
        curves = {}
        for k, v in data.get("curves", {}).items():
            curves[int(k)] = v
        
        return cls(
            name=data.get("name", "Untitled"),
            duration_ms=data.get("duration_ms", 3000),
            curves=curves,
            annotations=data.get("annotations", []),
            audio_file=data.get("audio_file"),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )


class AnimationStore:
    """Manages saved animations on disk."""
    
    def __init__(self, storage_dir: Optional[Path] = None):
        """Initialize the animation store.
        
        Args:
            storage_dir: Directory to store animation files
        """
        self.storage_dir = storage_dir or Path(__file__).parent.parent.parent / "animations"
        self.storage_dir.mkdir(exist_ok=True)
    
    def _sanitize_filename(self, name: str) -> str:
        """Convert animation name to safe filename."""
        # Remove/replace unsafe characters
        safe = re.sub(r'[^\w\s-]', '', name.lower())
        safe = re.sub(r'[-\s]+', '-', safe).strip('-')
        return safe or "untitled"
    
    def _get_filepath(self, name: str) -> Path:
        """Get the file path for an animation."""
        return self.storage_dir / f"{self._sanitize_filename(name)}.json"
    
    def save(self, animation: SavedAnimation) -> Path:
        """Save an animation to disk.
        
        Args:
            animation: Animation to save
            
        Returns:
            Path to the saved file
        """
        animation.updated_at = datetime.now().isoformat()
        
        filepath = self._get_filepath(animation.name)
        
        # Convert curves keys to strings for JSON
        data = animation.to_dict()
        data["curves"] = {str(k): v for k, v in animation.curves.items()}
        
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
        
        return filepath
    
    def load(self, name: str) -> Optional[SavedAnimation]:
        """Load an animation by name.
        
        Args:
            name: Animation name
            
        Returns:
            SavedAnimation or None if not found
        """
        filepath = self._get_filepath(name)
        
        if not filepath.exists():
            # Try exact filename match
            for f in self.storage_dir.glob("*.json"):
                if f.stem.lower() == name.lower():
                    filepath = f
                    break
            else:
                return None
        
        try:
            with open(filepath) as f:
                data = json.load(f)
            return SavedAnimation.from_dict(data)
        except (json.JSONDecodeError, IOError):
            return None
    
    def load_by_filename(self, filename: str) -> Optional[SavedAnimation]:
        """Load an animation by its filename.
        
        Args:
            filename: The JSON filename (with or without .json extension)
            
        Returns:
            SavedAnimation or None if not found
        """
        if not filename.endswith('.json'):
            filename = f"{filename}.json"
        
        filepath = self.storage_dir / filename
        
        if not filepath.exists():
            return None
        
        try:
            with open(filepath) as f:
                data = json.load(f)
            return SavedAnimation.from_dict(data)
        except (json.JSONDecodeError, IOError):
            return None
    
    def delete(self, name: str) -> bool:
        """Delete an animation.
        
        Args:
            name: Animation name
            
        Returns:
            True if deleted, False if not found
        """
        filepath = self._get_filepath(name)
        
        if not filepath.exists():
            # Try exact filename match
            for f in self.storage_dir.glob("*.json"):
                if f.stem.lower() == name.lower():
                    filepath = f
                    break
            else:
                return False
        
        filepath.unlink()
        return True
    
    def list_all(self) -> List[Dict[str, Any]]:
        """List all saved animations.
        
        Returns:
            List of animation metadata dicts
        """
        animations = []
        
        for filepath in sorted(self.storage_dir.glob("*.json")):
            try:
                with open(filepath) as f:
                    data = json.load(f)
                
                animations.append({
                    "filename": filepath.stem,
                    "name": data.get("name", filepath.stem),
                    "duration_ms": data.get("duration_ms", 0),
                    "audio_file": data.get("audio_file"),
                    "created_at": data.get("created_at", ""),
                    "updated_at": data.get("updated_at", ""),
                    "num_curves": len(data.get("curves", {})),
                })
            except (json.JSONDecodeError, IOError):
                continue
        
        # Sort by updated_at, newest first
        animations.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        
        return animations
    
    def exists(self, name: str) -> bool:
        """Check if an animation exists.
        
        Args:
            name: Animation name
            
        Returns:
            True if exists
        """
        return self._get_filepath(name).exists()

