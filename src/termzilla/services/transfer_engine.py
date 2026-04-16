"""Async transfer engine for uploads and downloads."""

import asyncio
import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

import paramiko

logger = logging.getLogger("termzilla")


class TransferStatus(Enum):
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TransferDirection(Enum):
    UPLOAD = "upload"
    DOWNLOAD = "download"


@dataclass
class TransferJob:
    """Represents a single file transfer."""

    id: str
    source: str
    destination: str
    direction: TransferDirection
    size: int = 0
    transferred: int = 0
    status: TransferStatus = TransferStatus.QUEUED
    error: Optional[str] = None
    speed: float = 0.0  # bytes/sec


class TransferEngine:
    """Manages async file transfers."""

    def __init__(self, sftp_client: paramiko.SFTPClient) -> None:
        self.sftp = sftp_client
        self._jobs: dict[str, TransferJob] = {}
        self._job_counter = 0
        self._cancelled: set[str] = set()
        self._max_concurrent = 3  # Max parallel transfers

    async def upload(
        self,
        local_path: str,
        remote_path: str,
        callback: Optional[Callable[[int, int], None]] = None,
    ) -> TransferJob:
        """Upload a file or directory from local to remote."""
        job = self._create_job(
            source=local_path,
            destination=remote_path,
            direction=TransferDirection.UPLOAD,
        )
        await self._execute_upload(job, callback)
        return job

    async def _execute_upload(
        self,
        job: TransferJob,
        callback: Optional[Callable[[int, int], None]],
    ) -> None:
        job.status = TransferStatus.IN_PROGRESS
        try:
            local_path = Path(job.source)
            loop = asyncio.get_event_loop()
            if local_path.is_dir():
                await loop.run_in_executor(
                    None,
                    lambda: self._upload_dir(local_path, job.destination, job, callback),
                )
            else:
                job.size = local_path.stat().st_size

                def progress_callback(transferred: int, total: int) -> None:
                    logger.info(
                        f"DEBUG: progress_callback called with transferred={transferred}, total={total}"
                    )
                    job.transferred = transferred
                    if callback:
                        callback(transferred, total)

                await loop.run_in_executor(
                    None,
                    lambda: self.sftp.put(
                        str(local_path), job.destination, callback=progress_callback
                    ),
                )
            job.status = TransferStatus.COMPLETED
            job.transferred = job.size
            logger.info(f"Upload completed: {job.source} -> {job.destination}")
        except Exception as e:
            job.status = TransferStatus.FAILED
            job.error = str(e)
            logger.error(f"Upload failed: {e}")

    def _upload_dir(
        self,
        local_dir: Path,
        remote_dest: str,
        job: TransferJob,
        callback: Optional[Callable[[int, int], None]],
    ) -> None:
        """Recursively upload a local directory to remote (blocking)."""
        try:
            self.sftp.mkdir(remote_dest)
        except IOError:
            pass  # already exists
        for item in sorted(local_dir.iterdir()):
            r_path = f"{remote_dest.rstrip('/')}/{item.name}"
            if item.is_dir():
                self._upload_dir(item, r_path, job, callback)
            else:
                size = item.stat().st_size
                job.size += size

                def _cb(transferred: int, total: int) -> None:
                    job.transferred += transferred
                    if callback:
                        callback(job.transferred, job.size)

                self.sftp.put(str(item), r_path, callback=_cb)

    async def download(
        self,
        remote_path: str,
        local_path: str,
        callback: Optional[Callable[[int, int], None]] = None,
    ) -> TransferJob:
        """Download a file from remote to local.

        Args:
            remote_path: Remote file path
            local_path: Local destination path
            callback: Optional callback(transferred, total) for progress

        Returns:
            TransferJob instance
        """
        job = self._create_job(
            source=remote_path,
            destination=local_path,
            direction=TransferDirection.DOWNLOAD,
        )

        await self._execute_download(job, callback)
        return job

    async def _execute_download(
        self,
        job: TransferJob,
        callback: Optional[Callable[[int, int], None]],
    ) -> None:
        job.status = TransferStatus.IN_PROGRESS
        try:
            from stat import S_ISDIR

            remote_stat = self.sftp.stat(job.source)
            loop = asyncio.get_event_loop()

            if S_ISDIR(remote_stat.st_mode or 0):
                await loop.run_in_executor(
                    None,
                    lambda: self._download_dir(job.source, job.destination, job, callback),
                )
            else:
                job.size = remote_stat.st_size or 0
                Path(job.destination).parent.mkdir(parents=True, exist_ok=True)

                def progress_callback(transferred: int, total: int) -> None:
                    job.transferred = transferred
                    if callback:
                        callback(transferred, total)

                await loop.run_in_executor(
                    None,
                    lambda: self.sftp.get(job.source, job.destination, callback=progress_callback),
                )
            job.status = TransferStatus.COMPLETED
            job.transferred = job.size
            logger.info(f"Download completed: {job.source} -> {job.destination}")
        except Exception as e:
            job.status = TransferStatus.FAILED
            job.error = str(e)
            logger.error(f"Download failed: {e}")

    def _download_dir(
        self,
        remote_dir: str,
        local_dest: str,
        job: TransferJob,
        callback: Optional[Callable[[int, int], None]],
    ) -> None:
        """Recursively download a remote directory to local (blocking)."""
        from stat import S_ISDIR

        Path(local_dest).mkdir(parents=True, exist_ok=True)
        for attr in self.sftp.listdir_attr(remote_dir):
            r_path = f"{remote_dir.rstrip('/')}/{attr.filename}"
            l_path = str(Path(local_dest) / attr.filename)
            if S_ISDIR(attr.st_mode or 0):
                self._download_dir(r_path, l_path, job, callback)
            else:
                job.size += attr.st_size or 0

                def _cb(transferred: int, total: int) -> None:
                    job.transferred += transferred
                    if callback:
                        callback(job.transferred, job.size)

                self.sftp.get(r_path, l_path, callback=_cb)

    def cancel_transfer(self, job_id: str) -> None:
        """Mark a transfer as cancelled."""
        self._cancelled.add(job_id)
        if job_id in self._jobs:
            job = self._jobs[job_id]
            if job.status == TransferStatus.IN_PROGRESS:
                job.status = TransferStatus.CANCELLED

    def get_job(self, job_id: str) -> Optional[TransferJob]:
        """Get a transfer job by ID."""
        return self._jobs.get(job_id)

    def get_active_jobs(self) -> list[TransferJob]:
        """Get all non-completed jobs."""
        return [
            job
            for job in self._jobs.values()
            if job.status
            in (
                TransferStatus.QUEUED,
                TransferStatus.IN_PROGRESS,
            )
        ]

    def get_recent_jobs(self, limit: int = 10) -> list[TransferJob]:
        """Get recently completed/failed jobs."""
        completed = [
            job
            for job in self._jobs.values()
            if job.status
            in (
                TransferStatus.COMPLETED,
                TransferStatus.FAILED,
            )
        ]
        return completed[-limit:]

    def _create_job(
        self, source: str, destination: str, direction: TransferDirection
    ) -> TransferJob:
        """Create a new transfer job."""
        self._job_counter += 1
        job_id = f"job-{self._job_counter:04d}"
        job = TransferJob(
            id=job_id,
            source=source,
            destination=destination,
            direction=direction,
        )
        self._jobs[job_id] = job
        return job

    def _is_cancelled(self, job_id: str) -> bool:
        """Check if a job was cancelled."""
        return job_id in self._cancelled

    def clear_completed(self) -> None:
        """Remove completed jobs from memory."""
        self._jobs = {
            k: v
            for k, v in self._jobs.items()
            if v.status
            not in (
                TransferStatus.COMPLETED,
                TransferStatus.CANCELLED,
            )
        }
        self._cancelled.clear()
