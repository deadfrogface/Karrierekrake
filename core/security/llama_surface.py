"""Verify the desktop-only backend without starting a listener or loading a model."""
from __future__ import annotations


def verify_llama_surface() -> dict[str, bool]:
    from importlib import util
    from pathlib import Path
    import sys
    from llama_cpp import llama_cpp as api

    # The desktop uses the local C API. The upstream RPC server is not part
    # of this product and must not silently appear in a substituted wheel.
    if api.llama_supports_rpc():
        raise RuntimeError('desktop_llama_rpc_backend_present')
    if getattr(sys, 'frozen', False):
        root = Path(sys._MEIPASS)
        if (util.find_spec('llama_cpp.server') is not None
                or (root / 'llama_cpp/server').exists()
                or any((folder / name).exists()
                       for folder in (root, root / 'llama_cpp/lib')
                       for name in ('llama-server', 'llama-server.exe', 'rpc-server', 'rpc-server.exe'))):
            raise RuntimeError('desktop_llama_server_payload_present')
    return {'rpc': False, 'desktop_c_api': True}
