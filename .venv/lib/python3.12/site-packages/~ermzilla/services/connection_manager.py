"""SSH/SFTP connection manager using paramiko."""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import paramiko

logger = logging.getLogger("termzilla")


@dataclass
class ConnectionInfo:
    """Container for connection parameters."""
    host: str = ""
    port: int = 22
    username: str = ""
    password: Optional[str] = None
    key_path: Optional[str] = None
    label: Optional[str] = None


class ConnectionManager:
    """Manages SSH/SFTP connections."""

    def __init__(self) -> None:
        self._ssh_client: Optional[paramiko.SSHClient] = None
        self._sftp_client: Optional[paramiko.SFTPClient] = None
        self._connection_info: Optional[ConnectionInfo] = None

    @property
    def is_connected(self) -> bool:
        """Check if currently connected."""
        if self._sftp_client is None:
            return False
        try:
            # Test the connection by getting current directory
            self._sftp_client.getcwd()
            return True
        except Exception:
            return False

    @property
    def connection_info(self) -> Optional[ConnectionInfo]:
        """Get current connection info."""
        return self._connection_info

    def connect(
        self,
        host: str,
        port: int = 22,
        username: str = "",
        password: Optional[str] = None,
        key_path: Optional[str] = None,
        timeout: int = 10,
    ) -> paramiko.SFTPClient:
        """Establish SSH/SFTP connection.
        
        Args:
            host: Remote hostname or IP
            port: SSH port (default 22)
            username: SSH username
            password: SSH password (optional if using key)
            key_path: Path to SSH private key (optional)
            timeout: Connection timeout in seconds
            
        Returns:
            paramiko.SFTPClient instance
            
        Raises:
            Exception: Connection errors with descriptive messages
        """
        self.disconnect()  # Clean up any existing connection

        logger.info(f"Connecting to {host}:{port} as {username}")

        self._ssh_client = paramiko.SSHClient()
        self._ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            connect_kwargs = {
                "hostname": host,
                "port": port,
                "username": username,
                "timeout": timeout,
                "allow_agent": True,
                "look_for_keys": True,
            }

            # Authentication
            if key_path:
                key_path_expanded = Path(key_path).expanduser()
                logger.info(f"Using SSH key: {key_path_expanded}")
                # Try different key types
                for key_class in (
                    paramiko.RSAKey,
                    paramiko.DSSKey,
                    paramiko.ECDSAKey,
                    paramiko.Ed25519Key,
                ):
                    try:
                        pkey = key_class.from_private_key_file(
                            str(key_path_expanded)
                        )
                        connect_kwargs["pkey"] = pkey
                        break
                    except paramiko.SSHException:
                        continue
                    except Exception as e:
                        logger.debug(f"Key type {key_class} failed: {e}")

                if "pkey" not in connect_kwargs:
                    raise ConnectionError(
                        f"Unable to load SSH key from {key_path_expanded}"
                    )
            elif password:
                connect_kwargs["password"] = password
            else:
                raise ConnectionError("Password or SSH key is required")

            # Connect
            self._ssh_client.connect(**connect_kwargs)
            self._sftp_client = self._ssh_client.open_sftp()

            self._connection_info = ConnectionInfo(
                host=host,
                port=port,
                username=username,
                password=password,
                key_path=key_path,
            )

            logger.info(f"Connected to {host}:{port}")
            return self._sftp_client

        except paramiko.AuthenticationException:
            raise ConnectionError("Authentication failed. Check username/password/key.")
        except paramiko.SSHException as e:
            raise ConnectionError(f"SSH error: {e}")
        except ConnectionRefusedError:
            raise ConnectionError(f"Connection refused by {host}:{port}")
        except TimeoutError:
            raise ConnectionError(f"Connection timed out to {host}:{port}")
        except Exception as e:
            raise ConnectionError(f"Failed to connect: {e}")

    def disconnect(self) -> None:
        """Close the current connection."""
        try:
            if self._sftp_client:
                self._sftp_client.close()
                self._sftp_client = None
            if self._ssh_client:
                self._ssh_client.close()
                self._ssh_client = None
            self._connection_info = None
            logger.info("Disconnected")
        except Exception as e:
            logger.error(f"Error during disconnect: {e}")

    def get_sftp(self) -> Optional[paramiko.SFTPClient]:
        """Get the current SFTP client."""
        return self._sftp_client

    def get_display_string(self) -> str:
        """Get a display-friendly connection string."""
        if self._connection_info is None:
            return "Not connected"
        info = self._connection_info
        return f"{info.username}@{info.host}:{info.port}"


class ConnectionError(Exception):
    """Custom exception for connection errors."""
    pass
