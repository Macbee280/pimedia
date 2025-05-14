#!/bin/bash
# PiMedia Setup Script for Standard Raspberry Pi OS
# This script installs all dependencies and configures the system for PiMedia

# Exit on error
set -e

echo "===== PiMedia Setup Script ====="

# Update system
echo "Updating system packages..."
sudo apt update
sudo apt upgrade -y

# Install required packages
echo "Installing required dependencies..."
sudo apt install -y python3-pip python3-venv vlc chromium-browser xdotool unclutter git

# Setup Python virtual environment
echo "Setting up Python virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
echo "Installing Python dependencies..."
pip install --upgrade pip
pip install Flask Flask-Sock yt-dlp requests qrcode pillow python-dotenv netifaces psutil

# Setup autostart for kiosk mode
echo "Configuring kiosk mode autostart..."
mkdir -p ~/.config/autostart

# Create autostart entry for PiMedia
cat > ~/.config/autostart/pimedia-kiosk.desktop << EOT
[Desktop Entry]
Type=Application
Name=PiMedia Kiosk
Exec=/usr/bin/chromium-browser --kiosk --incognito --disable-restore-session-state --disable-translate --no-first-run http://localhost:5000
X-GNOME-Autostart-enabled=true
EOT

# Create startup script that ensures the Flask server is running
cat > ~/pimedia/start_pimedia.sh << EOT
#!/bin/bash
# Wait for network
sleep 10
# Make sure the Flask app is running first
cd ~/pimedia
source venv/bin/activate
python app.py &
EOT

chmod +x ~/pimedia/start_pimedia.sh

# Create autostart entry for PiMedia startup script
cat > ~/.config/autostart/pimedia-server.desktop << EOT
[Desktop Entry]
Type=Application
Name=PiMedia Server
Exec=/home/pi/pimedia/start_pimedia.sh
X-GNOME-Autostart-enabled=true
EOT

# Create systemd service file for PiMedia (alternative to autostart)
echo "Creating systemd service..."
sudo tee /etc/systemd/system/pimedia.service > /dev/null << EOT
[Unit]
Description=PiMedia Player Service
After=network.target

[Service]
User=$USER
WorkingDirectory=/home/$USER/pimedia
ExecStart=/home/$USER/pimedia/venv/bin/python /home/$USER/pimedia/app.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=pimedia
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOT

# Enable the service
echo "Enabling and starting PiMedia service..."
sudo systemctl enable pimedia.service
sudo systemctl start pimedia.service

# Disable screen blanking
echo "Disabling screen blanking..."
cat > ~/.config/autostart/disable-blanking.desktop << EOT
[Desktop Entry]
Type=Application
Name=Disable Screen Blanking
Exec=xset s off -dpms
X-GNOME-Autostart-enabled=true
EOT

# Configure auto-login (should already be setup on standard Raspberry Pi OS)
echo "Configuring auto-login..."
sudo raspi-config nonint do_boot_behaviour B4

echo "Setup complete! Your PiMedia Player is now configured."
echo "Please reboot your Raspberry Pi for all changes to take effect:"
echo "sudo reboot"