"""Run from the repository root: python -m PyInstaller packaging/voxbridge.spec"""

from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules

root = Path(SPECPATH).parent
sound_data, sound_binaries, sound_imports = collect_all("soundcard")
speech_data, speech_binaries, speech_imports = collect_all("faster_whisper")
a = Analysis(
    [str(root / "app" / "__main__.py")],
    pathex=[str(root)],
    hiddenimports=collect_submodules("app") + sound_imports + speech_imports,
    datas=[(str(root / "app" / "ui" / "theme.qss"), "app/ui")]
    + sound_data
    + speech_data,
    binaries=sound_binaries + speech_binaries,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="VoxBridge", console=False)
coll = COLLECT(exe, a.binaries, a.datas, name="VoxBridge")
