"""Send an exported model (M2 / WMO + sibling files) into a WoW 1.12 client's MPQ archives so it can be seen in game.

Writing goes through ctypes over a StormLib DLL (the bundled `storm` extension is read-only except for compaction).
Safety rules (all mandatory, see deploy()):
  * archives >= MAX_ARCHIVE_BYTES (1.9 GiB) are refused - StormLib compaction corrupts archives over 2 GB;
  * archives that cannot be opened for writing (client running / file locked) are refused with a clear message;
  * archive paths containing a protected fragment (default 'benilla_deploy', the LIVE launcher client) are refused;
  * before the FIRST write to an archive in this session it is copied to a backup folder OUTSIDE the client;
  * the (listfile) entry is added/refreshed, and the archive is COMPACTED after writing (repeated deploys do not grow it);
  * everything written is read back and compared byte for byte.

No bpy at import time; the Blender operator/panel live in ui/deploy_panel.py.
"""

import os
import re
import sys
import shutil
import ctypes
import datetime
from ctypes import wintypes as wt

MAX_ARCHIVE_BYTES = int(1.9 * 1024 ** 3)       # monkeypatched by tests
DEFAULT_PROTECTED = ('benilla_deploy',)

# StormLib constants
MPQ_FILE_COMPRESS = 0x00000200
MPQ_FILE_REPLACEEXISTING = 0x80000000
MPQ_COMPRESSION_ZLIB = 0x02
STREAM_FLAG_READ_ONLY = 0x00000100
ERROR_SHARING_VIOLATION = 32
ERROR_LOCK_VIOLATION = 33
ERROR_ACCESS_DENIED = 5
ERROR_DISK_FULL = 112

LISTFILE = b'(listfile)'

_BACKED_UP = {}            # normalized archive path -> backup file path (per Blender session)


class DeployError(RuntimeError):
    pass


# ------------------------------------------------------------------------------------------------ StormLib DLL

_DLL = None


def addon_dir():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def find_dll():
    for p in (os.path.join(addon_dir(), 'third_party', 'stormlib', 'StormLib.dll'),
              os.environ.get('WBS_STORMLIB', '')):
        if p and os.path.isfile(p):
            return p
    raise DeployError("StormLib.dll not found (expected third_party/stormlib/StormLib.dll inside the add-on).")


def storm():
    global _DLL
    if _DLL is not None:
        return _DLL
    if sys.platform != 'win32':
        raise DeployError("Send to test client needs Windows (StormLib.dll).")
    d = ctypes.WinDLL(find_dll(), use_last_error=True)
    vp, dw, bl = ctypes.c_void_p, wt.DWORD, wt.BOOL
    d.SFileOpenArchive.argtypes = [ctypes.c_wchar_p, dw, dw, ctypes.POINTER(vp)]
    d.SFileOpenArchive.restype = bl
    d.SFileCloseArchive.argtypes = [vp]
    d.SFileCloseArchive.restype = bl
    d.SFileFlushArchive.argtypes = [vp]
    d.SFileFlushArchive.restype = bl
    d.SFileHasFile.argtypes = [vp, ctypes.c_char_p]
    d.SFileHasFile.restype = bl
    d.SFileAddFileEx.argtypes = [vp, ctypes.c_wchar_p, ctypes.c_char_p, dw, dw, dw]
    d.SFileAddFileEx.restype = bl
    d.SFileRemoveFile.argtypes = [vp, ctypes.c_char_p, dw]
    d.SFileRemoveFile.restype = bl
    d.SFileCompactArchive.argtypes = [vp, ctypes.c_char_p, bl]
    d.SFileCompactArchive.restype = bl
    d.SFileGetMaxFileCount.argtypes = [vp]
    d.SFileGetMaxFileCount.restype = dw
    d.SFileSetMaxFileCount.argtypes = [vp, dw]
    d.SFileSetMaxFileCount.restype = bl
    d.SFileOpenFileEx.argtypes = [vp, ctypes.c_char_p, dw, ctypes.POINTER(vp)]
    d.SFileOpenFileEx.restype = bl
    d.SFileGetFileSize.argtypes = [vp, ctypes.POINTER(dw)]
    d.SFileGetFileSize.restype = dw
    d.SFileReadFile.argtypes = [vp, vp, dw, ctypes.POINTER(dw), vp]
    d.SFileReadFile.restype = bl
    d.SFileCloseFile.argtypes = [vp]
    d.SFileCloseFile.restype = bl
    _DLL = d
    return d


def _bool(v):
    return bool(v & 0xFF)       # BOOL returned in eax: only the low byte is reliable on some builds


class Archive:
    """One open MPQ (ctypes). Use as a context manager."""

    def __init__(self, path, write=False):
        self.path = path
        self.write = write
        self.h = ctypes.c_void_p()
        s = storm()
        flags = 0 if write else STREAM_FLAG_READ_ONLY
        ctypes.set_last_error(0)
        if not _bool(s.SFileOpenArchive(path, 0, flags, ctypes.byref(self.h))):
            err = ctypes.get_last_error()
            self.h = None
            raise DeployError(open_error_text(path, write, err))

    def close(self):
        if self.h:
            storm().SFileCloseArchive(self.h)
            self.h = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    @staticmethod
    def _n(name):
        return name.replace('/', '\\').encode('latin-1', 'replace')

    def has(self, name):
        return _bool(storm().SFileHasFile(self.h, self._n(name)))

    def read(self, name):
        s = storm()
        fh = ctypes.c_void_p()
        if not _bool(s.SFileOpenFileEx(self.h, self._n(name), 0, ctypes.byref(fh))):
            return None
        try:
            hi = wt.DWORD(0)
            size = s.SFileGetFileSize(fh, ctypes.byref(hi))
            buf = ctypes.create_string_buffer(size)
            got = wt.DWORD(0)
            if size and not _bool(s.SFileReadFile(fh, buf, size, ctypes.byref(got), None)):
                return None
            return buf.raw[:got.value]
        finally:
            s.SFileCloseFile(fh)

    def add(self, local_path, internal):
        s = storm()
        flags = MPQ_FILE_COMPRESS | MPQ_FILE_REPLACEEXISTING
        for attempt in range(3):
            ctypes.set_last_error(0)
            if _bool(s.SFileAddFileEx(self.h, local_path, self._n(internal), flags,
                                      MPQ_COMPRESSION_ZLIB, MPQ_COMPRESSION_ZLIB)):
                return
            err = ctypes.get_last_error()
            if err == ERROR_DISK_FULL:
                # hash table full: files past maxFileCount would be dropped - grow it and retry
                cur = s.SFileGetMaxFileCount(self.h)
                if not _bool(s.SFileSetMaxFileCount(self.h, max(cur * 2, 64))):
                    break
                continue
            raise DeployError("StormLib could not add '%s' to %s (error %d)." % (internal, os.path.basename(self.path), err))
        raise DeployError("Archive %s hash table is full and could not be enlarged." % os.path.basename(self.path))

    def compact(self, listfile_path=None):
        ctypes.set_last_error(0)
        lf = listfile_path.encode('mbcs') if listfile_path else None
        if not _bool(storm().SFileCompactArchive(self.h, lf, False)):
            raise DeployError("Compaction of %s failed (error %d)." % (os.path.basename(self.path),
                                                                        ctypes.get_last_error()))


def open_error_text(path, write, err):
    name = os.path.basename(path)
    if err in (ERROR_SHARING_VIOLATION, ERROR_LOCK_VIOLATION):
        return ("Archive %s is locked by another program (is the game client running?). Close it and try again."
                % name)
    if err == ERROR_ACCESS_DENIED and write:
        return "Archive %s cannot be opened for writing (access denied / read-only file)." % name
    if err == 2 or err == 3:
        return "Archive %s does not exist." % name
    return "Archive %s cannot be opened%s (Windows error %d)." % (name, ' for writing' if write else '', err)


# ------------------------------------------------------------------------------------------------ client layout

def data_dir_of(client_dir):
    d = os.path.join(client_dir, 'Data')
    if os.path.isdir(d):
        return d
    if any(f.lower().endswith('.mpq') for f in os.listdir(client_dir)):
        return client_dir
    raise DeployError("No Data folder with MPQ archives in '%s'." % client_dir)


def mount_order(client_dir):
    """Archive paths, ascending priority (last wins) - the same order the add-on's game data mounts."""
    data = data_dir_of(client_dir)
    try:
        from ..pywowlib.archives.wow_filesystem import WoWFileData
        order = [real for _norm, real in WoWFileData.list_game_data_paths(data) if os.path.isfile(real)]
        if order:
            return order
    except Exception:
        pass
    return sorted(os.path.join(data, f) for f in os.listdir(data) if f.lower().endswith('.mpq'))


def internal_norm(p):
    return p.replace('/', '\\').lstrip('\\')


def winner_of(order, internal):
    """(archive that wins for `internal`, [archives above it that do NOT contain it]) via read-only opens."""
    win = None
    for path in order:
        try:
            with Archive(path) as a:
                if a.has(internal):
                    win = path
        except DeployError:
            continue
    return win


def is_protected(path, protected):
    low = path.lower()
    return any(p.strip().lower() in low for p in protected if p and p.strip())


def check_archive(path, protected=DEFAULT_PROTECTED, probe_write=True):
    """None when `path` may be written, else the refusal reason (a sentence)."""
    name = os.path.basename(path)
    if not os.path.isfile(path):
        return "Archive %s does not exist." % name
    hit = [p for p in protected if p and p.strip() and p.strip().lower() in path.lower()]
    if hit:
        return "Archive %s is in a protected location (path contains '%s')." % (name, hit[0])
    size = os.path.getsize(path)
    if size >= MAX_ARCHIVE_BYTES:
        return ("Archive %s is %.2f GB - archives of %.1f GB or more are refused (StormLib compaction corrupts "
                "archives over 2 GB). Pick a smaller patch archive." % (name, size / 1024 ** 3,
                                                                       MAX_ARCHIVE_BYTES / 1024 ** 3))
    if probe_write:
        try:
            with Archive(path, write=True):
                pass
        except DeployError as e:
            return str(e)
    return None


def default_target(order, protected=DEFAULT_PROTECTED, probe_write=True):
    """Highest-priority patch archive (patch*.mpq) that passes check_archive."""
    for path in reversed(order):
        base = os.path.basename(path).lower()
        if not base.startswith('patch'):
            continue
        if check_archive(path, protected, probe_write) is None:
            return path
    return None


# ------------------------------------------------------------------------------------------------ file discovery

def sibling_files(model_path, internal_path):
    """[(local, internal)] for the model plus its sibling files with the same stem:
    M2: <stem>.m2, <stem>NN.skin, <stem>.anim / <stem>NNNN-NN.anim, <stem>.phys ...; WMO: <stem>.wmo, <stem>_NNN.wmo."""
    folder = os.path.dirname(model_path)
    base = os.path.basename(model_path)
    stem, ext = os.path.splitext(base)
    idir = internal_norm(os.path.dirname(internal_path.replace('/', '\\'))) if internal_path else ''
    iname = os.path.basename(internal_path.replace('/', '\\')) if internal_path else base
    istem = os.path.splitext(iname)[0]

    def join(name):
        return (idir + '\\' + name) if idir else name

    out = [(model_path, join(iname))]
    for n in sorted(os.listdir(folder)):
        if n.lower() == base.lower() or not n.lower().startswith(stem.lower()):
            continue
        rest = n[len(stem):]
        ok = False
        if ext.lower() == '.m2':
            ok = bool(re.fullmatch(r'\d{2}\.skin|(\d{4}-\d{2})?\.anim|\.phys|\.bone|\.skel', rest, re.I))
        elif ext.lower() == '.wmo':
            ok = bool(re.fullmatch(r'_\d{3}\.wmo|_lod\d\.wmo', rest, re.I))
        if ok:
            out.append((os.path.join(folder, n), join(istem + rest)))
    return out


# ------------------------------------------------------------------------------------------------ deploy

class Report:
    def __init__(self):
        self.lines = []
        self.target = None
        self.backup = None
        self.written = []
        self.ok = False

    def add(self, s):
        self.lines.append(s)


def backup_archive(path, backup_dir, client_dir, report):
    key = os.path.normcase(os.path.abspath(path))
    if key in _BACKED_UP:
        report.add("Backup of %s already made this session: %s" % (os.path.basename(path), _BACKED_UP[key]))
        report.backup = _BACKED_UP[key]
        return
    if not backup_dir:
        raise DeployError("No backup folder configured - refusing to write without a backup.")
    cd = os.path.normcase(os.path.abspath(client_dir)) + os.sep
    bd = os.path.normcase(os.path.abspath(backup_dir)) + os.sep
    if bd.startswith(cd):
        raise DeployError("The backup folder must be OUTSIDE the client (%s)." % backup_dir)
    os.makedirs(backup_dir, exist_ok=True)
    size = os.path.getsize(path)
    free = shutil.disk_usage(backup_dir).free
    if free < size + 64 * 1024 * 1024:
        raise DeployError("Not enough free space in the backup folder (%d MB needed)." % (size // 1048576 + 64))
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    dest = os.path.join(backup_dir, '%s.%s.bak' % (os.path.basename(path), stamp))
    shutil.copy2(path, dest)
    if os.path.getsize(dest) != size:
        raise DeployError("Backup copy of %s has the wrong size." % os.path.basename(path))
    _BACKED_UP[key] = dest
    report.backup = dest
    report.add("Backed up %s -> %s" % (os.path.basename(path), dest))


def _listfile_text(arc, names):
    """Existing (listfile) text plus every name we wrote, de-duplicated (StormLib keeps (listfile) itself up to date
    on close/compaction; handing the full list to the compaction makes sure no name is lost)."""
    cur = arc.read(LISTFILE.decode()) or b''
    lines = [x.strip() for x in cur.decode('latin-1').splitlines() if x.strip() and x.strip().lower() != '(listfile)']
    have = set(x.lower() for x in lines)
    for n in names:
        if n.lower() not in have:
            lines.append(n)
            have.add(n.lower())
    return '\r\n'.join(lines) + '\r\n'


def plan(client_dir, files, target_archive=None, protected=DEFAULT_PROTECTED, probe_write=True):
    """Work out where `files` [(local, internal)] would go. Returns (target_path|None, order, notes, problem|None).
    `notes` are informational/warning sentences; `problem` is a refusal reason."""
    order = mount_order(client_dir)
    notes = []
    primary = internal_norm(files[0][1])
    if target_archive:
        target = target_archive
        if not os.path.isabs(target):
            target = os.path.join(data_dir_of(client_dir), target)
    else:
        target = winner_of(order, primary)
        if target:
            notes.append("'%s' currently comes from %s - that archive is updated so the change is visible."
                         % (primary, os.path.basename(target)))
        else:
            target = default_target(order, protected, probe_write)
            if target is None:
                return None, order, notes, ("'%s' is new and no writable patch archive passed the safety rules "
                                            "(size, protected paths, lock). Choose an archive manually." % primary)
            notes.append("'%s' is new - default target: %s." % (primary, os.path.basename(target)))
    problem = check_archive(target, protected, probe_write)
    if problem:
        return target, order, notes, problem
    # shadowing: a higher-priority archive containing the path would hide our copy
    idx = [os.path.normcase(p) for p in order].index(os.path.normcase(target)) if os.path.normcase(target) in \
        [os.path.normcase(p) for p in order] else -1
    for p in order[idx + 1:] if idx >= 0 else []:
        try:
            with Archive(p) as a:
                shadow = [i for _l, i in files if a.has(internal_norm(i))]
        except DeployError:
            continue
        if shadow:
            notes.append("WARNING: %s (higher priority) also contains %s - the game will keep using that copy."
                         % (os.path.basename(p), shadow[0]))
    return target, order, notes, None


def deploy(client_dir, files, target_archive=None, protected=DEFAULT_PROTECTED, backup_dir='',
           release_game_data=None, compact=True):
    """Write `files` [(local_path, internal_path)] into the client. Returns a Report (report.ok). Raises DeployError
    for refusals. `release_game_data()` must close every handle this process holds on the archives."""
    if not files:
        raise DeployError("Nothing to deploy.")
    for local, internal in files:
        if not os.path.isfile(local):
            raise DeployError("File not found: %s" % local)
        if not internal.strip():
            raise DeployError("Empty internal path for %s." % local)
    rep = Report()
    if release_game_data:
        release_game_data()
    target, _order, notes, problem = plan(client_dir, files, target_archive, protected)
    for n in notes:
        rep.add(n)
    if problem:
        raise DeployError(problem)
    rep.target = target
    backup_archive(target, backup_dir, client_dir, rep)

    names = [internal_norm(i) for _l, i in files]
    import tempfile
    with Archive(target, write=True) as arc:
        for (local, _i), name in zip(files, names):
            arc.add(local, name)
        if compact:
            fd, tmp = tempfile.mkstemp(suffix='.txt')
            try:
                with os.fdopen(fd, 'wb') as f:
                    f.write(_listfile_text(arc, names).encode('latin-1', 'replace'))
                arc.compact(tmp)
            finally:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
    listed = True
    rep.add("Wrote %d file(s) to %s%s%s." % (len(files), os.path.basename(target),
                                             ', (listfile) refreshed', ', compacted' if compact else ''))

    # verify: read back byte for byte, listfile names
    with Archive(target) as arc:
        lf = arc.read(LISTFILE.decode()) or b''
        lfset = set(x.strip().lower() for x in lf.decode('latin-1').splitlines())
        for (local, _i), name in zip(files, names):
            with open(local, 'rb') as f:
                want = f.read()
            got = arc.read(name)
            if got != want:
                raise DeployError("Verification failed for %s: the archive does not hold the bytes that were written."
                                  % name)
            if name.lower() not in lfset:
                raise DeployError("Verification failed: %s is missing from (listfile)." % name)
            rep.written.append((name, len(want)))
            rep.add("  %s (%d bytes)" % (name, len(want)))
    rep.ok = True
    return rep


def reset_session_backups():
    _BACKED_UP.clear()
