# Standalone backend entry point for Linux/Proton.
#
# The Hongguo Windows app is a Tauri shell (crashing Edge/WebView2 under Wine)
# wrapped around a local FastAPI backend that does all the real work: it forges
# the ByteDance/FQNovel API signatures (via a Java signer), fetches the catalog,
# and serves *decrypted, seekable MP4* at /stream. That backend runs fine under
# Wine. This entry point runs it directly -- no companion, no stdin handshake,
# no in-Wine Java signer -- on a fixed PORT so a native Linux browser can be the
# UI instead of the broken WebView2. It mirrors the env setup that the app's own
# desktop_bootstrap.py performs before importing the server.
#
# Provided by launch-hongguo via the environment:
#   PORT, SIGN_SERVER (host-JVM signer), HONGGUO_SESSION_API_KEY,
#   HONGGUO_BACKEND_DATA_DIR, HONGGUO_CONTENT_CONFIG, HONGGUO_HLS_WORK_DIR
import os, sys, secrets, traceback
from pathlib import Path

_LOG = os.environ.get("HONGGUO_STANDALONE_LOG", r"C:\hg-standalone.log")
def _log(msg):
    try:
        with open(_LOG, "a", encoding="utf-8") as f:
            f.write(str(msg) + "\n")
    except Exception:
        pass

try:
    open(_LOG, "w").close()
except Exception:
    pass
_log("entry")

root = Path(__file__).resolve().parent
sys.path.insert(0, str(root))

# Mirror desktop_bootstrap's packaged-mode environment.
os.environ.setdefault("ADMIN_TOKEN", secrets.token_hex(32))
os.environ["BIND_HOST"] = "127.0.0.1"
_data = os.environ.get("HONGGUO_BACKEND_DATA_DIR")
if _data:
    os.environ.setdefault("HONGGUO_STREAM_CACHE", str(Path(_data) / "stream-cache"))
os.environ["IMPERSONATE"] = ""
os.environ["DEVICE_POOL_SIZE"] = "0"          # Desktop never rotates device identities.
# Unsigned catalog requests now return empty successful responses upstream.
os.environ.setdefault("HG_SIGN_LIST", "1")
os.environ.pop("API_KEYS", None)
for _n in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy",
           "all_proxy", "HONGGUO_PROXY"):
    os.environ.pop(_n, None)

# --- Persistent caches (survive restarts) --------------------------------------
# Stock Hongguo keeps everything in process memory: the catalog cache lives in
# safeguards._cache and cover thumbnails in server._img_cache. launch-hongguo
# starts a fresh backend each time, so without persistence every app open re-hits
# the throttled FQNovel API for each page and re-fetches+re-decodes every HEIC
# cover -- the "few seconds after I click a page" lag. We back both with disk
# stores under HONGGUO_BACKEND_DATA_DIR so re-opens are warm. All best-effort:
# any failure falls back to the stock in-memory behaviour.
_CACHE_ROOT = Path(_data) / "cache" if _data else root / "cache"


class _DiskTTLCache:
    """Disk-backed TTL cache (SQLite) with a hot in-memory layer, shaped to
    drop in for safeguards.cache_get/cache_set. TTLs are supplied by callers
    (rank 30m, episodes 6h, stream URLs 5h, ...) and honoured on read."""

    def __init__(self, path):
        import sqlite3, threading
        self._lock = threading.Lock()
        self._mem = {}
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.execute("CREATE TABLE IF NOT EXISTS cache (k TEXT PRIMARY KEY, exp REAL, v BLOB)")
        self._db.commit()

    def get(self, key):
        import time, pickle
        now = time.time()
        with self._lock:
            e = self._mem.get(key)
            if e is not None:
                if e[0] > now:
                    return e[1]
                self._mem.pop(key, None)
            try:
                row = self._db.execute("SELECT exp, v FROM cache WHERE k=?", (key,)).fetchone()
            except Exception:
                return None
            if row and row[0] > now:
                try:
                    val = pickle.loads(row[1])
                except Exception:
                    return None
                self._mem[key] = (row[0], val)
                return val
            if row:
                try:
                    self._db.execute("DELETE FROM cache WHERE k=?", (key,))
                    self._db.commit()
                except Exception:
                    pass
        return None

    def set(self, key, val, ttl):
        import time, pickle
        exp = time.time() + ttl
        with self._lock:
            self._mem[key] = (exp, val)
            try:
                self._db.execute("INSERT OR REPLACE INTO cache VALUES (?,?,?)",
                                 (key, exp, pickle.dumps(val)))
                self._db.commit()
            except Exception:
                pass


class _DiskImgCache:
    """Disk-backed cover cache shaped like the dict server._img_cache uses
    (.get / in / [] / len / assignment). Stores the already-decoded JPEG bytes
    as files so covers never re-download or re-HEIC-decode across restarts."""

    def __init__(self, directory):
        import hashlib
        self._hashlib = hashlib
        self._dir = directory
        os.makedirs(directory, exist_ok=True)
        self._mem = {}

    def _path(self, key):
        h = self._hashlib.md5(key.encode("utf-8")).hexdigest()
        return os.path.join(self._dir, h + ".jpg")

    def get(self, key, default=None):
        v = self._mem.get(key)
        if v is not None:
            return v
        p = self._path(key)
        try:
            with open(p, "rb") as f:
                data = f.read()
        except Exception:
            return default
        self._mem[key] = data
        return data

    def __contains__(self, key):
        return self.get(key) is not None

    def __getitem__(self, key):
        v = self.get(key)
        if v is None:
            raise KeyError(key)
        return v

    def __setitem__(self, key, val):
        self._mem[key] = val
        try:
            with open(self._path(key), "wb") as f:
                f.write(val)
        except Exception:
            pass

    def __len__(self):
        return len(self._mem)


def _install_persistent_caches():
    try:
        _CACHE_ROOT.mkdir(parents=True, exist_ok=True)
        import safeguards
        _catalog = _DiskTTLCache(_CACHE_ROOT / "catalog.sqlite")
        safeguards.cache_get = _catalog.get
        safeguards.cache_set = lambda key, val, ttl: _catalog.set(key, val, ttl)
        _log("persistent catalog cache installed at %s" % (_CACHE_ROOT / "catalog.sqlite"))
        return True
    except Exception:
        _log("catalog cache patch failed (using in-memory):\n" + traceback.format_exc())
        return False


try:
    _log("env-set; patching caches")
    _install_persistent_caches()
    _log("importing server")
    import server     # noqa: E402  (import only after env is prepared)
    try:
        server._img_cache = _DiskImgCache(str(_CACHE_ROOT / "img"))
        _log("persistent image cache installed at %s" % (_CACHE_ROOT / "img"))
    except Exception:
        _log("image cache swap failed (using in-memory):\n" + traceback.format_exc())
    import uvicorn     # noqa: E402
    _log("server imported; starting uvicorn")
    port = int(os.environ.get("PORT", "8793"))
    cfg = uvicorn.Config(server.app, host="127.0.0.1", port=port, log_config=None,
                         access_log=False, log_level="warning")
    uvicorn.Server(cfg).run()
    _log("uvicorn returned")
except BaseException:
    _log("EXCEPTION:\n" + traceback.format_exc())
    raise
