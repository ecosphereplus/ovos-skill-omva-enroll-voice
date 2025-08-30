#!/usr/bin/env python3
"""
Prepare skill for release to skillstore by updating version branch
"""

import json
from os.path import join, dirname


def get_version():
    """Find the version of the package"""
    base_dir = dirname(dirname(__file__))
    version_file = join(base_dir, "version.py")
    major, minor, build, alpha = (None, None, None, None)
    
    with open(version_file) as f:
        for line in f:
            if "VERSION_MAJOR" in line:
                major = line.split("=")[1].strip()
            elif "VERSION_MINOR" in line:
                minor = line.split("=")[1].strip()
            elif "VERSION_BUILD" in line:
                build = line.split("=")[1].strip()
            elif "VERSION_ALPHA" in line:
                alpha = line.split("=")[1].strip()

            if (major and minor and build and alpha) or "# END_VERSION_BLOCK" in line:
                break
    
    version = f"{major}.{minor}.{build}"
    if alpha and int(alpha) > 0:
        version += f"a{alpha}"
    return version


def prepare_release():
    """Update skill.json for release"""
    base_dir = dirname(dirname(__file__))
    jsonf = join(base_dir, "skill.json")
    
    version = get_version()
    print(f"Preparing release for version {version}")

    with open(jsonf) as f:
        data = json.load(f)

    # Set release branch
    data["branch"] = f"v{version}"
    
    print(f"Updated skill.json branch to: v{version}")

    with open(jsonf, "w") as f:
        json.dump(data, f, indent=4)
        
    print("Release preparation complete!")


if __name__ == "__main__":
    prepare_release()