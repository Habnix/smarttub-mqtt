# SmartTub-MQTT Docker Deployment

Complete Docker Compose stack for running SmartTub-MQTT with MQTT Broker and OpenHAB.

## Quick Start

### 1. Prerequisites

- Docker Engine 20.10+
- Docker Compose 2.0+
- SmartTub account credentials

### 2. Setup

```bash
# Navigate to deploy directory
cd deploy/

# Copy environment template
cp .env.example .env

# Edit .env with your credentials
nano .env
```

**Required variables in `.env`:**
- `SMARTTUB_EMAIL` - Your SmartTub account email
- `SMARTTUB_PASSWORD` or `SMARTTUB_TOKEN` - Authentication credentials

### 3. Start Services

```bash
# Copy compose template (if needed)
cp docker-compose.example.yml docker-compose.yml

# Start all services
docker-compose up -d

# View logs
docker-compose logs -f
```

### 4. Access Services

- **SmartTub-MQTT Web UI**: http://localhost:8080
- **OpenHAB**: http://localhost:8181
- **MQTT Broker**: mqtt://localhost:1883

## Services

### Mosquitto (MQTT Broker)

Eclipse Mosquitto MQTT broker for message routing.

**Ports:**
- `1883` - MQTT protocol
- `9001` - WebSocket (optional)

**Configuration:**
- Config: `./mosquitto/config/mosquitto.conf`
- Data: `./mosquitto/data/`
- Logs: `./mosquitto/log/`

**Enable Authentication:**

```bash
# Create password file
docker-compose exec mosquitto mosquitto_passwd -c /mosquitto/config/passwd admin

# Edit mosquitto.conf, uncomment:
# allow_anonymous false
# password_file /mosquitto/config/passwd

# Restart mosquitto
docker-compose restart mosquitto

# Update .env with MQTT credentials
MQTT_USERNAME=admin
MQTT_PASSWORD=your-password
```

### SmartTub-MQTT

Bridge between SmartTub API and MQTT.

**Ports:**
- `8080` - Web UI + REST API

**Volumes:**
- `./smarttub-mqtt/config/` - YAML configuration
- `./smarttub-mqtt/log/` - Rotated logs

**Health Check:**
```bash
# Check container health
docker-compose ps

# View health status
curl http://localhost:8080/health
```

**Enable Web UI Authentication:**

Edit `.env`:
```bash
WEB_AUTH_ENABLED=true
WEB_BASIC_AUTH_USERNAME=admin
WEB_BASIC_AUTH_PASSWORD=secure-password
```

Restart:
```bash
docker-compose restart smarttub-mqtt
```

### OpenHAB (Optional)

Home automation platform for SmartTub integration.

**Ports:**
- `8181` - Web UI (mapped to avoid conflict)
- `8443` - HTTPS

**Volumes:**
- `./openhab/conf/` - Configuration files
- `./openhab/userdata/` - User data
- `./openhab/addons/` - Add-ons

**First Time Setup:**

1. Access OpenHAB: http://localhost:8181
2. Complete initial setup wizard
3. Install MQTT Binding:
   - Settings → Add-ons → Bindings
   - Search "MQTT"
   - Install "MQTT Binding"

4. Configure MQTT Broker Connection:
   - Settings → Things → Add Thing
   - Select "MQTT Binding"
   - Add "MQTT Broker"
   - Configure:
     - Host: `mosquitto`
     - Port: `1883`
     - Client ID: `openhab`

5. Import SmartTub Items:
   - Copy examples from `docs/automation-migration.md`
   - Create `items/smarttub.items`

## Discovery Mode

Run discovery to scan SmartTub capabilities and generate YAML:

```bash
# Enable discovery in .env
CHECK_SMARTTUB=true

# Restart SmartTub-MQTT
docker-compose restart smarttub-mqtt

# Watch discovery progress
docker-compose logs -f smarttub-mqtt

# Check discovery results
cat smarttub-mqtt/config/smarttub.yaml
```

After discovery completes, disable it:
```bash
CHECK_SMARTTUB=false
docker-compose restart smarttub-mqtt
```

## MQTT Topics

SmartTub-MQTT publishes to these topics (default base: `smarttub-mqtt`):

### State Topics (Read-Only)

```
smarttub-mqtt/{spa_id}/status/online          → true/false
smarttub-mqtt/{spa_id}/heater/state           → ON/OFF
smarttub-mqtt/{spa_id}/heater/current_temperature → 38.5
smarttub-mqtt/{spa_id}/heater/target_temperature  → 40.0
smarttub-mqtt/{spa_id}/pumps/CP/state         → OFF/LOW/HIGH
smarttub-mqtt/{spa_id}/lights/1/state         → ON/OFF
smarttub-mqtt/{spa_id}/lights/1/color         → #FF0000
```

### Command Topics (Write)

```
smarttub-mqtt/{spa_id}/heater/target_temperature_writetopic → 40
smarttub-mqtt/{spa_id}/pumps/CP/state_writetopic → HIGH
smarttub-mqtt/{spa_id}/lights/1/state_writetopic → ON
```

### Meta Topics

```
smarttub-mqtt/meta/errors         → Error tracking (JSON)
smarttub-mqtt/meta/discovery      → Discovery progress (JSON)
smarttub-mqtt/meta/mqtt           → MQTT connection status (JSON)
```

## Monitoring

### Container Status

```bash
# View running containers
docker-compose ps

# View resource usage
docker stats

# Check health
docker inspect smarttub-mqtt | grep -A 10 Health
```

### Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f smarttub-mqtt

# Last 100 lines
docker-compose logs --tail 100 smarttub-mqtt

# SmartTub-MQTT rotated logs
tail -f smarttub-mqtt/log/smarttub.log
```

### MQTT Topics

```bash
# Subscribe to all topics
docker-compose exec mosquitto mosquitto_sub -t 'smarttub-mqtt/#' -v

# Subscribe to errors
docker-compose exec mosquitto mosquitto_sub -t 'smarttub-mqtt/meta/errors' -v

# Test command
docker-compose exec mosquitto mosquitto_pub -t 'smarttub-mqtt/spa_abc123/heater/target_temperature_writetopic' -m '40'
```

## Troubleshooting

### SmartTub-MQTT won't start

**Check logs:**
```bash
docker-compose logs smarttub-mqtt
```

**Common issues:**
- Missing `SMARTTUB_EMAIL` or `SMARTTUB_PASSWORD` in `.env`
- Invalid credentials
- MQTT broker not accessible

**Verify environment:**
```bash
docker-compose exec smarttub-mqtt env | grep SMARTTUB
```

### MQTT connection failed

**Check Mosquitto:**
```bash
docker-compose logs mosquitto
docker-compose exec mosquitto mosquitto_sub -t '$SYS/#' -v
```

**Test connectivity:**
```bash
# From SmartTub-MQTT container
docker-compose exec smarttub-mqtt ping mosquitto
```

### OpenHAB can't connect to MQTT

**Verify network:**
```bash
docker network inspect smarttub-network
```

**All containers should be on `smarttub-network`.**

**Test MQTT from OpenHAB:**
```bash
docker-compose exec openhab ping mosquitto
```

### Discovery not working

**Enable DEBUG logging:**

Edit `.env`:
```bash
LOG_LEVEL=DEBUG
CHECK_SMARTTUB=true
```

Restart and check logs:
```bash
docker-compose restart smarttub-mqtt
docker-compose logs -f smarttub-mqtt | grep -i discovery
```

## Backup & Restore

### Backup

```bash
# Create backup directory
mkdir -p backups/$(date +%Y%m%d)

# Backup SmartTub config
cp -r smarttub-mqtt/config/ backups/$(date +%Y%m%d)/

# Backup OpenHAB config
cp -r openhab/conf/ backups/$(date +%Y%m%d)/

# Backup environment
cp .env backups/$(date +%Y%m%d)/
```

### Restore

```bash
# Stop services
docker-compose down

# Restore from backup
cp -r backups/20251030/config/ smarttub-mqtt/
cp -r backups/20251030/conf/ openhab/
cp backups/20251030/.env .

# Start services
docker-compose up -d
```

## Updates

### Update SmartTub-MQTT

```bash
# Pull latest image
docker pull smarttub-mqtt:latest

# Restart service
docker-compose up -d smarttub-mqtt
```

### Update All Services

```bash
# Pull latest images
docker-compose pull

# Recreate containers
docker-compose up -d
```

## Security Best Practices

1. **Use `.env` for secrets** - Never commit credentials to git
2. **Enable MQTT authentication** - Use `mosquitto_passwd`
3. **Enable Web UI auth** - Set `WEB_AUTH_ENABLED=true`
4. **Use strong passwords** - Minimum 16 characters
5. **Restrict network access** - Use firewall rules
6. **Keep images updated** - Regular `docker-compose pull`
7. **Review logs regularly** - Check for errors/warnings
8. **Backup configurations** - Automated backups recommended

## Advanced Configuration

### Custom Networks

```yaml
networks:
  smarttub-net:
    external: true
    name: my-existing-network
```

### Named Volumes

```yaml
volumes:
  smarttub-config:
  smarttub-log:

services:
  smarttub-mqtt:
    volumes:
      - smarttub-config:/config
      - smarttub-log:/log
```

### Resource Limits

```yaml
services:
  smarttub-mqtt:
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 512M
        reservations:
          cpus: '0.5'
          memory: 256M
```

## Support

- **Documentation**: [../docs/](../docs/)
- **Migration Guide**: [../docs/automation-migration.md](../docs/automation-migration.md)
- **GitHub Issues**: [Report Issue](https://github.com/your-org/smarttub-mqtt/issues)

## License

MIT License - See [LICENSE](../LICENSE)
