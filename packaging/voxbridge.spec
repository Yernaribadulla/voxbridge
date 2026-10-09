from PyInstaller.utils.hooks import collect_submodules
a=Analysis(['../app/__main__.py'], pathex=['..'], hiddenimports=collect_submodules('app'), datas=[])
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,a.binaries,a.datas,[],name='VoxBridge',console=False)
