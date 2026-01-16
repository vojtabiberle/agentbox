#!/bin/bash
set -euo pipefail

# agentbox installer
# Usage: curl -fsSL https://raw.githubusercontent.com/vojtabiberle/agentbox/main/install.sh | bash

VERSION="${AGENTBOX_VERSION:-latest}"
INSTALL_DIR="${AGENTBOX_INSTALL_DIR:-$HOME/.agentbox}"
BIN_DIR="${AGENTBOX_BIN_DIR:-$HOME/.local/bin}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info() { echo -e "${CYAN}==>${NC} $1"; }
success() { echo -e "${GREEN}==>${NC} $1"; }
warn() { echo -e "${YELLOW}==>${NC} $1"; }
error() { echo -e "${RED}==>${NC} $1" >&2; }

# Check for Python 3.10+
check_python() {
    local python_cmd=""

    for cmd in python3 python; do
        if command -v "$cmd" &>/dev/null; then
            local version
            version=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
            local major minor
            major=$(echo "$version" | cut -d. -f1)
            minor=$(echo "$version" | cut -d. -f2)

            if [[ "$major" -ge 3 && "$minor" -ge 10 ]]; then
                python_cmd="$cmd"
                break
            fi
        fi
    done

    if [[ -z "$python_cmd" ]]; then
        error "Python 3.10+ is required but not found."
        error "Please install Python 3.10 or later and try again."
        exit 1
    fi

    echo "$python_cmd"
}

# Check for container runtime
check_container_runtime() {
    if command -v podman &>/dev/null; then
        info "Found Podman"
        return 0
    elif command -v docker &>/dev/null; then
        info "Found Docker"
        return 0
    else
        warn "Neither Podman nor Docker found."
        warn "You'll need to install one before using agentbox."
    fi
}

main() {
    echo ""
    echo -e "${CYAN}Installing agentbox...${NC}"
    echo ""

    # Find Python
    info "Checking for Python 3.10+..."
    PYTHON=$(check_python)
    success "Found $PYTHON"

    # Check container runtime
    check_container_runtime

    # Create install directory
    info "Creating installation directory..."
    mkdir -p "$INSTALL_DIR"

    # Create virtual environment
    info "Creating virtual environment..."
    "$PYTHON" -m venv "$INSTALL_DIR/venv"

    # Install agentbox
    info "Installing agentbox..."
    if [[ "$VERSION" == "latest" ]]; then
        "$INSTALL_DIR/venv/bin/pip" install --quiet --upgrade agentbox
    else
        "$INSTALL_DIR/venv/bin/pip" install --quiet --upgrade "agentbox==$VERSION"
    fi

    # Create bin directory and symlink
    info "Creating symlink..."
    mkdir -p "$BIN_DIR"
    ln -sf "$INSTALL_DIR/venv/bin/agentbox" "$BIN_DIR/agentbox"

    # Check if BIN_DIR is in PATH
    if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
        warn "$BIN_DIR is not in your PATH."
        echo ""
        echo "Add this to your shell profile (.bashrc, .zshrc, etc.):"
        echo ""
        echo "    export PATH=\"\$PATH:$BIN_DIR\""
        echo ""
    fi

    echo ""
    success "agentbox installed successfully!"
    echo ""
    echo "Usage:"
    echo "    agentbox run ~/workspace/my-project"
    echo "    agentbox run ~/workspace/my-project --bash"
    echo "    agentbox --help"
    echo ""
}

main "$@"
