import ctypes
import json
from ctypes import wintypes
from pathlib import Path
from tempfile import NamedTemporaryFile
from platform_support import WINDOWS


class Blob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def protect(data, *, decrypt=False):
    source = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    value = Blob(len(source), source)
    result = Blob()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    function = crypt32.CryptUnprotectData if decrypt else crypt32.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    if not function(ctypes.byref(value), None, None, None, None, 1, ctypes.byref(result)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(result.data, result.size)
    finally:
        kernel32.LocalFree(result.data)


class AccountStore:
    def __init__(self, path):
        self.path = Path(path)
        self.keyring_saved = False

    def load(self):
        if not WINDOWS:
            try:
                saved = self.secret_service().get_password("Bilibili Network", str(self.path))
                self.keyring_saved = bool(saved)
                return json.loads(saved) if saved else []
            except Exception:
                return []
        if not self.path.is_file():
            return []
        return json.loads(protect(self.path.read_bytes(), decrypt=True))

    def save(self, records):
        if not WINDOWS:
            try:
                self.secret_service().set_password("Bilibili Network", str(self.path), json.dumps(records))
                self.keyring_saved = True
            except Exception as exc:
                raise OSError("System keyring unavailable") from exc
            return
        encrypted = protect(json.dumps(records).encode("utf-8"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(prefix=".account-", dir=self.path.parent, delete=False) as output:
            pending = Path(output.name)
            try:
                output.write(encrypted)
            except OSError:
                output.close()
                pending.unlink(missing_ok=True)
                raise
        try:
            pending.replace(self.path)
        finally:
            pending.unlink(missing_ok=True)

    def clear(self):
        if not WINDOWS:
            try:
                service = self.secret_service()
                if service.get_password("Bilibili Network", str(self.path)):
                    service.delete_password("Bilibili Network", str(self.path))
                self.keyring_saved = False
            except Exception:
                if not self.keyring_saved:
                    return
                raise OSError("System keyring unavailable")
            return
        self.path.unlink(missing_ok=True)

    @staticmethod
    def secret_service():
        from keyring.backends.SecretService import Keyring

        return Keyring()
