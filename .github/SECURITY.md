# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.4.x   | :white_check_mark: (from the 0.4.0 release) |
| 0.3.x   | :white_check_mark: |
| < 0.3   | :x:                |

## Reporting a Vulnerability

**Please do NOT report security vulnerabilities through public issues.**

On GitHub, open **Security → Advisories → Report a vulnerability** if private
vulnerability reporting is enabled. If that button is unavailable, open an
issue asking the maintainer for a private reporting channel, without including
vulnerability details. The private development Gitea instance is not a public
support channel.

### What to Include

1. **Description**: Clear description of the vulnerability
2. **Impact**: Potential impact and attack scenario
3. **Reproduction**: Step-by-step instructions to reproduce
4. **Suggested Fix**: If you have a proposed solution
5. **Disclosure Timeline**: Your expectations for disclosure

### Response Timeline

- **Acknowledgment**: Within 24 hours
- **Initial Assessment**: Within 7 days
- **Fix Timeline**: Depends on severity
  - Critical: 7 days
  - High: 30 days
  - Medium: 90 days
  - Low: Next release

## Security Best Practices

### For Developers

1. **Never commit sensitive data**
   ```bash
   # Always check before committing
   git diff --staged
   ```

2. **Use strong credentials**
   ```bash
   # Generate strong passwords
   openssl rand -base64 32
   ```

3. **Review dependencies**
   ```bash
   # Check for vulnerabilities
   pip-audit
   ```

### For Deployers

1. **Enable authentication**
   ```bash
   WEB_AUTH_ENABLED=true
   WEB_AUTH_PASSWORD=$(openssl rand -base64 32)
   ```

2. **Use TLS for MQTT**
   ```bash
   MQTT_BROKER_URL=mqtts://broker:8883
   ```

3. **Restrict file permissions**
   ```bash
   chmod 600 /config/.env
   ```

4. **Use reverse proxy for HTTPS**
   - nginx with Let's Encrypt
   - Traefik with automatic TLS

## Security Features

- ✅ HTTP Basic Authentication (optional)
- ✅ Constant-time password comparison
- ✅ No hardcoded credentials
- ✅ Secure credential storage (.env)
- ✅ TLS support for MQTT
- ✅ Sanitized logging (no credentials)

## Known Limitations

- HTTP only (use reverse proxy for HTTPS)
- No built-in rate limiting (use reverse proxy)
- No built-in audit logging (command logs available)

## Security Contacts

Use the reporting process above for security-related questions.

## Acknowledgments

We thank the security researchers who help keep our users safe:

- TBD

---

Last Updated: 2026-10-07
