"""Reject incomplete image inventories before signing or publishing them."""

import json
import sys
from collections import Counter
from pathlib import Path


def verify(root: Path) -> str:
    installed = {
        tuple(line.split("\t", 1))
        for line in (root / "rpm-packages.txt").read_text().splitlines()
    }
    syft = json.loads((root / "sbom.syft.json").read_text())
    cdx = json.loads((root / "sbom.cdx.json").read_text())
    scan = json.loads((root / "vulnerabilities.json").read_text())
    cataloged = {
        (package["name"], package["version"].split(":", 1)[-1])
        for package in syft["artifacts"] if package["type"] == "rpm"
    }
    attested = {
        (package["name"], package["version"].split(":", 1)[-1])
        for package in cdx["components"] if package.get("purl", "").startswith("pkg:rpm/")
    }
    if not installed or not installed <= cataloged or not installed <= attested:
        raise ValueError("SBOM omits installed RPM names/versions; refusing publication")
    if scan.get("distro", {}).get("id") != "fedora":
        raise ValueError("Vulnerability report does not identify Fedora; refusing publication")
    counts = Counter(match["vulnerability"]["severity"] for match in scan["matches"])
    return f"Verified {len(installed)} RPM packages in both inventories. Findings (report-only): {dict(counts)}"


if __name__ == "__main__":
    print(verify(Path(sys.argv[1])))
