# Voice Typer - Security Audit & Release Report

**Date:** 2026-10-02
**Target:** Voice Typer (Windows Desktop)

## A. Executive Summary
A comprehensive security and privacy audit was conducted on the Voice Typer codebase, its PyInstaller bundle, and the Inno Setup installer. The overall architecture is highly robust. Key security strengths include:
- Pure local execution (offline STT). No telemetry or network calls besides the initial model download from HuggingFace.
- Safe Registry access (`HKCU` without admin privileges). Unquoted executable path vulnerabilities are prevented.
- The PyInstaller bundle strictly loads CUDA DLLs from its own `_internal` directory, preventing untrusted DLL hijacking from the working directory.
- `installer.iss` correctly cleans up the registry and runs with lowest privileges (`PrivilegesRequired=lowest`).
- Text Injection (`SendInput`) verifies the active foreground `HWND`, preventing accidental pasting into unintended applications.

## B. Critical Findings
**None**

## C. High Findings
**None**

## D. Medium Findings
**None**

## E. Low / Hardening Findings
1. **Config Model Size Validation:** The `model_size` field is string-typed but not constrained to a strict Enum list in `ConfigManager`. An attacker who modifies `config.json` could cause arbitrary file loading or directory traversal. *(Risk is low because in a local desktop threat model, an attacker able to modify `%LOCALAPPDATA%\VoiceTyper\config.json` already has user-level access).*
2. **Dependency Vulnerability (pip):** Scanned using `pip-audit`. `pip` version 25.3 has known vulnerabilities (e.g., `PYSEC-2026-1796`), but `pip` is only present in the development `.venv` and is **not** bundled into the production `.exe`. All production runtime libraries (CTranslate2, PySide6, sounddevice) are free of known high-severity CVEs.
3. **Subprocess Call:** `subprocess.Popen(["notepad.exe", ...])` is safe because `log_file` is an internal path, but passing the absolute path for `notepad.exe` (e.g., `C:\Windows\System32\notepad.exe`) would prevent extremely rare PATH hijacking attacks.

## F. Privacy Findings
1. **Data Retention (FIXED):** `AudioConfig` originally defaulted to `keep_recordings=True`, saving every voice recording forever into `%LOCALAPPDATA%\VoiceTyper\cache\audio\saved` without an auto-cleanup mechanism. Over time, this could expose the user's private voice memos to other local apps/users, and indefinitely consume disk space.
2. **Transcript Logging (FIXED):** The first 60 characters of the detected transcript were logged at `DEBUG` level. If a user enabled DEBUG logs to troubleshoot a microphone issue, their private conversations would be written to `voicetyper.log`.

## G. Dependency Findings
A local `pip-audit` scan revealed 10 known vulnerabilities strictly related to `pip` (v25.3). As mentioned in Section E, this does not affect the packaged PyInstaller application. The core runtime dependencies (faster-whisper, numpy, PySide6) are secure and up-to-date. `bandit` static analysis revealed 0 High, 0 Medium, and 9 Low severity issues (all related to intentional `try: ... except Exception: pass` mechanisms for graceful degradation and safe clipboard handling).

## H. Git Exposure Findings
If `git add .` had been run before this audit, the following sensitive and local data would have leaked into the repository:
- `cache/audio/saved/*` (Personal diagnostic voice recordings)
- `models/cache/*` (Large cached model binaries)
- `logs/voicetyper.log` (Runtime logs)
- `.venv/` (Local environment)
- `config.json` (Local settings and configurations)

*(A `.gitignore` file has been provided below to prevent this).*

## I. Fixes Applied
During this audit, the following minimum required fixes were implemented to secure the release candidate:
1. **Privacy Logging Fix:** Removed the transcript content from the DEBUG log in `app_controller.py`. It now strictly logs only the character length of the string.
2. **Data Retention Fix:** Changed the default `keep_recordings` value from `True` to `False` in `config_manager.py` to prevent the permanent accumulation of voice recordings in the `saved` directory.

## J. Remaining Risks
- **Model Supply Chain Risk:** Voice Typer depends on `mobiuslabsgmbh/faster-whisper-large-v3-turbo` from Hugging Face. Downloading models dynamically over the internet means if that specific repository is compromised, malicious model binaries could be downloaded. *(Mitigation: CTranslate2 binary format is largely safe from RCE compared to Python Pickles, and Hugging Face implements its own malware scanning).*

## K. Release Recommendation
**ACCEPTABLE FOR PUBLIC RELEASE**
The application adheres to strong offline and privacy-first principles. The installer is unprivileged, registry operations are secure, and clipboard interactions properly validate window contexts. With the privacy bugs fixed, it is ready for public GitHub release.

---

### Recommended `.gitignore`

```gitignore
# Environments
.venv/
.venv_DISABLED/
env/
venv/
ENV/

# Python
__pycache__/
*.py[cod]
*$py.class
*.so

# Build & Dist
build/
dist/
*.egg-info/
*.spec

# User Data & Cache (Critical for Privacy)
cache/
models/
logs/
config.json
*.wav

# IDEs
.vscode/
.idea/
*.swp

# OS Files
.DS_Store
Thumbs.db
```
