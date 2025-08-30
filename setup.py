#!/usr/bin/env python3
# Copyright 2024 OMVA Team
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from os import getenv, path, walk

from setuptools import setup

SKILL_NAME = "omva-skill-voice-enrollment"
SKILL_PKG = SKILL_NAME.replace("-", "_")
# skill_id=package_name:SkillClass
PLUGIN_ENTRY_POINT = f"{SKILL_NAME}.openvoiceos={SKILL_PKG}:OMVAVoiceEnrollmentSkill"
BASE_PATH = path.abspath(path.dirname(__file__))


def get_version():
    """Find the version of the package"""
    version = None
    version_file = path.join(BASE_PATH, "version.py")
    major, minor, build, alpha = (None, None, None, None)
    with open(version_file, encoding="utf-8") as f:
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


def package_files(directory):
    paths = []
    for path_name, directories, filenames in walk(directory):
        for filename in filenames:
            paths.append(path.join("..", path_name, filename))
    return paths


def required(requirements_file):
    """Read requirements file and remove comments and empty lines."""
    with open(path.join(BASE_PATH, requirements_file), "r", encoding="utf-8") as f:
        requirements = f.read().splitlines()
        if "MYCROFT_LOOSE_REQUIREMENTS" in getenv("", ""):
            print("USING LOOSE REQUIREMENTS!")
            requirements = [
                r.replace("==", ">=").replace("~=", ">=") for r in requirements
            ]
        return [pkg for pkg in requirements if pkg.strip() and not pkg.startswith("#")]


with open("README.md", "r", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name=SKILL_NAME,
    version=get_version(),
    description="Natural voice interface for voice enrollment with semantic intent recognition",
    long_description=(
        "A plugin for voice enrollment with semantic intent recognition."
        " This skill allows users to enroll their voice for personalized interactions."
        " This allows for a more tailored and effective user experience."
    ),
    url="https://github.com/ecosphereplus/omva-skill-voice-enrollment",
    author="OMVA Team",
    author_email="contact@omva.ai",
    license="Apache-2.0",
    packages=["omva_skill_voice_enrollment"],
    install_requires=required("requirements.txt"),
    package_data={SKILL_PKG: package_files(f"{SKILL_PKG}")},
    include_package_data=True,
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: OpenVoiceOS",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Multimedia :: Sound/Audio :: Speech",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
    keywords="ovos skill voice enrollment biometric recognition speechbrain",
    zip_safe=True,
    entry_points={"ovos.plugin.skill": PLUGIN_ENTRY_POINT},
)
