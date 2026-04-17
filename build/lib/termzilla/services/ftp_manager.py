"""FTP/FTPS connection and filesystem backend."""

import ftplib
import logging
import os
import tempfile
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger("termzilla")


def connect_ftp(
    host: str,
    port: int,
    username: str,
    password: str,
    protocol: str,
    timeout: int = 10,
) -> ftplib.FTP:
    """Connect via FTP or FTPS, return an ftplib.FTP instance."""
    if protocol == "ftps":
        ftp: ftplib.FTP = ftplib.FTP_TLS(timeout=timeout)
        ftp.connect(host, port)
        ftp.login(username, password)
        ftp.prot_p()  # type: ignore[attr-defined]  # enable encrypted data channel
    else:
        ftp = ftplib.FTP(timeout=timeout)
        ftp.connect(host, port)
        ftp.login(username, password)
    return ftp


class FtpFileSystem:
    """FTP/FTPS filesystem — same external interface as RemoteFileSystem."""

    def __init__(self, ftp: ftplib.FTP) -> None:
        self.ftp = ftp
        self.current_path: str = ftp.pwd()

    # ── Navigation ────────────────────────────────────────────────────

    def get_current_path(self) -> str:
        return self.current_path

    def change_directory(self, path: str) -> str:
        self.ftp.cwd(path)
        self.current_path = self.ftp.pwd()
        return self.current_path

    # ── Listing ───────────────────────────────────────────────────────

    def list_directory(self, path: Optional[str] = None) -> list[dict]:
        target = path or self.current_path
        entries: list[dict] = []
        try:
            for name, facts in self.ftp.mlsd(target):
                if name in (".", ".."):
                    continue
                is_dir = facts.get("type", "") in ("dir", "cdir", "pdir")
                size = int(facts.get("size", 0)) if not is_dir else 0
                modified = 0.0
                if "modify" in facts:
                    try:
                        from datetime import datetime
                        dt = datetime.strptime(facts["modify"][:14], "%Y%m%d%H%M%S")
                        modified = dt.timestamp()
                    except Exception:
                        pass
                entries.append({
                    "name": name,
                    "path": f"{target.rstrip('/')}/{name}",
                    "is_dir": is_dir,
                    "size": size,
                    "modified": modified,
                })
        except ftplib.error_perm:
            # MLSD not supported — fall back to NLST
            try:
                for name in self.ftp.nlst(target):
                    basename = name.split("/")[-1]
                    if basename in (".", "..", ""):
                        continue
                    entry_path = f"{target.rstrip('/')}/{basename}"
                    try:
                        size = self.ftp.size(entry_path) or 0
                        is_dir = False
                    except Exception:
                        size = 0
                        is_dir = True
                    entries.append({
                        "name": basename,
                        "path": entry_path,
                        "is_dir": is_dir,
                        "size": size,
                        "modified": 0.0,
                    })
            except Exception as e:
                logger.error(f"FTP NLST error: {e}")
        return sorted(entries, key=lambda e: (not e["is_dir"], e["name"].lower()))

    # ── File operations ───────────────────────────────────────────────

    def create_directory(self, path: str) -> None:
        self.ftp.mkd(path)

    def delete(self, path: str) -> None:
        try:
            self.ftp.delete(path)
        except ftplib.error_perm:
            self._rmdir_recursive(path)

    def _rmdir_recursive(self, path: str) -> None:
        for entry in self.list_directory(path):
            if entry["is_dir"]:
                self._rmdir_recursive(entry["path"])
            else:
                self.ftp.delete(entry["path"])
        self.ftp.rmd(path)

    def rename(self, old_path: str, new_path: str) -> None:
        self.ftp.rename(old_path, new_path)

    def copy(self, src_path: str, dest_path: str, callback: Optional[Callable] = None) -> None:
        """FTP has no server-side copy — download to temp then re-upload."""
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = tmp.name
        try:
            self.download(src_path, tmp_path)
            self.upload(tmp_path, dest_path, callback)
        finally:
            os.unlink(tmp_path)

    # ── Transfers ─────────────────────────────────────────────────────

    def upload(self, local_path: str, remote_path: str, callback: Optional[Callable] = None) -> None:
        total = Path(local_path).stat().st_size
        transferred = [0]

        def handle(data: bytes) -> None:
            transferred[0] += len(data)
            if callback:
                callback(transferred[0], total)

        with open(local_path, "rb") as f:
            self.ftp.storbinary(f"STOR {remote_path}", f, 65536, handle)

    def download(self, remote_path: str, local_path: str, callback: Optional[Callable] = None) -> None:
        total = 0
        try:
            total = self.ftp.size(remote_path) or 0
        except Exception:
            pass
        transferred = [0]

        with open(local_path, "wb") as f:
            def handle(data: bytes) -> None:
                f.write(data)
                transferred[0] += len(data)
                if callback:
                    callback(transferred[0], max(total, transferred[0]))
            self.ftp.retrbinary(f"RETR {remote_path}", handle, 65536)
