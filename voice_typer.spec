# -*- mode: python ; coding: utf-8 -*-
import sys
import os
from pathlib import Path

block_cipher = None

# Proje dizinleri
project_root = Path(os.getcwd())
venv_dir = project_root / ".venv"
site_packages = venv_dir / "Lib" / "site-packages"

# CUDA DLLs'i bul
nvidia_dir = site_packages / "nvidia"
cuda_dlls = []

# Sadece zorunlu gordugumuz DLL'leri seciyoruz
required_dlls = [
    "cublas64_12.dll",
    "cublasLt64_12.dll",
    "cudnn64_9.dll",
    "cudnn_ops64_9.dll",
    "cudnn_cnn64_9.dll",
    "cudnn_adv64_9.dll",
    "cudnn_engines_runtime_compiled64_9.dll",
    # Additionally CTranslate2 needs zlibwapi.dll or some C++ redist sometimes, but we'll see
]

if nvidia_dir.exists():
    for dll_name in required_dlls:
        # Alt klasorlerde (cublas/bin, cudnn/bin vs) ara
        found = False
        for root, dirs, files in os.walk(nvidia_dir):
            if dll_name in files:
                full_path = os.path.join(root, dll_name)
                # target path as 'cuda_runtime'
                cuda_dlls.append((full_path, "cuda_runtime"))
                found = True
                break
        if not found:
            print(f"UYARI: {dll_name} bulunamadi!")

from PyInstaller.utils.hooks import collect_data_files
faster_whisper_datas = collect_data_files('faster_whisper')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=cuda_dlls,
    datas=[
        ('app/assets', 'app/assets'),
    ] + faster_whisper_datas,
    hiddenimports=[
        'faster_whisper',
        'ctranslate2',
        'sounddevice',
        'soundfile',
        'numpy',
        'PySide6',
        'app.core.transcription.faster_whisper_provider', # Dynamically loaded
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['av'], # Python 3.14 av hatasini onlemek icin mockladigimiz modulu dahil etmiyoruz
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='VoiceTyper',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True, # Compress if possible
    console=False, # Production build
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='app/assets/icon.ico' if os.path.exists('app/assets/icon.ico') else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='VoiceTyper',
)
