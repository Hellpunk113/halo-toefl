# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('data', 'data'),
        ('resources/audio', 'resources/audio'),
        ('resources/images/people/*.jpg', 'resources/images/people'),
    ],
    hiddenimports=[],
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
    [],
    exclude_binaries=True,
    name='HALO TOEFL',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='HALO TOEFL',
)
app = BUNDLE(
    coll,
    name='HALO TOEFL.app',
    icon='artwork/HALO-TOEFL.icns',
    bundle_identifier='com.haloeducationresearch.toefl',
    info_plist={
        'CFBundleDisplayName': 'HALO TOEFL',
        'CFBundleName': 'HALO TOEFL',
        'CFBundleShortVersionString': '1.0.5',
        'CFBundleVersion': '6',
        'NSHighResolutionCapable': True,
        'NSMicrophoneUsageDescription': 'HALO TOEFL uses the microphone to record speaking practice responses.',
    },
)
