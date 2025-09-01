#!/usr/bin/env python3
"""
Constants for OMVA Voice Enrollment Skill

Copyright 2024 OMVA Team
Licensed under the Apache License, Version 2.0
"""

# Voice sample collection settings
DEFAULT_TARGET_SAMPLES = 3
MIN_AUDIO_DURATION = 3.0
MAX_AUDIO_DURATION = 10.0
DEFAULT_QUALITY_THRESHOLD = 0.7

# Name validation settings
MIN_NAME_LENGTH = 2
MAX_NAME_LENGTH = 50
NAME_PATTERN = r"^[a-zA-Z]([a-zA-Z\s\-\'])*[a-zA-Z]$"


# Enrollment states
class EnrollmentState:
    IDLE = "idle"
    CONFIRMATION = "confirmation"
    NAME_COLLECTION = "name_collection"
    SAMPLE_COLLECTION = "sample_collection"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


# Message bus events
class MessageBusEvents:
    # Outgoing events (to voice ID plugin)
    START_ENROLLMENT = "omva.voiceid.start_enrollment"
    COLLECT_SAMPLE = "omva.voiceid.collect_sample"
    STOP_SAMPLE_COLLECTION = "omva.voiceid.stop_sample_collection"
    SESSION_EXPIRED = "omva.voiceid.session_expired"
    ENROLL_USER = "ovos.voiceid.enroll_user"
    GET_USERS = "ovos.voiceid.list_users"
    DELETE_USER = "ovos.voiceid.remove_user"  # Updated to match plugin API
    UPDATE_USER = "ovos.voiceid.update_user"
    VERIFY_SPEAKERS = "ovos.voiceid.verify_speakers"
    GET_USER_INFO = "ovos.voiceid.get_user_info"
    GET_STATS = "ovos.voiceid.get_stats"

    # Incoming events (from voice ID plugin)
    SAMPLE_COLLECTED = "omva.voiceid.sample.collected"
    ENROLL_RESPONSE = "ovos.voiceid.enroll.response"
    USERS_RESPONSE = "ovos.voiceid.users.response"  # Updated to match plugin API docs
    REMOVE_RESPONSE = "ovos.voiceid.remove.response"
    UPDATE_RESPONSE = "ovos.voiceid.update.response"
    VERIFY_RESPONSE = "ovos.voiceid.verify.response"
    USER_INFO_RESPONSE = "ovos.voiceid.user_info.response"
    STATS_RESPONSE = "ovos.voiceid.stats.response"

    # Automatic identification events
    VOICE_IDENTIFIED = "ovos.voice.identified"
    VOICE_UNKNOWN = "ovos.voice.unknown"


# Audio quality thresholds
class AudioQuality:
    EXCELLENT = 0.9
    GOOD = 0.7
    ACCEPTABLE = 0.5
    POOR = 0.3


# Sample collection phrases for voice training
SAMPLE_PHRASES = [
    "The quick brown fox jumps over the lazy dog",
    "She sells seashells by the seashore",
    "How much wood would a woodchuck chuck if a woodchuck could chuck wood",
    "Peter Piper picked a peck of pickled peppers",
    "A proper copper coffee pot",
    "Red leather, yellow leather",
    "Toy boat, toy boat, toy boat",
    "Unique New York, unique New York",
    "Sally sells seashells down by the seashore",
    "The thirty-three thieves thought that they thrilled the throne throughout Thursday",
]


# Intent confidence thresholds
class IntentConfidence:
    HIGH = 0.8
    MEDIUM = 0.6
    LOW = 0.4
    FALLBACK_THRESHOLD = 0.6


# Skill metadata
SKILL_NAME = "omva-skill-voice-enrollment"
SKILL_AUTHOR = "OMVA Team"
SKILL_DESCRIPTION = (
    "Natural voice interface for voice enrollment with semantic intent recognition"
)


# Error codes
class ErrorCodes:
    AUDIO_QUALITY_POOR = "audio_quality_poor"
    PROCESSING_FAILED = "processing_failed"
    NETWORK_ERROR = "network_error"
    PLUGIN_UNAVAILABLE = "plugin_unavailable"
    INVALID_NAME = "invalid_name"
    USER_EXISTS = "user_exists"
    SAMPLE_COUNT_INSUFFICIENT = "sample_count_insufficient"
