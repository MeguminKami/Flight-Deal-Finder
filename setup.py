#!/usr/bin/env python3
'''
Quick setup script for Flight Deal Finder
'''
import subprocess
import sys
from pathlib import Path


def main():
    print("=" * 70)
    print("Flight Deal Finder - Setup")
    print("=" * 70)

    # Check Python version
    if sys.version_info < (3, 11):
        print("❌ Error: Python 3.11 or higher required")
        print(f"   Current version: {sys.version}")
        sys.exit(1)

    print(f"✓ Python {sys.version_info.major}.{sys.version_info.minor} detected")

    # Install dependencies
    print("\nInstalling dependencies...")
    try:
        subprocess.check_call([
            sys.executable, "-m", "pip", "install", "-r", "requirements.txt"
        ])
        print("✓ Dependencies installed")
    except subprocess.CalledProcessError:
        print("❌ Failed to install dependencies")
        sys.exit(1)

    # Check for .env file
    env_file = Path(".env")
    if not env_file.exists():
        print("\n⚠️  .env file not found")
        print("   Creating from .env.example...")

        example_file = Path(".env.example")
        if example_file.exists():
            env_file.write_text(example_file.read_text())
            print("✓ Created .env file")
            print("\n⚠️  IMPORTANT: Edit .env and add your Travelpayouts API token!")
            print("   Get your token from: https://www.travelpayouts.com/developers/api")
        else:
            print("❌ .env.example not found")
            sys.exit(1)
    else:
        print("\n✓ .env file exists")

    # Validate airports.json
    print("\nValidating airport data...")
    airports_file = Path("airports.json")
    if airports_file.exists():
        print("✓ airports.json found")
    else:
        print("❌ airports.json not found")
        sys.exit(1)

    print("\n" + "=" * 70)
    print("Setup complete!")
    print("=" * 70)
    print("\nNext steps:")
    print("1. Edit .env and add your TRAVELPAYOUTS_TOKEN")
    print("2. Run: python app.py")
    print("3. Open: http://localhost:8080")
    print("\nHappy flight hunting! ✈️")


if __name__ == '__main__':
    main()
