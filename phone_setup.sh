#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail


# Ensure Termux path is loaded
export PATH="/data/data/com.termux/files/usr/bin:$PATH"

echo "=================================================="
echo " Garmin Custom DSW - Termux Setup Script "
echo "=================================================="

# 1. Create target directories first to avoid access conflicts
echo "1. Creating local directories..."
mkdir -p "$HOME/scripts"
mkdir -p "$HOME/bin"
mkdir -p "$HOME/.config/garmin"
mkdir -p "$HOME/.garminconnect"

# 2. Update pkg repo and install system dependencies
echo "2. Installing system packages (python, build tools, openssl)..."
pkg update -y
pkg install -y python build-essential libffi openssl openssl-tool termux-tools termux-api python-cryptography

# 3. Install python package dependencies
echo "3. Installing Python libraries (Flask, PyYAML, requests, garminconnect)..."
pip install Flask PyYAML requests urllib3 garminconnect

# 4. Copy files into position
echo "4. Copying scripts and binaries..."
REPO_DIR=$(pwd)

if [ -d "$REPO_DIR/phone" ]; then
    cp -r "$REPO_DIR/phone/scripts/"* "$HOME/scripts/"
    cp "$REPO_DIR/phone/bin/wake_poll.sh" "$HOME/bin/wake_poll.sh"
    chmod +x "$HOME/bin/wake_poll.sh"
    echo "Files copied successfully."
else
    echo "ERROR: Could not find 'phone' folder in the current directory."
    echo "Please make sure you run this script from the root of the cloned repository."
    exit 1
fi

# 5. Initialize credentials secrets file if not present
SECRETS_FILE="$HOME/.config/garmin/secrets.yaml"
if [ ! -f "$SECRETS_FILE" ]; then
    echo "5. Initializing secrets.yaml configuration..."
    cat << 'EOF' > "$SECRETS_FILE"
garmin_email: "your_email@example.com"
garmin_password: "your_garmin_password_here"
EOF
    chmod 600 "$SECRETS_FILE"
    echo "Secrets file initialized at: $SECRETS_FILE"
else
    echo "5. Secrets file already exists. Skipping initialization."
fi

# 6. Generate local SSL Certificate for secure HTTPS loopback
CERT_FILE="$HOME/scripts/cert.pem"
KEY_FILE="$HOME/scripts/key.pem"
if [ ! -f "$CERT_FILE" ] || [ ! -f "$KEY_FILE" ]; then
    echo "6. Generating self-signed SSL certificate for secure GCM HTTPS loopback..."
    
    openssl req -x509 -newkey rsa:2048 -nodes -out "$CERT_FILE" -keyout "$KEY_FILE" -days 365 -subj "/CN=localhost"
    echo "SSL Certificate generated at $CERT_FILE"
else
    echo "6. SSL Certificate already exists. Skipping generation."
fi

# 7. Configure Android Job Scheduler for passive wake checks
echo "7. Registering wake_poll.sh with Android Task Scheduler (every 20 mins)..."
if command -v termux-job-scheduler &> /dev/null; then
    termux-job-scheduler --network unmetered --charging false --persisted true --period-ms 1200000 -s "$HOME/bin/wake_poll.sh"
    echo "Task scheduler job successfully registered."
else
    echo "WARNING: termux-job-scheduler not found. Please install Termux:API app and package if you want automated wake checks."
fi

echo "=================================================="
echo " Setup Complete! Next Steps:"
echo " 1. Edit your Garmin credentials in:"
echo "    nano $SECRETS_FILE"
echo " 2. Edit your training preferences in:"
echo "    nano $HOME/scripts/config.yaml"
echo " 3. Start the local Flask server on your phone:"
echo "    python $HOME/scripts/local_server.py"
echo ""
echo " CRITICAL ANDROID PERFORMANCE REMINDERS:"
echo " - To prevent Android from suspending your Termux server in the background,"
echo "   disable battery optimization for Termux (Settings -> Apps -> Termux -> Battery)."
echo " - If you want the background sleep-polling job scheduler to work,"
echo "   make sure you have installed the 'Termux:API' application from your app store."
echo "=================================================="
