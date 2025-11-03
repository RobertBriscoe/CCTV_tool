#!/usr/bin/env python3
"""
Script to remove hardcoded secrets from camera_config.json
Creates a new file with only non-sensitive camera metadata
"""

import json
from pathlib import Path

def clean_camera_config():
    """Remove secrets from camera_config.json"""

    # Load the original file
    config_file = Path("camera_config.json")
    with open(config_file, 'r') as f:
        config = json.load(f)

    # Create cleaned version with only camera metadata
    cleaned = {
        "cameras": {}
    }

    # Process cameras - remove username and password
    if "cctv_cameras" in config:
        for camera_id, camera_data in config["cctv_cameras"].items():
            cleaned["cameras"][camera_id] = {
                "name": camera_data.get("name", ""),
                "ip": camera_data.get("ip", ""),
                "reboot_url": camera_data.get("reboot_url", "/api/reboot"),
                "snapshot_url": camera_data.get("snapshot_url", "/api/snapshot"),
                # Remove username and password - will use defaults from .env
            }

    # Save cleaned version
    with open("camera_config.json", 'w') as f:
        json.dump(cleaned, f, indent=4)

    print(f"✓ Cleaned camera_config.json")
    print(f"✓ Removed all hardcoded credentials")
    print(f"✓ Kept {len(cleaned['cameras'])} camera entries")
    print("\nNOTE: All secrets are now in .env file")
    print("      Camera credentials use CAMERA_DEFAULT_USERNAME and CAMERA_DEFAULT_PASSWORD")

if __name__ == "__main__":
    clean_camera_config()
