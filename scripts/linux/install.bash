#!/bin/bash
# HsBot Installation Script for Linux
# This script sets up the virtual environment and installs dependencies

echo "=== HsBot Installation ==="
echo ""

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "Error: Python3 is not installed"
    echo "Please install Python3 using your package manager:"
    echo "  Ubuntu/Debian: sudo apt install python3 python3-venv python3-pip"
    echo "  Fedora/RHEL:   sudo dnf install python3 python3-pip"
    echo "  Arch:          sudo pacman -S python python-pip"
    exit 1
fi

PYTHON_VERSION=$(python3 --version)
echo "Found: $PYTHON_VERSION"

echo ""
echo "Step 1: Creating virtual environment..."
if [ -d "venv" ]; then
    echo "Virtual environment already exists. Skipping creation."
else
    python3 -m venv venv
    if [ $? -eq 0 ]; then
        echo "Virtual environment created successfully."
    else
        echo "Error: Failed to create virtual environment"
        exit 1
    fi
fi

echo ""
echo "Step 2: Verifying virtual environment..."
VENV_PYTHON="venv/bin/python"
VENV_PIP="venv/bin/pip"

if [ ! -f "$VENV_PYTHON" ]; then
    echo "Error: Virtual environment Python not found at $VENV_PYTHON"
    echo "Virtual environment creation may have failed."
    exit 1
fi

echo "Virtual environment Python found at: $VENV_PYTHON"

echo ""
echo "Step 3: Upgrading pip in virtual environment..."
"$VENV_PYTHON" -m pip install --upgrade pip --quiet
if [ $? -ne 0 ]; then
    echo "Error: Failed to upgrade pip"
    exit 1
fi
echo "pip upgraded successfully."

echo ""
echo "Step 4: Installing dependencies from requirements.txt..."
"$VENV_PIP" install -r requirements.txt
INSTALL_EXIT_CODE=$?

if [ $INSTALL_EXIT_CODE -ne 0 ]; then
    echo ""
    echo "Warning: Some packages failed to install"
    echo ""
    echo "Note: psutil may fail on some systems."
    echo "To install psutil, try:"
    echo "  - Ubuntu/Debian: sudo apt install python3-psutil"
    echo "  - Fedora/RHEL:   sudo dnf install python3-psutil"
    echo "  - Arch:          sudo pacman -S python-psutil"
    echo ""
    echo "Alternatively, the bot will work without psutil (resource monitoring disabled)."
    echo ""
    
    # Try installing without psutil
    echo "Attempting to install core dependencies without psutil..."
    "$VENV_PIP" install discord.py aiosqlite
    if [ $? -eq 0 ]; then
        echo "Core dependencies installed successfully (without psutil)."
    else
        echo "Error: Failed to install core dependencies"
        echo "Please check your requirements.txt file and internet connection."
        exit 1
    fi
else
    echo "Dependencies installed successfully."
fi

echo ""
echo "=== Optional: Bot Token Configuration ==="
echo ""
read -p "Do you want to configure a bot token now? (y/N): " response

if [[ "$response" =~ ^[Yy]$ ]]; then
    echo ""
    read -sp "Please enter your Discord bot token: " token
    echo ""
    
    if [ -n "$token" ]; then
        # Create config directory in user's home
        CONFIG_DIR="$HOME/.config/hsbot"
        CONFIG_FILE="$CONFIG_DIR/config"
        
        mkdir -p "$CONFIG_DIR"
        
        # Store token in config file with correct variable name
        echo "WZ_BOT_TOKEN=$token" > "$CONFIG_FILE"
        
        # Set restrictive permissions (only user can read/write)
        chmod 600 "$CONFIG_FILE"
        
        echo ""
        echo "Bot token stored successfully."
        echo "Config location: $CONFIG_FILE"
        echo "Permissions set to 600 (user read/write only)"
    else
        echo ""
        echo "No token entered. Skipping token configuration."
    fi
else
    echo "Skipping bot token configuration."
fi

echo ""
echo "=== Installation Complete ==="
echo ""
echo "Next steps:"
echo "  1. Activate the virtual environment: source venv/bin/activate"
echo "     (or use directly: ./venv/bin/python Bot.py)"
echo "  2. Run your bot: python Bot.py"
echo ""
echo "To retrieve the stored bot token, use:"
echo "  cat ~/.config/hsbot/config"
echo "Or source it in your environment:"
echo "  source ~/.config/hsbot/config"
echo ""