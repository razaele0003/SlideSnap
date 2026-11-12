from PyInstaller.utils.hooks import collect_all

av_data, av_binaries, av_imports = collect_all('av')
a = Analysis(
    ['main.py'], pathex=['.'], binaries=av_binaries,
    datas=av_data + [('slidesnap/assets', 'slidesnap/assets')],
    hiddenimports=av_imports, hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'PySide6.QtWebEngineQuick',
              'matplotlib', 'IPython', 'pytest', 'pymupdf', 'fitz', 'tkinter'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='SlideSnap', debug=False,
          bootloader_ignore_signals=False, strip=False, upx=False, console=False,
          icon='slidesnap/assets/slidesnap.ico')
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='SlideSnap')
