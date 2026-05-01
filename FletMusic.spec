# -*- mode: python ; coding: utf-8 -*-
import os
import site

# 查找 flet 库的安装路径
flet_path = None
for p in site.getsitepackages():
    test_path = os.path.join(p, 'flet')
    if os.path.exists(test_path):
        flet_path = p
        break

# 只收集 flet 的资源文件（不需要打包图标，只需要嵌入 exe）
datas = []
if flet_path:
    datas.append((os.path.join(flet_path, 'flet'), 'flet'))

a = Analysis(
    ['fletmusic.py'],
    pathex=[os.path.abspath('.')],
    binaries=[],
    datas=datas,
    hiddenimports=['flet'],  # 只保留必要的
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='FletMusic',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['Music_31107.ico'],
)
