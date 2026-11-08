# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_submodules


hiddenimports = collect_submodules("reportlab")

datas = [
    ("styles/light_theme.qss", "styles"),
    ("assets/app_icon.svg", "assets"),
    ("assets/app_icon.ico", "assets"),
    ("assets/DejaVuSans.ttf", "assets"),
    ("assets/passport_template/back_page_baran.pdf", "assets/passport_template"),
    ("assets/passport_template/back_page_matka.pdf", "assets/passport_template"),
    ("assets/passport_template/face_page1_no_tables.pdf", "assets/passport_template"),
    ("assets/passport_template/face_page1_no_tables_baran.pdf", "assets/passport_template"),
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
    icon="assets/app_icon.ico",
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
