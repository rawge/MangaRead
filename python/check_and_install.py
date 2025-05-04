import sys
import subprocess
import importlib.metadata
from time import sleep

def is_package_installed(package_spec):
    package_name = package_spec.split('==')[0]
    try:
        version = importlib.metadata.version(package_name)
        print(f"[✓] {package_name} already installed (version {version})")
        return True
    except importlib.metadata.PackageNotFoundError:
        return False
    except Exception as e:
        print(f"[!] Error checking {package_name}: {str(e)}")
        return False

def install_package(package_spec):
    print(f"[~] Installing {package_spec}...")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", package_spec],
            check=True,
            capture_output=True,
            text=True
        )
        
        if "Successfully installed" in result.stdout:
            print(f"[✓] {package_spec} installed successfully")
            return True
        return False
    except subprocess.CalledProcessError as e:
        print(f"[X] Install failed: {e.stderr}")
        return False

def main():
    print("\n=== Python 3.13 Dependencies Installation ===")
    required_packages = [
        "selenium==4.18.1",
        "requests==2.31.0",
        "webdriver-manager==4.0.1",
        "colorama==0.4.6",
        "pycryptodome==3.22.0"
    ]
    
    for package in required_packages:
        if not is_package_installed(package):
            if not install_package(package):
                print(f"[X] Critical error installing {package}")
                input("\nPress Enter to exit...")
                sys.exit(1)
    
    print("\n[✓] All dependencies installed successfully!")
    input("\nPress Enter to exit...")

if __name__ == "__main__":
    main()
