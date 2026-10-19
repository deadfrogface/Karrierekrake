$ErrorActionPreference='Continue'
$R='%USERPROFILE%\kk_extracts_2026-10-18'
Expand-Archive -Force "$R\_harness\kk144_src_47e8f83b.zip" "$R\src_47e8f83b"
"src files: $((Get-ChildItem -Recurse -File "$R\src_47e8f83b").Count)"
robocopy %USERPROFILE%\kk-speedtest\.venv "$R\venv_llama0335" /E /NFL /NDL /NJH /NP /R:1 /W:1 | Select -Last 4
$PY="$R\venv_llama0335\Scripts\python.exe"
& $PY -m pip install --no-deps --force-reinstall "https://github.com/abetlen/llama-cpp-python/releases/download/v0.3.35/llama_cpp_python-0.3.35-py3-none-win_amd64.whl" 2>&1 | Select -Last 3
& $PY -m pip show llama-cpp-python 2>&1
& $PY -c "import llama_cpp,sys;print('import ok',llama_cpp.__version__,llama_cpp.__file__);print(sys.prefix)"
(Get-FileHash "$R\venv_llama0335\Lib\site-packages\llama_cpp\lib\llama.dll" -Algorithm SHA256).Hash
& $PY -m pip freeze 2>$null | Out-File -Encoding utf8 "$R\pip_freeze_venv_llama0335.txt"
& %USERPROFILE%\kk-speedtest\.venv\Scripts\python.exe -m pip show llama-cpp-python 2>&1 | Select -First 3
Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue | Select LocalPort,OwningProcess
"setup done"
