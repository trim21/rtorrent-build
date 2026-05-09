"""Shared download utility with tqdm progress bar."""

import time
from pathlib import Path

import httpx
from tqdm import tqdm

MAX_RETRIES = 5
RETRY_DELAY = 3


def download_file(url: str, dest: Path, desc: str = "") -> None:
    """Download a file from *url* to *dest* with a tqdm progress bar.

    Downloads to a ``.part`` temp file first, then atomically renames to
    *dest* on success so an interrupted download is never mistaken for
    a complete one. Retries up to 5 times on failure.
    """
    if dest.exists():
        print(f"Using cached {dest}")
        return

    part = dest.with_suffix(dest.suffix + ".part")
    last_exc: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"Downloading {desc} from {url} (attempt {attempt}/{MAX_RETRIES})")
            with httpx.stream("GET", url, follow_redirects=True) as response:
                response.raise_for_status()
                total = int(response.headers.get("content-length", 0))
                with (
                    open(part, "wb") as f,
                    tqdm(
                        total=total,
                        unit="B",
                        unit_scale=True,
                        unit_divisor=1024,
                        desc=desc or dest.name,
                        ascii=True,
                    ) as bar,
                ):
                    for chunk in response.iter_bytes(chunk_size=65536):
                        f.write(chunk)
                        bar.update(len(chunk))
            part.rename(dest)
            print(f"Downloaded {dest}")
            return
        except Exception as exc:
            last_exc = exc
            if part.exists():
                part.unlink()
            if attempt < MAX_RETRIES:
                print(
                    f"Download failed (attempt {attempt}/{MAX_RETRIES}): "
                    f"{exc}, retrying in {RETRY_DELAY}s..."
                )
                time.sleep(RETRY_DELAY)
            else:
                print(f"Download failed after {MAX_RETRIES} attempts: {exc}")
    raise RuntimeError(f"Failed to download {url} after {MAX_RETRIES} attempts") from last_exc
