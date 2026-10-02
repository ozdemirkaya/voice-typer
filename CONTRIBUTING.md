# Contributing to Voice Typer

Thank you for your interest in contributing to Voice Typer!

## Getting Started

1. **Fork** the repository on GitHub.
2. **Clone** your fork locally.
3. **Branch** out from `master` (e.g., `git checkout -b feature/my-feature`).
4. **Setup** the development environment:
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\activate
   pip install -r requirements.txt
   ```
5. **Make your changes**. Please ensure your code adheres to the existing style and architecture.
6. **Test** your changes. Run relevant scripts in the `tests/` directory to ensure no regressions were introduced (e.g. `python tests/test_regression.py`).
7. **Commit & Push** to your fork.
8. **Submit a Pull Request** detailing your changes.

## General Guidelines
- Keep pull requests focused on a single feature or bug fix.
- Ensure no personal or sensitive data is committed.
- Voice Typer is a privacy-first, offline-only application. Features that require cloud processing or external analytics will not be accepted.
