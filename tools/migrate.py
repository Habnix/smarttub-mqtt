#!/usr/bin/env python3
"""
Migration Tool for SmartTub-MQTT Configuration

Migrates old configuration format to new v1.0 format.
Validates and reports potential issues.
"""

import argparse
import sys
from pathlib import Path
from typing import Dict, Any, List, Tuple
import yaml
import shutil
from datetime import datetime


class MigrationReport:
    """Track migration changes and issues."""
    
    def __init__(self):
        self.changes: List[str] = []
        self.warnings: List[str] = []
        self.errors: List[str] = []
    
    def add_change(self, message: str):
        self.changes.append(message)
    
    def add_warning(self, message: str):
        self.warnings.append(message)
    
    def add_error(self, message: str):
        self.errors.append(message)
    
    def print_report(self):
        """Print migration report."""
        print("\n" + "=" * 70)
        print("MIGRATION REPORT")
        print("=" * 70)
        
        if self.changes:
            print("\n✅ Changes Applied:")
            for change in self.changes:
                print(f"  • {change}")
        
        if self.warnings:
            print("\n⚠️  Warnings:")
            for warning in self.warnings:
                print(f"  • {warning}")
        
        if self.errors:
            print("\n❌ Errors:")
            for error in self.errors:
                print(f"  • {error}")
        
        if not self.changes and not self.warnings and not self.errors:
            print("\n✅ No migration needed - configuration is up to date!")
        
        print("=" * 70 + "\n")
    
    def has_errors(self) -> bool:
        return len(self.errors) > 0


class ConfigMigrator:
    """Migrate configuration from old to new format."""
    
    # Renamed parameters mapping
    RENAMED_PARAMS = {
        ("logging", "max_size_mb"): ("logging", "log_max_size_mb"),
        ("logging", "max_files"): ("logging", "log_max_files"),
        ("logging", "dir"): ("logging", "log_dir"),
    }
    
    def __init__(self, report: MigrationReport):
        self.report = report
    
    def migrate_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Migrate configuration dictionary."""
        migrated = config.copy()
        
        # Migrate renamed parameters
        for old_path, new_path in self.RENAMED_PARAMS.items():
            self._migrate_parameter(migrated, old_path, new_path)
        
        # Ensure required sections exist
        self._ensure_sections(migrated)
        
        return migrated
    
    def _migrate_parameter(self, config: Dict[str, Any], old_path: Tuple[str, str], new_path: Tuple[str, str]):
        """Migrate a single parameter from old to new name."""
        section, old_key = old_path
        _, new_key = new_path
        
        if section not in config:
            return
        
        section_data = config[section]
        if not isinstance(section_data, dict):
            return
        
        if old_key in section_data:
            value = section_data.pop(old_key)
            section_data[new_key] = value
            self.report.add_change(f"Renamed {section}.{old_key} → {section}.{new_key}")
    
    def _ensure_sections(self, config: Dict[str, Any]):
        """Ensure all required sections exist with defaults."""
        required_sections = {
            "smarttub": {},
            "mqtt": {},
            "web": {},
            "logging": {},
        }
        
        for section, defaults in required_sections.items():
            if section not in config:
                config[section] = defaults
                self.report.add_change(f"Added missing section: {section}")


class EnvMigrator:
    """Migrate .env file to new format."""
    
    def __init__(self, report: MigrationReport):
        self.report = report
    
    def migrate_env(self, env_path: Path) -> Dict[str, str]:
        """Read and migrate .env file."""
        if not env_path.exists():
            self.report.add_warning(f".env file not found: {env_path}")
            return {}
        
        env_vars = {}
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                if '=' in line:
                    key, value = line.split('=', 1)
                    env_vars[key.strip()] = value.strip()
        
        return env_vars
    
    def validate_env(self, env_vars: Dict[str, str]):
        """Validate environment variables."""
        required = ['SMARTTUB_EMAIL']
        
        for var in required:
            if var not in env_vars or not env_vars[var]:
                self.report.add_error(f"Required environment variable missing: {var}")
        
        # Check for password or token
        has_password = 'SMARTTUB_PASSWORD' in env_vars and env_vars['SMARTTUB_PASSWORD']
        has_token = 'SMARTTUB_TOKEN' in env_vars and env_vars['SMARTTUB_TOKEN']
        
        if not has_password and not has_token:
            self.report.add_error("Either SMARTTUB_PASSWORD or SMARTTUB_TOKEN must be set")


def backup_file(file_path: Path) -> Path:
    """Create timestamped backup of file."""
    if not file_path.exists():
        return None
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = file_path.with_suffix(f".{timestamp}.bak")
    shutil.copy2(file_path, backup_path)
    return backup_path


def main():
    parser = argparse.ArgumentParser(
        description="Migrate SmartTub-MQTT configuration to v1.0 format"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("/config/smarttub.yaml"),
        help="Path to config file (default: /config/smarttub.yaml)"
    )
    parser.add_argument(
        "--env",
        type=Path,
        default=Path("/config/.env"),
        help="Path to .env file (default: /config/.env)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show changes without applying them"
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Don't create backup files"
    )
    
    args = parser.parse_args()
    
    print("SmartTub-MQTT Configuration Migration Tool")
    print("=" * 70)
    
    report = MigrationReport()
    
    # Migrate YAML config
    if args.config.exists():
        print(f"\n📄 Processing config: {args.config}")
        
        try:
            with open(args.config, 'r') as f:
                config = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            report.add_error(f"Failed to parse YAML: {e}")
            report.print_report()
            return 1
        
        migrator = ConfigMigrator(report)
        migrated_config = migrator.migrate_config(config)
        
        if not args.dry_run:
            # Backup original
            if not args.no_backup:
                backup_path = backup_file(args.config)
                if backup_path:
                    print(f"  ✅ Backup created: {backup_path}")
            
            # Write migrated config
            with open(args.config, 'w') as f:
                yaml.dump(migrated_config, f, default_flow_style=False, sort_keys=False)
            print(f"  ✅ Config migrated: {args.config}")
    else:
        report.add_warning(f"Config file not found: {args.config}")
    
    # Validate .env
    if args.env.exists():
        print(f"\n📄 Processing .env: {args.env}")
        
        env_migrator = EnvMigrator(report)
        env_vars = env_migrator.migrate_env(args.env)
        env_migrator.validate_env(env_vars)
        
        print(f"  ✅ Environment variables validated")
    else:
        report.add_warning(f".env file not found: {args.env}")
    
    # Print report
    report.print_report()
    
    if args.dry_run:
        print("DRY RUN: No changes were applied. Run without --dry-run to apply.")
        return 0
    
    if report.has_errors():
        print("\n❌ Migration completed with errors. Please fix the errors above.")
        return 1
    
    print("\n✅ Migration completed successfully!")
    print("\nNext steps:")
    print("  1. Review the changes above")
    print("  2. Restart SmartTub-MQTT:")
    print("     docker restart smarttub-mqtt")
    print("  3. Check logs for errors:")
    print("     docker logs smarttub-mqtt")
    print("  4. Verify MQTT topics:")
    print("     mosquitto_sub -t 'smarttub-mqtt/#' -v")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
