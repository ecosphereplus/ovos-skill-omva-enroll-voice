#!/usr/bin/env python3
"""
Development utilities for OMVA Voice Enrollment Skill
Combines multiple development tasks in one convenient script
"""

import argparse
import subprocess
import sys
from pathlib import Path
import json
import os


def run_validation():
    """Run the skill validation"""
    print("Running skill validation...")
    
    base_dir = Path(__file__).parent.parent
    validate_script = base_dir / "validate.py"
    enhanced_validate = base_dir / "scripts" / "validate_skill.py"
    
    # Run basic validation
    if validate_script.exists():
        result = subprocess.run([sys.executable, str(validate_script)], 
                               cwd=base_dir, capture_output=True, text=True)
        if result.returncode == 0:
            print("PASS Basic validation passed")
        else:
            print("FAIL Basic validation failed")
            print(result.stdout)
            return False
    
    # Run enhanced validation  
    if enhanced_validate.exists():
        result = subprocess.run([sys.executable, str(enhanced_validate)], 
                               cwd=base_dir, capture_output=True, text=True)
        if result.returncode == 0:
            print("PASS Enhanced validation passed")
        else:
            print("FAIL Enhanced validation failed")
            print(result.stdout)
            return False
    
    return True


def run_tests():
    """Run unit tests if they exist"""
    print("Running tests...")
    
    base_dir = Path(__file__).parent.parent
    test_dir = base_dir / "test"
    
    if test_dir.exists() and any(test_dir.glob("test_*.py")):
        result = subprocess.run([sys.executable, "-m", "pytest", str(test_dir), "-v"],
                               cwd=base_dir, capture_output=True, text=True)
        if result.returncode == 0:
            print("PASS Tests passed")
            return True
        else:
            print("FAIL Tests failed")
            print(result.stdout)
            return False
    else:
        print("INFO No tests found")
        return True


def lint_code():
    """Run code linting"""
    print("Running code linting...")
    
    base_dir = Path(__file__).parent.parent
    init_file = base_dir / "__init__.py"
    
    # Try flake8 first
    try:
        result = subprocess.run(["flake8", str(init_file), "--max-line-length=120"],
                               capture_output=True, text=True)
        if result.returncode == 0:
            print("PASS flake8 linting passed")
        else:
            print("WARN flake8 found issues:")
            print(result.stdout)
    except FileNotFoundError:
        print("INFO flake8 not available")
    
    # Try pylint
    try:
        result = subprocess.run(["pylint", str(init_file), "--disable=missing-docstring"],
                               capture_output=True, text=True)
        if result.returncode == 0:
            print("PASS pylint passed")
        else:
            print("WARN pylint found issues (non-blocking)")
    except FileNotFoundError:
        print("INFO pylint not available")
    
    return True


def check_dependencies():
    """Check if all dependencies are available"""
    print("Checking dependencies...")
    
    base_dir = Path(__file__).parent.parent
    requirements_file = base_dir / "requirements.txt"
    
    if not requirements_file.exists():
        print("✗ requirements.txt not found")
        return False
    
    with open(requirements_file) as f:
        deps = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    
    missing_deps = []
    for dep in deps:
        try:
            # Extract package name (remove version constraints)
            pkg_name = dep.split(">=")[0].split("==")[0].split("~=")[0].split("<")[0].split(">")[0]
            __import__(pkg_name.replace("-", "_"))
            print(f"PASS {pkg_name}")
        except ImportError:
            missing_deps.append(pkg_name)
            print(f"FAIL {pkg_name}")
    
    if missing_deps:
        print(f"\nMissing dependencies: {', '.join(missing_deps)}")
        print("Run: pip install -r requirements.txt")
        return False
    
    print("PASS All dependencies available")
    return True


def package_info():
    """Show package information"""
    print("Package Information:")
    print("=" * 50)
    
    base_dir = Path(__file__).parent.parent
    
    # Version info
    version_file = base_dir / "version.py"
    if version_file.exists():
        with open(version_file) as f:
            content = f.read()
        
        import re
        major = re.search(r'VERSION_MAJOR = (\d+)', content)
        minor = re.search(r'VERSION_MINOR = (\d+)', content)
        build = re.search(r'VERSION_BUILD = (\d+)', content)
        alpha = re.search(r'VERSION_ALPHA = (\d+)', content)
        
        if all([major, minor, build, alpha]):
            version = f"{major.group(1)}.{minor.group(1)}.{build.group(1)}"
            if int(alpha.group(1)) > 0:
                version += f"a{alpha.group(1)}"
            print(f"Version: {version}")
        else:
            print("Version: Unable to parse")
    
    # Skill info
    skill_json = base_dir / "skill.json"
    if skill_json.exists():
        with open(skill_json) as f:
            data = json.load(f)
        print(f"Skill Name: {data.get('skillname', 'N/A')}")
        print(f"Title: {data.get('title', 'N/A')}")
        print(f"Description: {data.get('description', 'N/A')[:100]}...")
        print(f"Examples: {len(data.get('examples', []))}")
    
    # File counts
    locale_dir = base_dir / "locale" / "en-us"
    if locale_dir.exists():
        dialog_count = len(list((locale_dir / "dialog").glob("*.dialog"))) if (locale_dir / "dialog").exists() else 0
        vocab_count = len(list((locale_dir / "vocab").glob("*.*"))) if (locale_dir / "vocab").exists() else 0
        print(f"Dialog files: {dialog_count}")
        print(f"Vocab files: {vocab_count}")


def main():
    parser = argparse.ArgumentParser(description='OMVA Voice Enrollment Skill Development Utilities')
    parser.add_argument('command', choices=[
        'validate', 'test', 'lint', 'deps', 'info', 'all'
    ], help='Development command to run')
    
    args = parser.parse_args()
    
    if args.command == 'validate':
        return 0 if run_validation() else 1
    elif args.command == 'test':
        return 0 if run_tests() else 1
    elif args.command == 'lint':
        return 0 if lint_code() else 1
    elif args.command == 'deps':
        return 0 if check_dependencies() else 1
    elif args.command == 'info':
        package_info()
        return 0
    elif args.command == 'all':
        print("Running all development checks...")
        results = []
        results.append(run_validation())
        results.append(run_tests())
        results.append(lint_code())
        results.append(check_dependencies())
        
        print("\n" + "=" * 50)
        if all(results):
            print("PASS All development checks passed!")
        else:
            print("FAIL Some development checks failed")
            
        package_info()
        return 0 if all(results) else 1


if __name__ == "__main__":
    exit(main())