#!/bin/bash

# setup_service.sh - Automatically configures and starts the posting service as a systemd service.
# Run this script from INSIDE the posting_service directory.

# Get the absolute path of the directory where this script is located
SERVICE_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PARENT_DIR="$( dirname "$SERVICE_DIR" )"
USER_NAME=$(whoami)
SERVICE_NAME="posting-service"

echo "Configuring service for user: $USER_NAME"
echo "Working directory: $PARENT_DIR"
echo "Service directory: $SERVICE_DIR"

# Path to the python executable in the venv
PYTHON_PATH="$SERVICE_DIR/venv/bin/python"

if [ ! -f "$PYTHON_PATH" ]; then
    echo "Error: Virtual environment not found at $PYTHON_PATH"
    echo "Please create a venv inside the posting_service directory first."
    exit 1
fi

# Create the systemd service file
cat <<EOF | sudo tee /etc/systemd/system/$SERVICE_NAME.service
[Unit]
Description=Social Media Posting Service
After=network.target

[Service]
Type=simple
User=$USER_NAME
WorkingDirectory=$PARENT_DIR
ExecStart=$PYTHON_PATH -m posting_service
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

# Reload, enable and start
sudo systemctl daemon-reload
sudo systemctl enable $SERVICE_NAME
sudo systemctl restart $SERVICE_NAME

echo "------------------------------------------------"
echo "Service $SERVICE_NAME installed and started!"
echo "Check status: sudo systemctl status $SERVICE_NAME"
echo "View logs:    sudo journalctl -u $SERVICE_NAME -f"
echo "------------------------------------------------"
