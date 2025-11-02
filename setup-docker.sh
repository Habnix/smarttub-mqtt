#!/bin/bash
# SmartTub-MQTT Docker Setup Script

set -e

echo "🚀 SmartTub-MQTT Docker Setup"
echo "=============================="
echo ""

# Create directories
echo "📁 Creating directories..."
mkdir -p config
mkdir -p logs
mkdir -p mosquitto/config
mkdir -p mosquitto/data
mkdir -p mosquitto/log

# Set correct permissions for container access
chmod 777 config logs
chmod -R 777 mosquitto 2>/dev/null || true

# Create .env file if it doesn't exist
if [ ! -f config/.env ]; then
    echo "📝 Creating config/.env file..."
    cat > config/.env << 'EOF'
# SmartTub API Credentials
# WICHTIG: Email und besonders Passwort in einfache Anführungszeichen setzen!
# Beispiel: SMARTTUB_PASSWORD='mein!Passwort#123'
# Ohne Anführungszeichen können Sonderzeichen (!, #, $, etc.) zu Fehlern führen!
SMARTTUB_EMAIL='your@email.com'
SMARTTUB_PASSWORD='your_password'

# MQTT Broker Configuration
MQTT_BROKER_URL=192.168.178.164:1883
MQTT_USERNAME=
MQTT_PASSWORD=
MQTT_BASE_TOPIC=smarttub-mqtt
# MQTT_CLIENT_ID=

# Discovery Settings
CHECK_SMARTTUB=true
DISCOVERY_REFRESH_INTERVAL=3600
DISCOVERY_TEST_ALL_LIGHT_MODES=true

# Web UI Configuration
WEB_ENABLED=true
WEB_PORT=8080
WEB_HOST=0.0.0.0
WEB_AUTH_ENABLED=false
WEB_AUTH_USERNAME=admin
WEB_AUTH_PASSWORD=changeme

# Logging
LOG_LEVEL=INFO
LOG_DIR=/logs

# Polling & Safety
SMARTTUB_POLLING_INTERVAL_SECONDS=30
SAFETY_POST_COMMAND_WAIT_SECONDS=12
SAFETY_COMMAND_VERIFICATION_RETRIES=3
SAFETY_COMMAND_TIMEOUT_SECONDS=7

# Paths
CONFIG_PATH=/config/smarttub.yaml
EOF
    
    echo ""
    echo "⚠️  IMPORTANT: Edit config/.env with your credentials!"
    echo "   nano config/.env"
    echo ""
else
    echo "✅ config/.env already exists"
fi

# Create smarttub.yaml if it doesn't exist
if [ ! -f config/smarttub.yaml ]; then
    if [ -f config/smarttub.example.yaml ]; then
        echo "📝 Creating config/smarttub.yaml from example..."
        cp config/smarttub.example.yaml config/smarttub.yaml
        chmod 666 config/smarttub.yaml
    else
        echo "⚠️  WARNING: config/smarttub.example.yaml not found!"
        echo "   The container will create a default config on first start."
    fi
else
    echo "✅ config/smarttub.yaml already exists"
fi

# Create mosquitto config if needed (commented out by default)
if [ ! -f mosquitto/config/mosquitto.conf ]; then
    echo "📝 Creating mosquitto/config/mosquitto.conf..."
    cat > mosquitto/config/mosquitto.conf << 'EOF'
# Mosquitto MQTT Broker Configuration
listener 1883
allow_anonymous true

# Persistence
persistence true
persistence_location /mosquitto/data/

# Logging
log_dest stdout
log_type all

# System topics
sys_interval 10
EOF
fi

echo ""
echo "✅ Setup complete!"
echo ""
echo "📋 Next steps:"
echo ""
echo "1. Edit your credentials:"
echo "   nano config/.env"
echo ""
echo "2. Start the container:"
echo "   docker compose up -d"
echo ""
echo "3. View logs:"
echo "   docker compose logs -f smarttub-mqtt"
echo ""
echo "4. Access Web UI:"
echo "   http://localhost:8080"
echo ""
echo "5. Stop the container:"
echo "   docker compose down"
echo ""
