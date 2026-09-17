#!/bin/sh
# Linux amd64 CI tools, pinned to release asset SHA256 from GitHub.
set -eu
scanner_dir="$1"
mkdir -p "$scanner_dir"
install_scanner() {
    scanner_name="$1"
    scanner_version="$2"
    scanner_hash="$3"
    scanner_archive="$scanner_dir/$scanner_name.tar.gz"
    curl -fsSL --retry 3 "https://github.com/anchore/$scanner_name/releases/download/v$scanner_version/${scanner_name}_${scanner_version}_linux_amd64.tar.gz" -o "$scanner_archive"
    printf '%s  %s\n' "$scanner_hash" "$scanner_archive" | sha256sum -c -
    tar -xzf "$scanner_archive" -C "$scanner_dir" "$scanner_name"
}
install_scanner syft 1.51.1 8fcb33017a0dc1058298c923c436d19dfa68ae93968e0b423248542e3afb9fc3
install_scanner grype 0.118.0 1d444c5e7360471815f7158f71935fcecc68a3c417d85c7344f770854300bba2
