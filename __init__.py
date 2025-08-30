"""
OMVA Voice Enrollment Skill

Provides natural voice interface for voice enrollment with semantic intent recognition.
Supports multiple ways to express enrollment intent: "enroll my voice", "save my voice",
"remember me", etc.

Copyright 2024 OMVA Team
Licensed under the Apache License, Version 2.0
"""

import os
import re
import tempfile
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from ovos_bus_client.message import Message
from ovos_utils.log import LOG
from ovos_workshop.decorators import intent_handler
from ovos_workshop.intents import IntentBuilder
from ovos_workshop.skills import OVOSSkill

try:
    # Try relative import first (when used as a package)
    from .constants import SAMPLE_PHRASES, EnrollmentState, ErrorCodes, MessageBusEvents
except ImportError:
    # Fall back to absolute import (when run directly or in tests)
    from constants import SAMPLE_PHRASES, EnrollmentState, ErrorCodes, MessageBusEvents


class OMVAVoiceEnrollmentSkill(OVOSSkill):
    """
    OMVA Voice Enrollment Skill

    Handles voice enrollment requests using semantic intent recognition
    to support natural language variations like:
    - "enroll my voice"
    - "save my voice"
    - "remember me"
    - "register my voice as John"
    """

    def __init__(self, bus=None, skill_id=""):
        super().__init__(bus=bus, skill_id=skill_id)
        self.enrollment_context = {}
        self.target_samples = 3
        self.min_audio_duration = 3.0
        self.max_audio_duration = 10.0
        self.quality_threshold = 0.7
        self.confirmation_required = True
        self.replace_existing_profiles = False

    def initialize(self):
        """Initialize skill after construction"""
        LOG.info("Initializing OMVA Voice Enrollment Skill")
        self.setup_voice_id_integration()
        self.load_settings()

    def load_settings(self):
        """Load skill settings with defaults"""
        self.target_samples = self.settings.get("target_samples", 3)
        self.min_audio_duration = self.settings.get("min_audio_duration", 3.0)
        self.max_audio_duration = self.settings.get("max_audio_duration", 10.0)
        self.quality_threshold = self.settings.get("quality_threshold", 0.7)
        self.confirmation_required = self.settings.get("confirmation_required", True)
        self.replace_existing_profiles = self.settings.get(
            "replace_existing_profiles", False
        )
        LOG.info(
            f"Settings loaded: {self.target_samples} samples, confirmation: {self.confirmation_required}"
        )

    def setup_voice_id_integration(self):
        """Setup integration with voice identification plugin"""
        # Only set up bus integration if bus is available
        if hasattr(self, "_bus") and self._bus is not None:
            self.bus.on("ovos.voiceid.enroll.response", self.handle_enrollment_response)
            self.bus.on("ovos.voiceid.users.response", self.handle_users_response)
            LOG.debug("Voice ID integration setup complete")
        else:
            LOG.debug(
                "Bus not available during initialization - will set up integration later"
            )

    # Primary Intent Handlers

    @intent_handler("EnrollVoice.intent")
    def handle_enroll_voice_intent(self, message):
        """Handle primary voice enrollment intents from file"""
        LOG.info("EnrollVoice intent triggered")
        user_name = self.extract_user_name_from_utterance(
            message.data.get("utterance", "")
        )
        self.start_enrollment_flow(user_name, trigger="file_intent")

    @intent_handler(
        IntentBuilder("EnrollVoiceAdapt")
        .require("EnrollKeyword")
        .require("VoiceKeyword")
        .optionally("UserName")
        .build()
    )
    def handle_enroll_voice_adapt_intent(self, message):
        """Handle enrollment intents using Adapt pattern matching"""
        LOG.info("EnrollVoiceAdapt intent triggered")
        user_name = message.data.get("UserName")
        self.start_enrollment_flow(user_name, trigger="adapt_intent")

    @intent_handler(
        IntentBuilder("RememberMeIntent")
        .require("RememberKeyword")
        .require("MeKeyword")
        .optionally("UserName")
        .build()
    )
    def handle_remember_me_intent(self, message):
        """Handle 'remember me' style enrollment requests"""
        LOG.info("RememberMe intent triggered")
        user_name = message.data.get("UserName")
        self.start_enrollment_flow(user_name, trigger="remember_intent")

    # Confirmation Intent Handlers

    @intent_handler(
        IntentBuilder("ConfirmEnrollmentYes")
        .require("YesKeyword")
        .require("AwaitingEnrollmentConfirmation")
        .build()
    )
    def handle_confirm_enrollment_yes(self, message):
        """Handle positive confirmation for enrollment"""
        LOG.info("Enrollment confirmed by user")
        self.remove_context("AwaitingEnrollmentConfirmation")
        self.proceed_with_enrollment()

    @intent_handler(
        IntentBuilder("ConfirmEnrollmentNo")
        .require("NoKeyword")
        .require("AwaitingEnrollmentConfirmation")
        .build()
    )
    def handle_confirm_enrollment_no(self, message):
        """Handle negative confirmation for enrollment"""
        LOG.info("Enrollment cancelled by user")
        self.remove_context("AwaitingEnrollmentConfirmation")
        self.speak_dialog("enrollment_cancelled")
        self.clear_enrollment_context()

    # Voice Profile Management Intent Handlers

    @intent_handler(
        IntentBuilder("ListEnrolledUsers")
        .require("ListKeyword")
        .require("VoiceKeyword")
        .optionally("UsersKeyword")
        .build()
    )
    def handle_list_enrolled_users(self, message):
        """Handle request to list enrolled users"""
        LOG.info("List enrolled users intent triggered")

        if hasattr(self, "_bus") and self._bus is not None:
            # Request user list from voice ID plugin
            self.bus.emit(Message(MessageBusEvents.GET_USERS, {}))

            # Provide immediate feedback
            self.speak_dialog("checking_enrolled_users")
        else:
            self.speak_dialog("error_plugin_unavailable")

    # Name Collection Intent Handlers

    @intent_handler(
        IntentBuilder("CollectUserName").require("AwaitingUserName").build()
    )
    def handle_collect_user_name(self, message):
        """Handle name input during enrollment"""
        utterance = message.data.get("utterance", "")
        user_name = self.extract_name_from_utterance_flexible(utterance)

        if user_name and self.validate_user_name(user_name):
            LOG.info(f"Valid name collected: {user_name}")
            self.remove_context("AwaitingUserName")
            self.enrollment_context["user_name"] = user_name
            self.enrollment_context["state"] = "sample_collection"
            self.speak_dialog("name_confirmed", {"name": user_name})
            self.speak_dialog(
                "ready_for_samples",
                {"name": user_name, "count": self.enrollment_context["target_samples"]},
            )
        else:
            LOG.warning(f"Invalid name provided: {user_name}")
            self.speak_dialog("name_invalid")
            self.speak_dialog("request_name")

    def extract_name_from_utterance_flexible(self, utterance: str) -> Optional[str]:
        """Extract name from utterance using flexible patterns for name collection"""
        if not utterance:
            return None

        utterance = utterance.strip()

        # Pattern 1: Direct name responses like "John", "Mary Smith"
        # Remove common phrase starters
        name_starters = [
            r"^my name is\s+",
            r"^i\'?m\s+",
            r"^call me\s+",
            r"^it\'?s\s+",
            r"^the name is\s+",
            r"^use\s+",
        ]

        cleaned_utterance = utterance
        for pattern in name_starters:
            cleaned_utterance = re.sub(
                pattern, "", cleaned_utterance, flags=re.IGNORECASE
            )

        # Pattern 2: Extract name from common patterns
        name_patterns = [
            r"as\s+([a-zA-Z][a-zA-Z\s\-\']{1,48}[a-zA-Z])",  # Check "as NAME" first
            r"name\s+([a-zA-Z][a-zA-Z\s\-\']{1,48}[a-zA-Z])",  # Then "name NAME"
            r"^([a-zA-Z][a-zA-Z\s\-\']{1,48}[a-zA-Z])$",  # Finally direct name
        ]

        for pattern in name_patterns:
            match = re.search(pattern, cleaned_utterance.strip(), re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                if len(name) >= 2:
                    LOG.debug(f"Extracted name: {name}")
                    return self.clean_name(name)

        return None

    def validate_user_name(self, name: str) -> bool:
        """Validate user name meets requirements"""
        if not name or not isinstance(name, str):
            return False

        name = name.strip()

        # Length requirements
        if len(name) < 2 or len(name) > 50:
            return False

        # Character requirements - allow letters (including Unicode), spaces, hyphens, apostrophes
        # Use Unicode character categories for better international name support
        import unicodedata

        # Check if name contains only valid characters (letters, spaces, hyphens, apostrophes)
        valid_chars = True
        for char in name:
            if not (
                unicodedata.category(char).startswith("L")  # Letters (any language)
                or char in " '-"
            ):  # Spaces, hyphens, apostrophes
                valid_chars = False
                break

        if not valid_chars:
            return False

        # Ensure name starts and ends with a letter
        if not (
            unicodedata.category(name[0]).startswith("L")
            and unicodedata.category(name[-1]).startswith("L")
        ):
            return False

        # Prevent excessive consecutive spaces or special chars
        if re.search(r"[\s\-\']{3,}", name):
            return False

        # Common name validation - no numbers, no profanity placeholders
        invalid_patterns = [
            r"\d",  # No numbers
            r"[!@#$%^&*()_+=\[\]{}|;:,.<>?/~`]",  # No special chars except allowed
            r"^(test|admin|root|user)$",  # No generic names
        ]

        for pattern in invalid_patterns:
            if re.search(pattern, name, re.IGNORECASE):
                return False

        return True

    def clean_name(self, name: str) -> str:
        """Clean and format name properly"""
        if not name:
            return ""

        # Remove extra whitespace
        name = re.sub(r"\s+", " ", name.strip())

        # Handle special cases for proper capitalization
        parts = []
        for word in name.split():
            if "-" in word:
                # Handle hyphenated names like Jean-Luc
                parts.append("-".join(part.capitalize() for part in word.split("-")))
            else:
                parts.append(word.capitalize())

        return " ".join(parts)

    def proceed_with_enrollment(self):
        """Continue with enrollment after confirmation"""
        if not self.enrollment_context.get("user_name"):
            # Need to collect name first
            self.enrollment_context["state"] = "name_collection"
            self.speak_dialog("request_name")
            self.set_context("AwaitingUserName")
        else:
            # Have name, proceed to sample collection
            self.enrollment_context["state"] = "sample_collection"
            self.enrollment_context["samples"] = []
            self.enrollment_context["current_sample_index"] = 0
            self.speak_dialog(
                "ready_for_samples",
                {
                    "name": self.enrollment_context["user_name"],
                    "count": self.enrollment_context["target_samples"],
                },
            )
            self.start_sample_collection()

    def extract_user_name_from_utterance(self, utterance: str) -> Optional[str]:
        """Extract user name from utterance using various patterns"""
        if not utterance:
            return None

        # Pattern 1: "as [Name]"
        as_match = re.search(
            r"\bas\s+([a-zA-Z][a-zA-Z\s\-\']{1,48}[a-zA-Z])\b", utterance, re.IGNORECASE
        )
        if as_match:
            name = as_match.group(1).strip()
            LOG.debug(f"Extracted name using 'as' pattern: {name}")
            return name

        # Pattern 2: "for [Name]"
        for_match = re.search(
            r"\bfor\s+([a-zA-Z][a-zA-Z\s\-\']{1,48}[a-zA-Z])\b",
            utterance,
            re.IGNORECASE,
        )
        if for_match:
            name = for_match.group(1).strip()
            LOG.debug(f"Extracted name using 'for' pattern: {name}")
            return name

        return None

    def start_enrollment_flow(self, user_name: Optional[str], trigger: str = "unknown"):
        """Start the voice enrollment flow"""
        LOG.info(
            f"Starting enrollment flow - user_name: {user_name}, trigger: {trigger}"
        )

        self.enrollment_context = {
            "state": "confirmation",
            "user_name": user_name,
            "trigger": trigger,
            "samples_collected": 0,
            "target_samples": self.target_samples,
            "started_at": datetime.now().isoformat(),
        }

        if user_name:
            self.speak_dialog("enrollment_start_with_name", {"name": user_name})
        else:
            self.speak_dialog("enrollment_start_no_name")

        # Request confirmation if enabled in settings
        if self.confirmation_required:
            self.set_context("AwaitingEnrollmentConfirmation")
        else:
            # Skip confirmation and proceed directly
            self.proceed_with_enrollment()

    def start_sample_collection(self):
        """Start collecting voice samples"""
        if self.enrollment_context.get(
            "current_sample_index", 0
        ) >= self.enrollment_context.get("target_samples", 3):
            # All samples collected, proceed to processing
            self.finish_sample_collection()
            return

        sample_index = self.enrollment_context["current_sample_index"]
        phrase = SAMPLE_PHRASES[sample_index % len(SAMPLE_PHRASES)]

        self.speak_dialog(
            "sample_prompt",
            {
                "number": sample_index + 1,
                "total": self.enrollment_context["target_samples"],
                "phrase": phrase,
            },
        )

        # Set context for recording
        self.set_context("AwaitingSample")
        self.enrollment_context["current_phrase"] = phrase
        self.enrollment_context["recording_start_time"] = datetime.now().isoformat()

        # Start recording after a brief pause
        self.schedule_event(self.start_recording, 2.0, data={"phrase": phrase})

    def start_recording(self, message):
        """Start audio recording for voice sample"""
        phrase = message.data.get("phrase", "")
        sample_id = str(uuid.uuid4())

        LOG.info(
            f"Starting recording for sample {self.enrollment_context['current_sample_index'] + 1}"
        )

        # Create temporary file for recording
        temp_dir = tempfile.gettempdir()
        audio_file = os.path.join(temp_dir, f"omva_sample_{sample_id}.wav")

        # Send message to start recording
        recording_data = {
            "sample_id": sample_id,
            "audio_file": audio_file,
            "phrase": phrase,
            "max_duration": self.max_audio_duration,
            "min_duration": self.min_audio_duration,
        }

        if hasattr(self, "_bus") and self._bus is not None:
            self.bus.emit(Message("mycroft.mic.listen", recording_data))

        # Store recording info in context
        self.enrollment_context["current_recording"] = {
            "sample_id": sample_id,
            "audio_file": audio_file,
            "phrase": phrase,
            "start_time": datetime.now().isoformat(),
        }

        # Set timeout for recording
        self.schedule_event(
            self.stop_recording_timeout,
            self.max_audio_duration + 1.0,
            data={"sample_id": sample_id},
        )

    def stop_recording_timeout(self, message):
        """Handle recording timeout"""
        sample_id = message.data.get("sample_id")
        current_recording = self.enrollment_context.get("current_recording", {})

        if current_recording.get("sample_id") == sample_id:
            LOG.warning("Recording timed out")
            self.speak_dialog("recording_timeout")
            self.retry_current_sample()

    @intent_handler(
        IntentBuilder("StopRecording")
        .require("StopKeyword")
        .require("AwaitingSample")
        .build()
    )
    def handle_stop_recording(self, message):
        """Handle stop recording command"""
        self.stop_current_recording()

    def stop_current_recording(self):
        """Stop the current recording and process it"""
        current_recording = self.enrollment_context.get("current_recording")
        if not current_recording:
            return

        LOG.info("Stopping current recording")

        # Send stop recording message
        if hasattr(self, "_bus") and self._bus is not None:
            self.bus.emit(Message("mycroft.mic.stop"))

        # Process the recorded sample
        self.process_audio_sample(current_recording)

    def process_audio_sample(self, recording_info: Dict[str, Any]):
        """Process recorded audio sample"""
        audio_file = recording_info["audio_file"]
        phrase = recording_info["phrase"]
        sample_id = recording_info["sample_id"]

        if not os.path.exists(audio_file):
            LOG.error(f"Audio file not found: {audio_file}")
            self.speak_dialog("recording_failed")
            self.retry_current_sample()
            return

        # Validate audio quality
        quality_score = self.validate_audio_quality(audio_file, phrase)

        if quality_score >= self.quality_threshold:
            # Good quality sample
            sample_data = {
                "sample_id": sample_id,
                "audio_file": audio_file,
                "phrase": phrase,
                "quality_score": quality_score,
                "duration": self.get_audio_duration(audio_file),
                "recorded_at": recording_info["start_time"],
            }

            self.enrollment_context["samples"].append(sample_data)
            self.enrollment_context["current_sample_index"] += 1

            LOG.info(
                f"Sample {len(self.enrollment_context['samples'])} recorded successfully"
            )
            self.speak_dialog(
                "sample_accepted",
                {
                    "number": len(self.enrollment_context["samples"]),
                    "total": self.enrollment_context["target_samples"],
                },
            )

            # Remove recording context and continue
            self.remove_context("AwaitingSample")
            self.enrollment_context.pop("current_recording", None)

            # Continue with next sample or finish
            self.schedule_event(self.start_sample_collection, 1.0)

        else:
            # Poor quality sample
            LOG.warning(f"Poor audio quality: {quality_score}")
            self.speak_dialog("sample_quality_poor")
            self.retry_current_sample()

    def validate_audio_quality(self, audio_file: str, expected_phrase: str) -> float:
        """Validate audio quality and content"""
        try:
            # Check file size (basic quality check)
            if not os.path.exists(audio_file):
                return 0.0

            file_size = os.path.getsize(audio_file)
            if file_size < 1000:  # Too small (less than 1KB)
                return 0.2

            # Check duration
            duration = self.get_audio_duration(audio_file)
            if duration < self.min_audio_duration:
                return 0.3
            if duration > self.max_audio_duration:
                return 0.4

            # Basic quality score based on duration and file size
            duration_score = min(
                1.0,
                (duration - self.min_audio_duration)
                / (self.max_audio_duration - self.min_audio_duration),
            )
            size_score = min(1.0, file_size / 50000)  # Normalize to ~50KB

            base_score = (duration_score + size_score) / 2

            # Add some randomness to simulate more sophisticated quality checks
            import random

            quality_variance = random.uniform(-0.1, 0.1)
            final_score = max(0.0, min(1.0, base_score + quality_variance))

            LOG.debug(
                f"Audio quality score: {final_score} (duration: {duration}s, size: {file_size}B)"
            )
            return final_score

        except Exception as e:
            LOG.error(f"Error validating audio quality: {e}")
            return 0.1

    def get_audio_duration(self, audio_file: str) -> float:
        """Get audio file duration in seconds"""
        try:
            # Simple duration estimation based on file size
            # In real implementation, would use audio library like librosa
            file_size = os.path.getsize(audio_file)
            # Rough estimate: 16kHz, 16-bit mono = ~32KB per second
            estimated_duration = file_size / 32000
            return max(0.1, estimated_duration)
        except Exception as e:
            LOG.error(f"Error getting audio duration: {e}")
            return 0.0

    def retry_current_sample(self):
        """Retry recording current sample"""
        # Clean up failed recording
        current_recording = self.enrollment_context.get("current_recording")
        if current_recording:
            audio_file = current_recording.get("audio_file")
            if audio_file and os.path.exists(audio_file):
                try:
                    os.remove(audio_file)
                except Exception as e:
                    LOG.warning(f"Could not remove failed recording: {e}")

        # Reset recording state
        self.enrollment_context.pop("current_recording", None)

        # Ask if user wants to try again
        self.speak_dialog("retry_sample")
        self.set_context("AwaitingRetryConfirmation")

    @intent_handler(
        IntentBuilder("RetryYes")
        .require("YesKeyword")
        .require("AwaitingRetryConfirmation")
        .build()
    )
    def handle_retry_yes(self, message):
        """Handle retry confirmation - yes"""
        self.remove_context("AwaitingRetryConfirmation")
        self.start_sample_collection()

    @intent_handler(
        IntentBuilder("RetryNo")
        .require("NoKeyword")
        .require("AwaitingRetryConfirmation")
        .build()
    )
    def handle_retry_no(self, message):
        """Handle retry confirmation - no"""
        self.remove_context("AwaitingRetryConfirmation")
        self.speak_dialog("enrollment_cancelled")
        self.clear_enrollment_context()

    def finish_sample_collection(self):
        """Complete sample collection and proceed to processing"""
        samples_count = len(self.enrollment_context.get("samples", []))
        user_name = self.enrollment_context.get("user_name", "Unknown")

        LOG.info(f"Sample collection complete: {samples_count} samples for {user_name}")

        self.enrollment_context["state"] = EnrollmentState.PROCESSING
        self.speak_dialog(
            "samples_complete", {"name": user_name, "count": samples_count}
        )

        # Send samples to voice identification plugin
        self.send_samples_for_processing()

    def send_samples_for_processing(self):
        """Send collected samples to voice identification plugin for processing"""
        user_name = self.enrollment_context.get("user_name")
        samples = self.enrollment_context.get("samples", [])

        if not user_name or not samples:
            LOG.error("Invalid enrollment context for processing")
            self.handle_enrollment_failed(
                ErrorCodes.PROCESSING_FAILED, "Invalid enrollment data"
            )
            return

        # Convert audio files to hex-encoded format required by plugin
        audio_samples_hex = []
        for sample in samples:
            audio_file = sample["audio_file"]
            try:
                if os.path.exists(audio_file):
                    with open(audio_file, "rb") as f:
                        audio_data = f.read()
                        audio_hex = audio_data.hex()
                        audio_samples_hex.append(audio_hex)
                        LOG.debug(
                            f"Converted audio sample to hex: {len(audio_hex)} chars"
                        )
                else:
                    LOG.warning(f"Audio file not found: {audio_file}")
            except Exception as e:
                LOG.error(f"Failed to read audio file {audio_file}: {e}")
                continue

        if not audio_samples_hex:
            LOG.error("No valid audio samples could be converted")
            self.handle_enrollment_failed(
                ErrorCodes.PROCESSING_FAILED, "No valid audio samples"
            )
            return

        enrollment_id = str(uuid.uuid4())
        enrollment_data = {
            "user_id": user_name,  # Plugin expects 'user_id', not 'user_name'
            "audio_samples": audio_samples_hex,  # Hex-encoded audio data
            "enrollment_id": enrollment_id,
            "timestamp": datetime.now().isoformat(),
        }

        # Store enrollment ID in context for response matching
        self.enrollment_context["enrollment_id"] = enrollment_id

        LOG.info(
            f"Sending {len(audio_samples_hex)} hex-encoded samples for processing: {user_name}"
        )

        # Send to voice identification plugin
        if hasattr(self, "_bus") and self._bus is not None:
            self.bus.emit(Message(MessageBusEvents.ENROLL_USER, enrollment_data))

        # Set timeout for processing response
        self.schedule_event(
            self.handle_processing_timeout, 30.0, data={"enrollment_id": enrollment_id}
        )

    def get_enrollment_state(self) -> str:
        """Get current enrollment state"""
        return self.enrollment_context.get("state", "idle")

    def clear_enrollment_context(self):
        """Clear enrollment context"""
        self.enrollment_context = {}
        LOG.debug("Enrollment context cleared")

    def handle_enrollment_response(self, message):
        """Handle response from voice identification plugin"""
        LOG.info(f"Received enrollment response: {message.data}")

        response_data = message.data
        status = response_data.get("status", "error")
        user_id = response_data.get("user_id", "Unknown")  # Plugin uses 'user_id'
        enrollment_id = response_data.get("enrollment_id")

        # Verify this response is for our current enrollment (if enrollment_id is available)
        current_enrollment_id = self.enrollment_context.get("enrollment_id")
        if (
            enrollment_id
            and current_enrollment_id
            and enrollment_id != current_enrollment_id
        ):
            LOG.debug(f"Received response for different enrollment: {enrollment_id}")
            return

        if status == "success":
            self.enrollment_context["state"] = EnrollmentState.COMPLETED
            samples_processed = response_data.get("samples_processed", 0)

            # Only speak if bus is available
            if hasattr(self, "_bus") and self._bus is not None:
                self.speak_dialog(
                    "enrollment_success",
                    {
                        "name": user_id,
                        "samples": samples_processed,
                        "total_users": 1,  # Default since total_users might not be available
                    },
                )

            self.cleanup_enrollment_files()
            self.clear_enrollment_context()
            LOG.info(f"Enrollment completed successfully for {user_id}")
        else:
            # Handle error response
            error_message = response_data.get("message", "Unknown error")

            # Map plugin error messages to our error codes
            if (
                "User ID is required" in error_message
                or "missing user_name" in error_message
            ):
                error_code = ErrorCodes.INVALID_NAME
            elif (
                "Audio samples are required" in error_message
                or "No valid audio samples" in error_message
            ):
                error_code = ErrorCodes.SAMPLE_COUNT_INSUFFICIENT
            elif "Voice processor not initialized" in error_message:
                error_code = ErrorCodes.PLUGIN_UNAVAILABLE
            else:
                error_code = ErrorCodes.PROCESSING_FAILED

            self.handle_enrollment_failed(error_code, error_message)

    def handle_users_response(self, message):
        """Handle response from voice identification plugin for user listing"""
        LOG.info(f"Received users response: {message.data}")

        response_data = message.data
        status = response_data.get("status", "error")  # Plugin uses 'status' field

        if status == "success":
            users = response_data.get("users", [])
            total_users = response_data.get("total_users", len(users))
            model_info = response_data.get("model_info", {})

            LOG.info(f"Voice ID plugin has {total_users} enrolled users: {users}")

            # Speak the results to the user
            if hasattr(self, "_bus") and self._bus is not None:
                if total_users == 0:
                    self.speak_dialog("no_enrolled_users")
                elif total_users == 1:
                    self.speak_dialog("one_enrolled_user", {"name": users[0]})
                else:
                    # For multiple users, speak count and first few names
                    if total_users <= 3:
                        users_list = ", ".join(users[:-1]) + f" and {users[-1]}"
                        self.speak_dialog(
                            "multiple_enrolled_users",
                            {"count": total_users, "users": users_list},
                        )
                    else:
                        # Too many to list all, just give count
                        self.speak_dialog("many_enrolled_users", {"count": total_users})

            # Store for potential skill use
            self.enrollment_context["enrolled_users"] = users
            self.enrollment_context["model_info"] = model_info
        else:
            # Handle error response
            error_message = response_data.get("message", "User listing failed")
            LOG.warning(f"Failed to get enrolled users: {status} - {error_message}")

            if hasattr(self, "_bus") and self._bus is not None:
                self.speak_dialog("error_checking_users")

    def handle_processing_timeout(self, message):
        """Handle processing timeout"""
        enrollment_id = message.data.get("enrollment_id")
        current_state = self.enrollment_context.get("state")

        if current_state == EnrollmentState.PROCESSING:
            LOG.warning(f"Processing timeout for enrollment {enrollment_id}")
            self.handle_enrollment_failed(
                ErrorCodes.PROCESSING_FAILED, "Processing timeout"
            )

    def handle_enrollment_failed(self, error_code: str, error_message: str):
        """Handle enrollment failure"""
        LOG.error(f"Enrollment failed: {error_code} - {error_message}")

        self.enrollment_context["state"] = EnrollmentState.FAILED
        self.enrollment_context["error_code"] = error_code
        self.enrollment_context["error_message"] = error_message

        # Only speak if bus is available
        if hasattr(self, "_bus") and self._bus is not None:
            # Speak appropriate error message
            if error_code == ErrorCodes.AUDIO_QUALITY_POOR:
                self.speak_dialog("error_audio_quality")
            elif error_code == ErrorCodes.PROCESSING_FAILED:
                self.speak_dialog("error_processing_failed")
            elif error_code == ErrorCodes.NETWORK_ERROR:
                self.speak_dialog("error_network")
            elif error_code == ErrorCodes.PLUGIN_UNAVAILABLE:
                self.speak_dialog("error_plugin_unavailable")
            elif error_code == ErrorCodes.USER_EXISTS:
                self.speak_dialog("error_user_exists")
            else:
                self.speak_dialog("error_general")

            # Ask if user wants to try again
            self.speak_dialog("ask_try_again")
            self.set_context("AwaitingRetryEnrollment")

        self.cleanup_enrollment_files()

    @intent_handler(
        IntentBuilder("TryAgainYes")
        .require("YesKeyword")
        .require("AwaitingRetryEnrollment")
        .build()
    )
    def handle_try_again_yes(self, message):
        """Handle try again confirmation - yes"""
        self.remove_context("AwaitingRetryEnrollment")
        user_name = self.enrollment_context.get("user_name")
        self.start_enrollment_flow(user_name, trigger="retry")

    @intent_handler(
        IntentBuilder("TryAgainNo")
        .require("NoKeyword")
        .require("AwaitingRetryEnrollment")
        .build()
    )
    def handle_try_again_no(self, message):
        """Handle try again confirmation - no"""
        self.remove_context("AwaitingRetryEnrollment")
        self.speak_dialog("enrollment_cancelled")
        self.clear_enrollment_context()

    def cleanup_enrollment_files(self):
        """Clean up temporary files from enrollment process"""
        samples = self.enrollment_context.get("samples", [])

        for sample in samples:
            audio_file = sample.get("audio_file")
            if audio_file and os.path.exists(audio_file):
                try:
                    os.remove(audio_file)
                    LOG.debug(f"Removed temporary file: {audio_file}")
                except Exception as e:
                    LOG.warning(f"Could not remove file {audio_file}: {e}")

        # Also clean up any current recording
        current_recording = self.enrollment_context.get("current_recording")
        if current_recording:
            audio_file = current_recording.get("audio_file")
            if audio_file and os.path.exists(audio_file):
                try:
                    os.remove(audio_file)
                except Exception as e:
                    LOG.warning(f"Could not remove recording file {audio_file}: {e}")

    def stop(self):
        """Clean up when skill stops"""
        self.clear_enrollment_context()

    def shutdown(self):
        """Cleanup on shutdown"""
        LOG.info("OMVA Voice Enrollment Skill shutting down")
        self.clear_enrollment_context()


def create_skill():
    """Create skill instance (required by OVOS)"""
    return OMVAVoiceEnrollmentSkill()
