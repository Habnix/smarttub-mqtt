# v0.1.0 - Initial Release

First public release of **smarttub-mqtt** - MQTT bridge for Jacuzzi SmartTub hot tubs.

## 🎯 Features

- **MQTT Bridge**: Full bidirectional communication between SmartTub API and MQTT broker
- **Automatic Discovery**: Detects spa capabilities (pumps, lights, heater) on startup
- **Web UI**: Real-time dashboard with health monitoring (port 8080)
- **Docker Ready**: Complete Docker deployment with docker-compose
- **Comprehensive Testing**: 193 tests (unit, integration, contract)
- **Error Tracking**: Centralized error handling with recovery strategies
- **Security**: Optional Basic Auth, secure credential handling

## 📦 Installation

### Quick Start (Docker)

```bash
mkdir -p /opt/smarttub-mqtt/config
cat > /opt/smarttub-mqtt/config/.env << EOF
SMARTTUB_EMAIL=your@email.com
SMARTTUB_PASSWORD=your_password
MQTT_BROKER_HOST=your-mqtt-broker
EOF

docker run -d \
  -v /opt/smarttub-mqtt/config:/config \
  -p 8080:8080 \
  ghcr.io/habnix/smarttub-mqtt:0.1.0
```

### Manual Installation

See [README.md](https://github.com/Habnix/smarttub-mqtt/blob/main/README.md) for detailed instructions.

## 🔧 Requirements

- Python 3.11+
- MQTT broker (Mosquitto recommended)
- SmartTub account with registered spa

## ✅ Verified Runtime

Tested on **November 1, 2025** with:
- ✅ MQTT connection (Mosquitto 2.x)
- ✅ SmartTub API (production account)
- ✅ Discovery (D1 Chairman spa)
- ✅ Web UI (FastAPI)
- ✅ 193/193 tests passing

## 📊 Test Coverage

| Component | Coverage |
|-----------|----------|
| Config Validation | 53% |
| Error Tracking | 95% |
| Discovery | 97% |
| Log Rotation | 94% |
| Basic Auth | 94% |
| MQTT Bridge | 63% |

## 🙏 Acknowledgements

Special thanks to **Matt Zimmerman** for the [python-smarttub](https://github.com/mdz/python-smarttub) library that makes this project possible.

## 📄 License

MIT License - see [LICENSE](https://github.com/Habnix/smarttub-mqtt/blob/main/LICENSE)

## 📖 Documentation

- [README](https://github.com/Habnix/smarttub-mqtt/blob/main/README.md)
- [Docker Guide](https://github.com/Habnix/smarttub-mqtt/blob/main/DOCKER.md)
- [Configuration](https://github.com/Habnix/smarttub-mqtt/blob/main/docs/configuration.md)
- [Testing Guide](https://github.com/Habnix/smarttub-mqtt/blob/main/docs/testing.md)

---

**Full Changelog**: https://github.com/Habnix/smarttub-mqtt/commits/v0.1.0
