# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_submodules


hiddenimports = collect_submodules("reportlab")

datas = [
    ("styles/light_theme.qss", "styles"),
    ("assets/app_icon.svg", "assets"),
    ("assets/passport_template/ewe_page1.png", "assets/passport_template"),
    ("assets/passport_template/ewe_page2.png", "assets/passport_template"),
    ("assets/passport_template/ram_page1.png", "assets/passport_template"),
    ("assets/passport_template/ram_page2.png", "assets/passport_template"),
]


a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ArashanBoniter",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon="assets/app_icon.svg",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="ArashanBoniter",
)
