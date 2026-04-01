# sky_agent.spec  –  PyInstaller build specification
# Run with:  pyinstaller sky_agent.spec

block_cipher = None

a = Analysis(
    ["sky_agent.py"],
    pathex=["."],
    binaries=[],
    datas=[],
    hiddenimports=[
        "pystray._win32",
        "PIL._tkinter_finder",
        "winreg",
        "services",
        "services.sap_logon_discovery",
        "models",
        "models.sap_system",
        "models.job",
        "state_manager",
        "job_manager",
        "notifications",
        "tray",
        "dashboard",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="SKYAgent",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,        # no console window — it's a tray app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
