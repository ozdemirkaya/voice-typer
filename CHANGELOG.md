# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
### Planned
- GUI Settings panel for modifying hotkeys and model configurations.
- Automated CI test pipeline.

## [0.1.0-rc1] - 2026-10-02
### Added
- Native Win32 global hotkey integration (`Alt+X` default).
- Local speech-to-text pipeline utilizing `faster-whisper` and `CTranslate2`.
- Automatic NVIDIA CUDA detection with zero-configuration fallback to CPU (`int8`).
- Bundled CUDA/cuDNN DLL integration without system `PATH` pollution.
- Active window (`HWND`) tracking to safely inject text via Win32 `SendInput`.
- Safe clipboard preservation and restoration during injection.
- Single-instance application lock via named Windows mutex.
- Privacy-first configuration (`keep_recordings = False` by default).
- PyInstaller `onedir` build specification and Inno Setup per-user installer configuration.
