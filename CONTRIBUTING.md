# Contribution Guidelines

Thank you for your interest in contributing to SmartTub-MQTT!

## Development Setup

### Prerequisites

- Python 3.11+
- Docker (for testing)
- Git

### Local Setup

```bash
# Clone repository
git clone https://github.com/your-org/smarttub-mqtt.git
cd smarttub-mqtt

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -e .
pip install -r requirements-dev.txt

# Run tests
pytest
```

## Code Quality

### Before Committing

Run these checks locally:

```bash
# Linting
ruff check .
ruff format .

# Type checking
mypy src/ --ignore-missing-imports

# Tests
pytest --cov=src

# All checks
./scripts/check.sh  # if available
```

### CI Pipeline

All pull requests must pass:
- ✅ Ruff linting & formatting
- ✅ MyPy type checking (warnings allowed)
- ✅ Pytest (all tests passing)
- ✅ Coverage > 70% (goal)
- ✅ Docker build successful
- ✅ Security scans (Bandit, Safety)

## Pull Request Process

1. **Fork** the repository
2. **Create** a feature branch: `git checkout -b feature/amazing-feature`
3. **Commit** your changes: `git commit -m 'Add amazing feature'`
4. **Push** to branch: `git push origin feature/amazing-feature`
5. **Open** a Pull Request

### PR Guidelines

- Clear description of changes
- Reference related issues
- Update documentation if needed
- Add tests for new features
- Follow existing code style
- Keep commits atomic and well-described

## Testing

### Running Tests

```bash
# All tests
pytest

# Specific test file
pytest tests/unit/test_config_loader.py

# With coverage
pytest --cov=src --cov-report=html

# Verbose output
pytest -vv

# Fast fail
pytest -x
```

### Writing Tests

- Unit tests in `tests/unit/`
- Integration tests in `tests/integration/`
- Contract tests in `tests/contract/`
- Follow existing test patterns
- Aim for >70% coverage
- Test error cases

Example test:

```python
import pytest
from src.core.config_loader import ConfigLoader

def test_config_loader_missing_email():
    """Test that missing email raises ValueError."""
    with pytest.raises(ValueError, match="SMARTTUB_EMAIL"):
        ConfigLoader.from_env({})
```

## Code Style

### Python

- Follow PEP 8
- Use Ruff for linting/formatting
- Type hints preferred (but optional)
- Docstrings for public functions
- Max line length: 88 (Black compatible)

Example:

```python
def process_temperature(value: float, unit: str = "celsius") -> float:
    """
    Process temperature value and convert if needed.
    
    Args:
        value: Temperature value
        unit: Temperature unit (celsius/fahrenheit)
        
    Returns:
        Processed temperature in celsius
        
    Raises:
        ValueError: If unit is invalid
    """
    if unit == "fahrenheit":
        return (value - 32) * 5/9
    return value
```

## Documentation

Update documentation when:
- Adding new features
- Changing configuration
- Modifying MQTT topics
- Updating deployment process

Documentation files:
- `README.md` - Main documentation
- `docs/configuration.md` - Config reference
- `docs/automation-migration.md` - Automation guides
- `deploy/README.md` - Deployment guide

## Versioning

We use [Semantic Versioning](https://semver.org/):

- **MAJOR**: Breaking changes
- **MINOR**: New features (backward compatible)
- **PATCH**: Bug fixes

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

## Questions?

- Open an issue for bugs/features
- Discussions for questions
- Security issues: See SECURITY.md

## Code of Conduct

- Be respectful and inclusive
- Constructive feedback
- Focus on collaboration
- Follow GitHub Community Guidelines
