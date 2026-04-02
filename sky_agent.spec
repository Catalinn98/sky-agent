# sky_agent.spec  –  PyInstaller build specification
# Run with:  pyinstaller sky_agent.spec
#
# Produces: dist/SKYAgent/
#   ├── SKYAgent.exe
#   ├── lib/jre/        ← embedded minimal JRE (jlink-built, ~31MB)
#   ├── lib/sapjco3/    ← SAP JCo (sapjco3.jar + sapjco3.dll)
#   └── ...             ← Python runtime + dependencies

import os
from pathlib import Path

block_cipher = None

# Paths to bundled libraries
AGENT_DIR = os.path.dirname(os.path.abspath(SPEC))
LIB_DIR = os.path.join(AGENT_DIR, "lib")

# Collect lib/jre and lib/sapjco3 as data directories
extra_datas = []
jre_dir = os.path.join(LIB_DIR, "jre")
jco_dir = os.path.join(LIB_DIR, "sapjco3")

if os.path.isdir(jre_dir):
    extra_datas.append((jre_dir, "lib/jre"))
if os.path.isdir(jco_dir):
    extra_datas.append((jco_dir, "lib/sapjco3"))

# Object catalog YAML files
catalog_dir = os.path.join(AGENT_DIR, "object_catalog")
if os.path.isdir(catalog_dir):
    extra_datas.append((catalog_dir, "object_catalog"))

a = Analysis(
    ["sky_agent.py"],
    pathex=["."],
    binaries=[],
    datas=extra_datas,
    hiddenimports=[
        "pystray._win32",
        "PIL._tkinter_finder",
        "winreg",
        "jpype",
        "jpype._core",
        "jpype._jvmfinder",
        "services",
        "services.sap_logon_discovery",
        "services.sap_connection",
        "services.db_connection",
        "services.target_db_service",
        "services.project_manager",
        "services.project_scaffold",
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
    [],
    exclude_binaries=True,      # onedir mode
    name="SKYAgent",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    console=False,              # tray app — no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="SKYAgent",
)
