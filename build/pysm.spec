# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

project_root = Path.cwd()
src_root = project_root / "src"
web_root = src_root / "pysm" / "web"

datas = [
    (str(web_root / "templates"), "pysm/web/templates"),
    (str(web_root / "static"), "pysm/web/static"),
]

block_cipher = None

a = Analysis(
    [str(src_root / "pysm" / "__main__.py")],
    pathex=[str(src_root)],
    binaries=[],
    datas=datas,
    hiddenimports=["uvicorn.logging", "uvicorn.loops.auto", "uvicorn.protocols.websockets.auto"],
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
    name="pysm",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="pysm",
)

