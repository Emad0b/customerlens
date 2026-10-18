import hashlib
import io
import json
import urllib.request
import zipfile
from pathlib import Path


def main():
    metadata = json.loads(Path("data/source.json").read_text())
    destination = Path("data/online_retail.xlsx")
    if (
        destination.exists()
        and hashlib.sha256(destination.read_bytes()).hexdigest() == metadata["sha256"]
    ):
        print("Verified existing UCI workbook.")
        return
    with urllib.request.urlopen(metadata["url"], timeout=90) as response:
        content = response.read(40 * 1024 * 1024 + 1)
    if len(content) > 40 * 1024 * 1024:
        raise ValueError("Archive exceeds size bound")
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        if archive.getinfo("Online Retail.xlsx").file_size > 40 * 1024 * 1024:
            raise ValueError("Workbook exceeds size bound")
        workbook = archive.read("Online Retail.xlsx")
    if hashlib.sha256(workbook).hexdigest() != metadata["sha256"]:
        raise ValueError("Workbook SHA-256 does not match the source manifest")
    destination.write_bytes(workbook)
    print("Downloaded and fingerprint-verified UCI workbook.")


if __name__ == "__main__":
    main()
