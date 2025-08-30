#!/usr/bin/env python3
"""
Version management script for OMVA Voice Enrollment Skill
Supports bumping major, minor, build, or alpha versions
"""

import argparse
import re
from pathlib import Path


def get_current_version():
    """Get current version from version.py"""
    base_dir = Path(__file__).parent.parent
    version_file = base_dir / "version.py"
    
    with open(version_file) as f:
        content = f.read()
        
    major = re.search(r'VERSION_MAJOR = (\d+)', content)
    minor = re.search(r'VERSION_MINOR = (\d+)', content)
    build = re.search(r'VERSION_BUILD = (\d+)', content)
    alpha = re.search(r'VERSION_ALPHA = (\d+)', content)
    
    if not all([major, minor, build, alpha]):
        raise ValueError("Invalid version.py format")
        
    return {
        'major': int(major.group(1)),
        'minor': int(minor.group(1)), 
        'build': int(build.group(1)),
        'alpha': int(alpha.group(1))
    }


def update_version(version_type):
    """Update version in version.py"""
    base_dir = Path(__file__).parent.parent
    version_file = base_dir / "version.py"
    
    current = get_current_version()
    
    # Calculate new version
    if version_type == 'major':
        current['major'] += 1
        current['minor'] = 0
        current['build'] = 0
        current['alpha'] = 0
    elif version_type == 'minor':
        current['minor'] += 1
        current['build'] = 0
        current['alpha'] = 0
    elif version_type == 'build':
        current['build'] += 1
        current['alpha'] = 0
    elif version_type == 'alpha':
        current['alpha'] += 1
    else:
        raise ValueError(f"Invalid version type: {version_type}")
    
    # Update version.py file
    new_content = f"""VERSION_MAJOR = {current['major']}
VERSION_MINOR = {current['minor']}
VERSION_BUILD = {current['build']}
VERSION_ALPHA = {current['alpha']}
# END_VERSION_BLOCK"""

    with open(version_file, 'w') as f:
        f.write(new_content)
    
    # Format version string
    version_str = f"{current['major']}.{current['minor']}.{current['build']}"
    if current['alpha'] > 0:
        version_str += f"a{current['alpha']}"
        
    return version_str


def main():
    parser = argparse.ArgumentParser(description='Bump version for OMVA Voice Enrollment Skill')
    parser.add_argument('type', choices=['major', 'minor', 'build', 'alpha'],
                        help='Version component to bump')
    parser.add_argument('--dry-run', action='store_true', 
                        help='Show what would be changed without modifying files')
    
    args = parser.parse_args()
    
    try:
        current = get_current_version()
        current_str = f"{current['major']}.{current['minor']}.{current['build']}"
        if current['alpha'] > 0:
            current_str += f"a{current['alpha']}"
            
        print(f"Current version: {current_str}")
        
        if not args.dry_run:
            new_version = update_version(args.type)
            print(f"Updated version: {new_version}")
        else:
            # Show what would change
            test_current = current.copy()
            if args.type == 'major':
                test_current['major'] += 1
                test_current['minor'] = 0
                test_current['build'] = 0
                test_current['alpha'] = 0
            elif args.type == 'minor':
                test_current['minor'] += 1
                test_current['build'] = 0
                test_current['alpha'] = 0
            elif args.type == 'build':
                test_current['build'] += 1
                test_current['alpha'] = 0
            elif args.type == 'alpha':
                test_current['alpha'] += 1
                
            new_str = f"{test_current['major']}.{test_current['minor']}.{test_current['build']}"
            if test_current['alpha'] > 0:
                new_str += f"a{test_current['alpha']}"
                
            print(f"Would update to: {new_str}")
            
    except Exception as e:
        print(f"Error: {e}")
        return 1
        
    return 0


if __name__ == "__main__":
    exit(main())