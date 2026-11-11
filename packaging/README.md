# Persistence Coach — Pake Windows desktop packaging

This is an optional packaging path. It does **not** change `index.html`, the Python decision core, or the main website.

## What is packaged

The repository root `index.html` is copied alone into a temporary static folder, then bundled into a Windows x64 MSI through Pake/Tauri. No local web server or Docker runtime is required for this **HTML UI**. The Python `judgment_core.py`, `dialogue_layer.py`, and `data_adapter.py` are **not** embedded as a running backend. Do not claim Python-core E2E validation from the UI build.

The page uses `localStorage`. Browser storage in a Pake app is a separate origin from the GitHub Pages website: existing browser data is **not** migrated automatically. Test persistence after app restart, and back up existing records before uninstalling/resetting. The CSS imports Google Fonts; the app may use fallback fonts offline.

## Build on Windows

Requirements: working Windows MSVC/Rust toolchain, Node and `pake-cli`. If needed:

```powershell
npm install -g pake-cli
git clone https://github.com/spring-kr/Persistence_Coach.git
cd Persistence_Coach
git checkout feat/pake-windows-desktop
.\packaging\build-windows.ps1
```

The build script stages only `index.html`, uses a short Cargo target directory (`C:\pc-pake-target` unless `CARGO_TARGET_DIR` is already defined), and outputs the MSI in `dist-windows`. It prints the resulting MSI path, byte size, and SHA-256. Use the full resulting hash as the evidence baseline. It does **not** upload the installer or sign it.

For a one-off manual build without the script:

```powershell
$env:CARGO_TARGET_DIR = "C:\pc-pake-target"
pake .\index.html --name Persistence-Coach --width 1280 --height 850 --json
```

## Acceptance checklist

1. `pake` exits with code 0 and an MSI is produced.
2. MSI SHA-256 and size are captured; install the MSI on Windows.
3. Launch offline: home screen renders and its core tabs work. Fonts may fall back.
4. Enter **synthetic** records only; close/reopen the app and verify persistence and UI state.
5. Check record isolation against browser GitHub Pages storage, and verify that uninstall/reinstall does not silently erase data (do not assume preservation).
6. Separate any Python-core integration, data migration, signing, SmartScreen, independent clean-PC installs, and full regression into further tests.

**Status:** packaging script prepared; actual Windows MSI build, installation and interaction tests require execution on a Windows machine and are **not yet verified**.
