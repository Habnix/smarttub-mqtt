# Web UI Configuration

## Overview

smarttub-mqtt includes an optional web-based user interface for monitoring and controlling your SmartTub whirlpool. The Web UI is built with FastAPI, Bootstrap, and HTMX for dynamic updates.

## Features

- **Real-time monitoring**: View current spa state, water temperature, heater status
- **Component control**: Adjust temperature, pumps, lights
- **Capability discovery**: See available features dynamically
- **REST API**: Full REST API for programmatic access
- **Optional Basic Authentication**: Secure access with HTTP Basic Auth

## Configuration

### Enable/Disable Web UI

Control whether the Web UI starts:

```yaml
# config/smarttub.yaml
web:
  enabled: true  # Set to false to disable Web UI
  host: 0.0.0.0
  port: 8080
```

Or via environment variable:

```bash
# /config/.env
WEB_ENABLED=true
WEB_HOST=0.0.0.0
WEB_PORT=8080
```

### Basic Authentication

Protect the Web UI with HTTP Basic Authentication:

```yaml
# config/smarttub.yaml
web:
  enabled: true
  auth_enabled: true
  basic_auth_username: admin
  basic_auth_password: your_secure_password
```

Or via environment variables:

```bash
# /config/.env
WEB_AUTH_ENABLED=true
WEB_BASIC_AUTH_USERNAME=admin
WEB_BASIC_AUTH_PASSWORD=your_secure_password
```

**Important**: 
- Use strong passwords in production
- The `/health` endpoint is always accessible without authentication
- All other routes require authentication when `auth_enabled=true`

## Access

Once running, access the Web UI at:

- **Without Auth**: `http://localhost:8080`
- **With Auth**: Browser will prompt for username/password

## Pages

### Overview Page (`/`)

Main dashboard showing:
- Spa system status
- Current water temperature
- Heater status and target temperature
- Pump states
- Light states and colors
- Last update timestamp

### Controls Page (`/controls`)

Interactive controls for:
- Setting target temperature
- Changing heater modes
- Controlling pumps (on/off, speed)
- Adjusting lights (on/off, brightness, color, mode)

### API Endpoints

All endpoints return JSON:

#### State Endpoints

- `GET /api/state` - Current spa state snapshot
- `GET /api/capabilities` - Spa capabilities and supported features
- `GET /health` - Health check (always accessible)

#### Command Endpoints

- `POST /api/commands/set_temperature` - Set target temperature
  ```json
  {"temperature": 38.5}
  ```

- `POST /api/commands/set_heat_mode` - Set heating mode
  ```json
  {"mode": "auto"}
  ```

- `POST /api/commands/set_pump_state` - Control pump
  ```json
  {"state": "on"}
  ```

- `POST /api/commands/set_light_state` - Control light
  ```json
  {"state": "on"}
  ```

- `POST /api/commands/set_light_color` - Set light color
  ```json
  {"color": "#FF0000"}
  ```

- `POST /api/commands/set_light_brightness` - Set brightness
  ```json
  {"brightness": 75}
  ```

- `GET /api/commands/history` - Command history

## Security Best Practices

### Enable Authentication

Always enable Basic Auth in production:

```bash
WEB_AUTH_ENABLED=true
WEB_BASIC_AUTH_USERNAME=admin
WEB_BASIC_AUTH_PASSWORD=$(openssl rand -base64 24)
```

### Use HTTPS

For production, place the Web UI behind a reverse proxy with HTTPS:

```nginx
# Example nginx config
server {
    listen 443 ssl;
    server_name smarttub.example.com;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    location / {
        proxy_pass http://localhost:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### Restrict Access

Bind to localhost only if using reverse proxy:

```yaml
web:
  host: 127.0.0.1  # Only accessible via reverse proxy
  port: 8080
```

## Disable Web UI

If you only need MQTT integration, disable the Web UI:

```yaml
web:
  enabled: false
```

Or:

```bash
WEB_ENABLED=false
```

This saves resources and reduces attack surface.

## Troubleshooting

### Web UI not starting

Check logs:
```
LOG_LEVEL=DEBUG
```

Common issues:
- Port already in use: Change `WEB_PORT`
- Missing dependencies: Install FastAPI, Jinja2, uvicorn
- Permission denied: Check file permissions for templates/static

### Authentication not working

- Verify credentials are set in config
- Check `WEB_AUTH_ENABLED=true`
- Clear browser cache/credentials
- Check logs for authentication errors

### Template errors

Ensure templates directory exists:
```bash
ls -la src/web/templates/
```

Should contain:
- `overview.html`
- `controls.html`
- `error.html` (if exists)

## Development

### Auto-reload

For development, uvicorn supports auto-reload:

```python
uvicorn src.web.app:app --reload --host 0.0.0.0 --port 8080
```

### Custom Templates

Template directory: `src/web/templates/`

Templates use Jinja2 with context:
- `state`: Current spa state
- `capabilities`: Spa capabilities
- `config`: Application configuration

## Dependencies

Web UI requires:
- FastAPI
- Jinja2  
- uvicorn
- python-multipart (for forms)

Install with:
```bash
pip install fastapi jinja2 uvicorn python-multipart
```

Or use the full requirements:
```bash
pip install -r requirements.txt
```

