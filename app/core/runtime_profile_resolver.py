"""
app/core/runtime_profile_resolver.py
====================================
Kullanıcı yapılandırmasından ve sistem donanımından yola çıkarak nihai
Whisper model, device ve compute türünü belirler.
"""
from typing import Tuple
from app.services.config_manager import ConfigManager
import app.services.cuda_runtime as cuda_runtime

class RuntimeProfileResolver:
    @staticmethod
    def resolve_profile(config_manager: ConfigManager) -> Tuple[str, str, str]:
        """
        Nihai (model, device, compute_type) üçlüsünü döndürür.
        
        Kural:
        - model=auto, device=auto:
            CUDA kullanılabiliyorsa -> large-v3-turbo / cuda / float16
            kullanılamıyorsa -> small / cpu / int8
        - model=small, device=auto: -> small / (cuda if possible else cpu) / float16 or int8
        - model=large-v3-turbo, device=cpu: -> large-v3-turbo / cpu / int8 (Kullanıcı kararına uyulur)
        """
        cfg = config_manager.config.stt.faster_whisper
        
        user_model = cfg.model_size
        user_device = cfg.device
        user_compute = cfg.compute_type
        
        # Check if CUDA is actually available via our runtime service
        is_cuda_ready = cuda_runtime.is_cuda_available()
        
        # Resolve Device
        final_device = "cuda" if is_cuda_ready else "cpu"
        if user_device != "auto":
            final_device = user_device # E.g., user explicitly chose "cpu"
            
        # Resolve Model
        if user_model == "auto":
            if final_device == "cuda":
                final_model = "large-v3-turbo"
            else:
                final_model = "small"
        else:
            final_model = user_model
            
        # Resolve Compute Type
        if user_compute == "auto":
            if final_device == "cuda":
                final_compute = "float16"
            else:
                final_compute = "int8"
        else:
            final_compute = user_compute
            
        return final_model, final_device, final_compute

