"""
app/core/operation.py
======================
Kullanicinin her yeni islem (kayit) denemesini temsil eden yapi.
Asenkron callback'lerde Stale-Callback durumlarini tespit etmeyi saglar.
"""

from dataclasses import dataclass
from typing import Optional
from pathlib import Path
import time

@dataclass
class OperationContext:
    operation_id: int
    started_at: float = 0.0
    target_hwnd: int = 0
    recording_path: Optional[Path] = None
    
    def __post_init__(self):
        if not self.started_at:
            self.started_at = time.time()
