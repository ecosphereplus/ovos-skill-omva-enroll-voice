"""
OMVA Voice Enrollment Skill

Provides natural voice interface for voice enrollment with semantic intent recognition.
Supports multiple ways to express enrollment intent: "enroll my voice", "save my voice",
"remember me", etc.

Copyright 2024 OMVA Team
Licensed under the Apache License, Version 2.0
"""

import re
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
        self.confirmation_required = True
        self.replace_existing_profiles = False
        self.relationship_words = []  # Initialize relationship words list
        self.locale_patterns = {}  # Initialize locale patterns dictionary

        # Timeout configuration
        self.enrollment_timeouts = {
            "confirmation": 30,  # Wait for user confirmation
            "sample_collection": 15,  # Wait for each sample
            "between_samples": 10,  # Wait between samples
            "overall_session": 600,  # Total enrollment session (10 minutes)
            "processing": 30,  # Wait for plugin processing
            "retry_confirmation": 30,  # Wait for retry confirmation
            "name_collection": 30,  # Wait for third-person name collection
        }
        self.active_timers = {}  # Track active timeout timers

    def initialize(self):
        """Initialize skill after construction"""
        LOG.info("Initializing OMVA Voice Enrollment Skill")
        self.setup_voice_id_integration()
        self.load_settings()
        self.load_locale_patterns()

    def load_locale_patterns(self):
        """Load locale-specific patterns for name extraction"""
        try:
            # Get current language/locale
            lang = self.lang if hasattr(self, "lang") else "en-us"
            patterns_file = self.find_resource(
                "patterns/name_extraction.patterns", lang
            )

            if not patterns_file:
                LOG.warning(
                    f"No name extraction patterns found for {lang}, falling back to hardcoded English patterns"
                )
                self.use_fallback_patterns()
                return

            self.locale_patterns = {}
            with open(patterns_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        if ":" in line:
                            pattern_type, pattern = line.split(":", 1)
                            if pattern_type not in self.locale_patterns:
                                self.locale_patterns[pattern_type] = []
                            self.locale_patterns[pattern_type].append(pattern.strip())

            LOG.info(
                f"Loaded locale patterns for {lang}: {len(self.locale_patterns)} pattern types"
            )

        except Exception as e:
            LOG.error(f"Error loading locale patterns: {e}")
            self.use_fallback_patterns()

    def use_fallback_patterns(self):
        """Use fallback English patterns when locale patterns aren't available"""
        self.locale_patterns = {
            "enrollment_action": [
                "enroll",
                "register",
                "save",
                "learn",
                "train",
                "add",
                "create",
            ],
            "possessive": ["my", "our", "the"],
            "voice_term": ["voice", "voice profile"],
            "name_intro": ["my name is", "i am", "i'm", "call me"],
            "name_with_preposition": ["as {name}", "for {name}"],
            "third_person_action": [
                "{enrollment_action} {possessive} {relationship}'s {voice_term}"
            ],
            "third_person_direct": ["{enrollment_action} {name}'s {voice_term}"],
            "third_person_with_my": ["my {relationship} {name}"],
            "third_person_standalone": ["{relationship} {name}"],
        }

    def build_dynamic_patterns(self):
        """Build regex patterns from locale-specific templates"""
        patterns = []

        # Get pattern components
        enrollment_actions = self.locale_patterns.get("enrollment_action", ["enroll"])
        possessives = self.locale_patterns.get("possessive", ["my"])
        voice_terms = self.locale_patterns.get("voice_term", ["voice"])
        name_intros = self.locale_patterns.get("name_intro", ["my name is"])

        # Build basic name extraction patterns
        for intro in name_intros:
            pattern = rf"\b{re.escape(intro)}\s+((?:Dr\.?\s+|Mr\.?\s+|Ms\.?\s+|Mrs\.?\s+|Miss\s+)?[a-zA-Z][a-zA-Z\s\-\'\.{{1,48}}[a-zA-Z])\b"
            patterns.append(pattern)

        # Build "as [Name]" and "for [Name]" patterns
        for prep_pattern in self.locale_patterns.get("name_with_preposition", []):
            if "{name}" in prep_pattern:
                pattern_template = prep_pattern.replace(
                    "{name}",
                    r"((?:Dr\.?\s+|Mr\.?\s+|Ms\.?\s+|Mrs\.?\s+|Miss\s+)?[a-zA-Z][a-zA-Z\s\-\'\.]{1,48}[a-zA-Z])",
                )
                pattern = rf"\b{re.escape(pattern_template)}\b".replace(
                    r"\(", "("
                ).replace(r"\)", ")")
                patterns.append(pattern)

        return patterns

    def build_third_person_patterns(self):
        """Build third-person enrollment patterns from locale templates"""
        patterns = []

        # Get pattern components
        enrollment_actions = self.locale_patterns.get("enrollment_action", ["enroll"])
        possessives = self.locale_patterns.get("possessive", ["my"])
        voice_terms = self.locale_patterns.get("voice_term", ["voice"])

        # Create dynamic relationship pattern
        relationship_list = "|".join(
            re.escape(word) for word in self.relationship_words
        )

        # Build basic third-person patterns
        basic_patterns = [
            # "enroll my [relationship]'s voice"
            rf"\b(?:{'|'.join(re.escape(action) for action in enrollment_actions)})\s+(?:{'|'.join(re.escape(poss) for poss in possessives)})\s+(\w+)\'?s\s+(?:{'|'.join(re.escape(term) for term in voice_terms)})\b",
            # "enroll [name]'s voice"
            rf"\b(?:{'|'.join(re.escape(action) for action in enrollment_actions)})\s+([a-zA-Z][a-zA-Z\s\-\'\.{{1,48}}[a-zA-Z])\'?s\s+(?:{'|'.join(re.escape(term) for term in voice_terms)})\b",
        ]

        # Build relationship-based patterns
        for poss in possessives:
            # "my [relationship] [name]"
            pattern = rf"\b{re.escape(poss)}\s+(?:{relationship_list})\s+([a-zA-Z][a-zA-Z\s\-\'\.{{1,48}}[a-zA-Z])\b"
            basic_patterns.append(pattern)

        # "[relationship] [name]"
        pattern = (
            rf"\b(?:{relationship_list})\s+([a-zA-Z][a-zA-Z\s\-\'\.{{1,48}}[a-zA-Z])\b"
        )
        basic_patterns.append(pattern)

        return basic_patterns

    def load_settings(self):
        """Load skill settings with defaults"""
        self.target_samples = self.settings.get("target_samples", 3)
        self.confirmation_required = self.settings.get("confirmation_required", True)
        self.replace_existing_profiles = self.settings.get(
            "replace_existing_profiles", False
        )

        # Load configurable relationship words for third-person enrollment
        default_relationships = [
            "son",
            "daughter",
            "wife",
            "husband",
            "brother",
            "sister",
            "mother",
            "father",
            "mom",
            "dad",
            "kid",
            "child",
            "parent",
            "grandson",
            "granddaughter",
            "grandfather",
            "grandmother",
            "grandpa",
            "grandma",
            "uncle",
            "aunt",
            "cousin",
            "nephew",
            "niece",
            "friend",
            "partner",
            "roommate",
            "colleague",
        ]

        relationship_setting = self.settings.get(
            "relationship_words", default_relationships
        )

        # Handle both list format (from code) and comma-separated string (from UI)
        if isinstance(relationship_setting, str):
            self.relationship_words = [
                word.strip().lower()
                for word in relationship_setting.split(",")
                if word.strip()
            ]
        elif isinstance(relationship_setting, list):
            self.relationship_words = [
                word.lower() for word in relationship_setting if word
            ]
        else:
            self.relationship_words = default_relationships

        LOG.info(
            f"Settings loaded: {self.target_samples} samples, confirmation: {self.confirmation_required}, "
            f"relationship_words: {len(self.relationship_words)} terms"
        )

    def settings_changed_callback(self):
        """Called when skill settings are changed"""
        LOG.info("Settings updated, reloading configuration")
        self.load_settings()

    def on_lang_changed(self, message):
        """Called when language/locale changes"""
        LOG.info(f"Language changed, reloading locale patterns")
        self.load_locale_patterns()

    def setup_voice_id_integration(self):
        """Setup integration with voice identification plugin"""
        # Only set up bus integration if bus is available
        if hasattr(self, "_bus") and self._bus is not None:
            self.bus.on("ovos.voiceid.enroll.response", self.handle_enrollment_response)
            self.bus.on("ovos.voiceid.users.response", self.handle_users_response)
            self.bus.on(MessageBusEvents.SAMPLE_COLLECTED, self.handle_sample_collected)
            LOG.debug("Voice ID integration setup complete")
        else:
            LOG.debug("Bus not available during initialization")

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

    # Third-Person Name Collection Intent Handlers

    @intent_handler(
        IntentBuilder("ThirdPersonNameProvided")
        .require("AwaitingThirdPersonName")
        .build()
    )
    def handle_third_person_name_provided(self, message):
        """Handle name provided for third-person enrollment"""
        utterance = message.data.get("utterance", "")
        LOG.info(f"Processing third-person name from utterance: {utterance}")

        # Extract name from the utterance using existing patterns
        extracted_name = None

        # Try standard name extraction patterns
        for pattern in [
            r"(?:their name is|his name is|her name is)\s+([a-zA-Z][a-zA-Z\s\-\'\.]{1,48}[a-zA-Z])",
            r"(?:it's|its)\s+([a-zA-Z][a-zA-Z\s\-\'\.]{1,48}[a-zA-Z])",
            r"^([a-zA-Z][a-zA-Z\s\-\'\.]{1,48}[a-zA-Z])$",  # Just a name
        ]:
            match = re.search(pattern, utterance.strip(), re.IGNORECASE)
            if match:
                extracted_name = match.group(1).strip()
                break

        if extracted_name:
            cleaned_name = self.clean_name(extracted_name)
            if self._is_valid_name_with_supported_title(cleaned_name):
                # Confirm the name and proceed
                self.enrollment_context["user_name"] = cleaned_name
                self.enrollment_context["state"] = "confirmation"
                self.remove_context("AwaitingThirdPersonName")

                # Confirm the third-person enrollment
                self.speak_dialog("name_confirmed", {"name": cleaned_name})
                self.speak_dialog("third_person_ready", {"name": cleaned_name})

                # Proceed with enrollment or confirmation
                if self.confirmation_required:
                    self.set_context("AwaitingEnrollmentConfirmation")
                    self.set_enrollment_timeout(
                        "confirmation",
                        self.enrollment_timeouts["confirmation"],
                        self.handle_confirmation_timeout,
                    )
                else:
                    self.proceed_with_enrollment()
                return

        # Invalid or no name provided
        self.speak_dialog("name_invalid")
        relationship = self.enrollment_context.get("relationship", "someone else")
        self.speak_dialog("third_person_enrollment", {"relationship": relationship})

        # Reset timeout
        self.set_enrollment_timeout(
            "name_collection", 30, self.handle_name_collection_timeout
        )

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
        utterance = message.data.get("utterance", "").lower()

        # Check for restart/change name requests
        restart_phrases = [
            "restart",
            "start over",
            "start again",
            "begin again",
            "restart enrollment",
            "change name",
            "different name",
            "wrong name",
            "use different name",
            "that's wrong",
            "that's not right",
            "not that name",
        ]

        if any(phrase in utterance for phrase in restart_phrases):
            LOG.info(f"User requested name change/restart: {utterance}")
            self.remove_context("AwaitingUserName")
            self.speak_dialog("name_change_requested")
            # Restart name collection
            self.set_context("AwaitingUserName")
            return

        # Check for abort/cancel during name collection
        abort_phrases = [
            "cancel",
            "stop",
            "abort",
            "quit",
            "exit",
            "nevermind",
            "never mind",
            "forget it",
            "not now",
            "no thanks",
            "i changed my mind",
        ]

        if any(phrase in utterance for phrase in abort_phrases):
            LOG.info(f"User aborted during name collection: {utterance}")
            self.remove_context("AwaitingUserName")
            self.speak_dialog("enrollment_cancelled")
            self.cleanup_enrollment_session()
            return

        user_name = self.extract_name_from_utterance_flexible(utterance)

        if user_name and self.validate_user_name(user_name):
            LOG.info(f"Valid name collected: {user_name}")
            self.remove_context("AwaitingUserName")
            self.enrollment_context["user_name"] = user_name
            self.enrollment_context["state"] = "sample_collection"
            self.enrollment_context["samples"] = []
            self.enrollment_context["current_sample_index"] = 0

            # Notify VoiceID plugin about enrollment session start
            if hasattr(self, "_bus") and self._bus is not None:
                self.bus.emit(
                    Message(
                        MessageBusEvents.START_ENROLLMENT,
                        {
                            "session_id": self.enrollment_context.get("session_id"),
                            "user_id": self.enrollment_context["user_name"],
                            "target_samples": self.enrollment_context["target_samples"],
                            "timestamp": datetime.now().isoformat(),
                        },
                    )
                )

            self.speak_dialog("name_confirmed", {"name": user_name})
            # Start sample collection immediately after name confirmation
            self.start_sample_collection()
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

        # Pattern 2: Extract name from common patterns - Enhanced with title support
        name_patterns = [
            # Check "as NAME" first - with title support
            r"as\s+((?:Dr\.?\s+|Mr\.?\s+|Ms\.?\s+|Mrs\.?\s+|Miss\s+)?[a-zA-Z][a-zA-Z\s\-\'\.]{1,48}[a-zA-Z])",
            # Then "name NAME" - with title support
            r"name\s+((?:Dr\.?\s+|Mr\.?\s+|Ms\.?\s+|Mrs\.?\s+|Miss\s+)?[a-zA-Z][a-zA-Z\s\-\'\.]{1,48}[a-zA-Z])",
            # Finally direct name - with title support
            r"^((?:Dr\.?\s+|Mr\.?\s+|Ms\.?\s+|Mrs\.?\s+|Miss\s+)?[a-zA-Z][a-zA-Z\s\-\'\.]{1,48}[a-zA-Z])$",
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

        # Check if this contains unsupported titles that should be rejected
        unsupported_titles = [
            "professor",
            "captain",
            "sergeant",
            "lieutenant",
            "colonel",
            "general",
            "admiral",
        ]
        first_word = name.split()[0].lower().rstrip(".")
        if first_word in unsupported_titles:
            # Return the original name as-is, but the calling function should handle validation
            pass

        # Handle special cases for proper capitalization
        parts = []
        for word in name.split():
            # Handle titles specially
            if word.lower() in [
                "dr",
                "dr.",
                "mr",
                "mr.",
                "ms",
                "ms.",
                "mrs",
                "mrs.",
                "miss",
            ]:
                if word.lower() in ["dr", "dr."]:
                    parts.append("Dr.")
                elif word.lower() in ["mr", "mr."]:
                    parts.append("Mr.")
                elif word.lower() in ["ms", "ms."]:
                    parts.append("Ms.")
                elif word.lower() in ["mrs", "mrs."]:
                    parts.append("Mrs.")
                elif word.lower() == "miss":
                    parts.append("Miss")
            elif "-" in word:
                # Handle hyphenated names like Jean-Luc
                parts.append("-".join(part.capitalize() for part in word.split("-")))
            elif "'" in word:
                # Handle apostrophes like O'Connor
                apostrophe_parts = word.split("'")
                formatted_parts = []
                for i, part in enumerate(apostrophe_parts):
                    if i == 0:
                        formatted_parts.append(part.capitalize())
                    else:
                        # Capitalize after apostrophe
                        formatted_parts.append(part.capitalize())
                parts.append("'".join(formatted_parts))
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

            # Notify VoiceID plugin about enrollment session start
            if hasattr(self, "_bus") and self._bus is not None:
                self.bus.emit(
                    Message(
                        MessageBusEvents.START_ENROLLMENT,
                        {
                            "session_id": self.enrollment_context.get("session_id"),
                            "user_id": self.enrollment_context["user_name"],
                            "target_samples": self.enrollment_context["target_samples"],
                            "timestamp": datetime.now().isoformat(),
                        },
                    )
                )

            self.speak_dialog(
                "ready_for_samples",
                {
                    "name": self.enrollment_context["user_name"],
                    "count": self.enrollment_context["target_samples"],
                },
            )
            # Start sample collection immediately - no need for extra confirmation
            self.start_sample_collection()

    def extract_user_name_from_utterance(self, utterance: str) -> Optional[str]:
        """Extract user name from utterance using locale-aware patterns"""
        if not utterance:
            return None

        # First check for third-person enrollment patterns
        third_person_result = self.extract_third_person_name(utterance)
        if third_person_result:
            return third_person_result

        # Use dynamically built patterns from locale
        try:
            patterns = self.build_dynamic_patterns()
            for pattern in patterns:
                match = re.search(pattern, utterance, re.IGNORECASE)
                if match:
                    name = match.group(1).strip()
                    cleaned_name = self.clean_name(name)
                    if self._is_valid_name_with_supported_title(cleaned_name):
                        LOG.debug(
                            f"Extracted name using locale pattern: {cleaned_name}"
                        )
                        return cleaned_name
        except Exception as e:
            LOG.warning(
                f"Error using locale patterns, falling back to hardcoded patterns: {e}"
            )

        # Fallback to hardcoded patterns if locale patterns fail
        return self._extract_name_fallback(utterance)

    def _extract_name_fallback(self, utterance: str) -> Optional[str]:
        """Fallback name extraction using hardcoded English patterns"""
        patterns = [
            # "as [Name]" - Enhanced to handle titles
            r"\bas\s+((?:Dr\.?\s+|Mr\.?\s+|Ms\.?\s+|Mrs\.?\s+|Miss\s+)?[a-zA-Z][a-zA-Z\s\-\'\.]{1,48}[a-zA-Z])\b",
            # "for [Name]" - Enhanced to handle titles
            r"\bfor\s+((?:Dr\.?\s+|Mr\.?\s+|Ms\.?\s+|Mrs\.?\s+|Miss\s+)?[a-zA-Z][a-zA-Z\s\-\'\.]{1,48}[a-zA-Z])\b",
            # "my name is [Name]"
            r"\bmy\s+name\s+is\s+((?:Dr\.?\s+|Mr\.?\s+|Ms\.?\s+|Mrs\.?\s+|Miss\s+)?[a-zA-Z][a-zA-Z\s\-\'\.]{1,48}[a-zA-Z])\b",
            # "I'm [Name]" or "I am [Name]"
            r"\b(?:i\'?m|i\s+am)\s+((?:Dr\.?\s+|Mr\.?\s+|Ms\.?\s+|Mrs\.?\s+|Miss\s+)?[a-zA-Z][a-zA-Z\s\-\'\.]{1,48}[a-zA-Z])\b",
            # "call me [Name]"
            r"\bcall\s+me\s+((?:Dr\.?\s+|Mr\.?\s+|Ms\.?\s+|Mrs\.?\s+|Miss\s+)?[a-zA-Z][a-zA-Z\s\-\'\.]{1,48}[a-zA-Z])\b",
        ]

        for pattern in patterns:
            match = re.search(pattern, utterance, re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                cleaned_name = self.clean_name(name)
                if self._is_valid_name_with_supported_title(cleaned_name):
                    LOG.debug(f"Extracted name using fallback pattern: {cleaned_name}")
                    return cleaned_name

        return None

    def extract_third_person_name(self, utterance: str) -> Optional[str]:
        """Extract name from third-person enrollment patterns"""
        if not utterance:
            return None

        # Create dynamic relationship pattern based on configured words
        relationship_list = "|".join(
            re.escape(word) for word in self.relationship_words
        )

        # Family/relationship patterns with dynamic relationship words
        basic_patterns = [
            # "enroll my [relationship]'s voice"
            r"\benroll\s+my\s+(\w+)\'?s\s+voice\b",
            # "register my [relationship]'s voice"
            r"\bregister\s+my\s+(\w+)\'?s\s+voice\b",
            # "enroll [name]'s voice"
            r"\benroll\s+([a-zA-Z][a-zA-Z\s\-\'\.]{1,48}[a-zA-Z])\'?s\s+voice\b",
            # "register [name]'s voice"
            r"\bregister\s+([a-zA-Z][a-zA-Z\s\-\'\.]{1,48}[a-zA-Z])\'?s\s+voice\b",
        ]

        # Dynamic patterns built with relationship words
        dynamic_patterns = [
            # "my [relationship] [name]"
            r"\bmy\s+(?:"
            + relationship_list
            + r")\s+([a-zA-Z][a-zA-Z\s\-\'\.]{1,48}[a-zA-Z])\b",
            # "[relationship] [name]"
            r"\b(?:"
            + relationship_list
            + r")\s+([a-zA-Z][a-zA-Z\s\-\'\.]{1,48}[a-zA-Z])\b",
        ]

        relationship_patterns = basic_patterns + dynamic_patterns

        for pattern in relationship_patterns:
            match = re.search(pattern, utterance, re.IGNORECASE)
            if match:
                extracted = match.group(1).strip()

                # Check if it's a relationship word (needs name collection)
                if extracted.lower() in self.relationship_words:
                    # Mark this as a third-person scenario requiring name collection
                    self.enrollment_context = getattr(self, "enrollment_context", {})
                    self.enrollment_context["third_person"] = True
                    self.enrollment_context["relationship"] = extracted.lower()
                    LOG.debug(
                        f"Detected third-person enrollment for relationship: {extracted}"
                    )
                    return None  # Will prompt for actual name
                else:
                    # It's an actual name
                    cleaned_name = self.clean_name(extracted)
                    if self._is_valid_name_with_supported_title(cleaned_name):
                        # Mark as third-person but with known name
                        self.enrollment_context = getattr(
                            self, "enrollment_context", {}
                        )
                        self.enrollment_context["third_person"] = True
                        LOG.debug(f"Extracted third-person name: {cleaned_name}")
                        return cleaned_name

        return None

    def _is_valid_name_with_supported_title(self, name: str) -> bool:
        """Check if name contains only supported titles or no title"""
        if not name:
            return False

        # List of supported titles
        supported_titles = ["dr.", "mr.", "ms.", "mrs.", "miss"]

        # List of unsupported titles that should be rejected
        unsupported_titles = [
            "professor",
            "captain",
            "sergeant",
            "lieutenant",
            "colonel",
            "general",
            "admiral",
        ]

        first_word = name.split()[0].lower().rstrip(".")

        # If it starts with an unsupported title, reject it
        if first_word in unsupported_titles:
            return False

        return True

    def start_enrollment_flow(self, user_name: Optional[str], trigger: str = "unknown"):
        """Start the voice enrollment flow"""
        LOG.info(
            f"Starting enrollment flow - user_name: {user_name}, trigger: {trigger}"
        )

        # Cancel any existing timeouts first
        self.cancel_all_enrollment_timeouts()

        # Initialize enrollment context
        if not hasattr(self, "enrollment_context") or not self.enrollment_context:
            self.enrollment_context = {}

        # Check if this is a third-person enrollment scenario
        is_third_person = self.enrollment_context.get("third_person", False)
        relationship = self.enrollment_context.get("relationship")

        # Update enrollment context
        self.enrollment_context.update(
            {
                "state": (
                    "confirmation"
                    if not is_third_person or user_name
                    else "name_collection"
                ),
                "user_name": user_name,
                "trigger": trigger,
                "samples_collected": 0,
                "target_samples": self.target_samples,
                "started_at": datetime.now().isoformat(),
                "session_id": str(uuid.uuid4())[:8],  # Short session ID for logging
            }
        )

        # Set overall session timeout
        self.set_enrollment_timeout(
            "overall_session",
            self.enrollment_timeouts["overall_session"],
            self.handle_session_timeout,
        )

        # Handle third-person enrollment scenarios
        if is_third_person and not user_name:
            # Need to collect the actual name for third-person enrollment
            if relationship:
                self.speak_dialog(
                    "third_person_enrollment", {"relationship": relationship}
                )
            else:
                self.speak_dialog(
                    "third_person_enrollment", {"relationship": "someone else"}
                )

            self.set_context("AwaitingThirdPersonName")
            self.set_enrollment_timeout(
                "name_collection",
                self.enrollment_timeouts.get("name_collection", 30),
                self.handle_name_collection_timeout,
            )
            return
        elif is_third_person and user_name:
            # Third-person enrollment with name already provided
            self.speak_dialog("third_person_ready", {"name": user_name})
        elif user_name:
            # Regular enrollment with name provided
            self.speak_dialog("enrollment_start_with_name", {"name": user_name})
        else:
            # Regular enrollment without name
            self.speak_dialog("enrollment_start_no_name")

        # Request confirmation if enabled in settings
        if self.confirmation_required:
            self.set_context("AwaitingEnrollmentConfirmation")
            # Set confirmation timeout
            self.set_enrollment_timeout(
                "confirmation",
                self.enrollment_timeouts["confirmation"],
                self.handle_confirmation_timeout,
            )
        else:
            # Skip confirmation and proceed directly, but add brief pause for better UX
            self.schedule_event(self.proceed_with_enrollment, 0.5)

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

        # For the first sample, provide context about what we're doing
        if sample_index == 0:
            self.speak_dialog(
                "ready_for_samples",
                {
                    "name": self.enrollment_context["user_name"],
                    "count": self.enrollment_context["target_samples"],
                },
            )

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

        # Set sample timeout
        timeout_duration = self.enrollment_timeouts.get("sample_collection", 15)
        self.set_enrollment_timeout(
            "sample_collection", timeout_duration, self.handle_sample_timeout
        )

        # Start recording immediately for a smooth experience
        self.schedule_event(self.start_recording, 1.0, data={"phrase": phrase})

    def start_recording(self, message):
        """Notify VoiceID plugin to start collecting voice sample"""
        phrase = message.data.get("phrase", "")
        sample_id = str(uuid.uuid4())

        LOG.info(
            f"Requesting voice sample {self.enrollment_context['current_sample_index'] + 1}: {phrase}"
        )

        # Store recording info in context for tracking
        self.enrollment_context["current_recording"] = {
            "sample_id": sample_id,
            "phrase": phrase,
            "start_time": datetime.now().isoformat(),
        }

        # Notify VoiceID plugin to start collecting this specific sample
        if hasattr(self, "_bus") and self._bus is not None:
            self.bus.emit(
                Message(
                    MessageBusEvents.COLLECT_SAMPLE,
                    {
                        "session_id": self.enrollment_context.get("session_id"),
                        "sample_id": sample_id,
                        "phrase": phrase,
                        "sample_number": self.enrollment_context["current_sample_index"]
                        + 1,
                        "total_samples": self.enrollment_context["target_samples"],
                    },
                )
            )

    def stop_recording_timeout(self, message):
        """Handle recording timeout"""
        sample_id = message.data.get("sample_id")
        current_recording = self.enrollment_context.get("current_recording", {})

        if current_recording.get("sample_id") == sample_id:
            LOG.warning("Sample collection timed out")
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

    @intent_handler(
        IntentBuilder("StopEnrollment")
        .one_of("StopKeyword", "AbortKeyword", "NoKeyword")
        .build()
    )
    def handle_stop_enrollment(self, message):
        """Handle general stop/abort commands during any enrollment phase"""
        if not self.enrollment_context or self.get_enrollment_state() == "idle":
            return False  # Not in enrollment, ignore

        utterance = message.data.get("utterance", "").lower()

        # More specific patterns for enrollment cancellation
        enrollment_stop_phrases = [
            "stop enrollment",
            "cancel enrollment",
            "abort enrollment",
            "stop this",
            "cancel this",
            "quit enrollment",
            "end enrollment",
            "i want to stop",
            "i want to cancel",
            "i don't want to continue",
        ]

        # Check if this is clearly an enrollment abort
        if any(phrase in utterance for phrase in enrollment_stop_phrases) or any(
            word in utterance.split()
            for word in ["stop", "cancel", "abort", "quit", "nevermind"]
        ):
            LOG.info(f"User requested enrollment abort: {utterance}")
            self.speak_dialog("enrollment_cancelled")
            self.cleanup_enrollment_session()
            return True  # Consumed the utterance

        return False  # Let other handlers process

    @intent_handler(
        IntentBuilder("RestartEnrollment").require("RestartKeyword").build()
    )
    def handle_restart_enrollment(self, message):
        """Handle restart enrollment requests during any phase"""
        if not self.enrollment_context or self.get_enrollment_state() == "idle":
            return False  # Not in enrollment, ignore

        LOG.info("User requested enrollment restart")

        # Extract new name if provided
        utterance = message.data.get("utterance", "")
        new_name = self.extract_user_name_from_utterance(utterance)

        # Clean up current session
        self.cleanup_enrollment_session()

        # Start fresh enrollment flow
        if new_name:
            LOG.info(f"Restarting enrollment with new name: {new_name}")
            self.start_enrollment_flow(new_name, trigger="restart_with_name")
        else:
            LOG.info("Restarting enrollment - will prompt for name")
            self.speak_dialog("enrollment_restarted")
            self.start_enrollment_flow(None, trigger="restart_no_name")

    @intent_handler(
        IntentBuilder("EnrollAsDifferentUser")
        .require("EnrollKeyword")
        .optionally("VoiceKeyword")
        .optionally("MeKeyword")
        .require("UserName")
        .build()
    )
    def handle_enroll_as_different_user(self, message):
        """Handle enrollment requests with new name during active enrollment"""
        if not self.enrollment_context or self.get_enrollment_state() == "idle":
            # Not in enrollment, treat as new enrollment
            return self.handle_enroll_voice_adapt_intent(message)

        new_name = message.data.get("UserName")
        if new_name:
            LOG.info(f"User wants to restart enrollment as: {new_name}")

            current_name = self.enrollment_context.get("user_name")
            if current_name and current_name.lower() != new_name.lower():
                # Different name - provide context about the switch
                self.speak_dialog("name_switched", {"new_name": new_name})

            # Clean up current session
            self.cleanup_enrollment_session()

            # Start fresh with new name
            self.start_enrollment_flow(new_name, trigger="restart_different_user")
            return True

        return False

    @intent_handler(
        IntentBuilder("ChangeName").one_of("RestartKeyword", "NoKeyword").build()
    )
    def handle_change_name_request(self, message):
        """Handle requests to change name during enrollment"""
        if not self.enrollment_context or self.get_enrollment_state() == "idle":
            return False  # Not in enrollment, ignore

        utterance = message.data.get("utterance", "").lower()

        # Patterns that indicate user wants to change/correct the name
        name_change_patterns = [
            "wrong name",
            "different name",
            "change name",
            "not that name",
            "that's wrong",
            "that's not right",
            "use different name",
            "call me",
            "my name is",
            "i am",
            "actually i'm",
            "no my name is",
        ]

        if any(pattern in utterance for pattern in name_change_patterns):
            LOG.info(f"User wants to change name: {utterance}")

            # Check if they provided a new name in the same utterance
            new_name = self.extract_user_name_from_utterance(
                message.data.get("utterance", "")
            )

            if new_name and self.validate_user_name(new_name):
                # Direct name change with new name provided
                LOG.info(f"Changing name to: {new_name}")
                old_name = self.enrollment_context.get("user_name", "previous")

                # Update enrollment context
                self.enrollment_context["user_name"] = new_name

                # If we were already collecting samples, restart with new name
                if self.enrollment_context.get("state") == "sample_collection":
                    self.cleanup_enrollment_session()
                    self.start_enrollment_flow(new_name, trigger="name_corrected")
                else:
                    # Just update the name and continue
                    self.speak_dialog("name_confirmed", {"name": new_name})
                    self.proceed_with_enrollment()
            else:
                # No new name provided, prompt for it
                self.speak_dialog("name_change_requested")
                self.enrollment_context["state"] = "name_collection"
                self.set_context("AwaitingUserName")

            return True  # Consumed the utterance

        return False

    def stop_current_recording(self):
        """Request VoiceID plugin to stop current sample collection"""
        current_recording = self.enrollment_context.get("current_recording")
        if not current_recording:
            return

        LOG.info("Requesting VoiceID plugin to stop current sample collection")

        # Request plugin to stop collecting current sample
        if hasattr(self, "_bus") and self._bus is not None:
            self.bus.emit(
                Message(
                    MessageBusEvents.STOP_SAMPLE_COLLECTION,
                    {
                        "session_id": self.enrollment_context.get("session_id"),
                        "sample_id": current_recording.get("sample_id"),
                    },
                )
            )
        # Plugin will send sample.collected message when ready

    def process_audio_sample(self, recording_info: Dict[str, Any]):
        """Process recorded audio sample - simplified as plugin handles audio processing"""
        phrase = recording_info["phrase"]
        sample_id = recording_info["sample_id"]

        # Store basic sample metadata (plugin will handle actual audio processing)
        sample_data = {
            "sample_id": sample_id,
            "phrase": phrase,
            "recorded_at": recording_info["start_time"],
        }

        self.enrollment_context["samples"].append(sample_data)
        self.enrollment_context["current_sample_index"] += 1

        LOG.info(
            f"Sample {len(self.enrollment_context['samples'])} recorded for phrase: {phrase}"
        )

        # Cancel sample timeout since we got a sample
        self.cancel_enrollment_timeout("sample_collection")

        current_sample_num = len(self.enrollment_context["samples"])
        target_samples = self.enrollment_context["target_samples"]

        self.speak_dialog(
            "sample_accepted",
            {
                "number": current_sample_num,
                "total": target_samples,
            },
        )

        # Remove recording context and continue
        self.remove_context("AwaitingSample")
        self.enrollment_context.pop("current_recording", None)

        # Provide smooth transition to next sample or completion
        if current_sample_num < target_samples:
            # More samples needed - start next one with brief pause for UX
            self.schedule_event(self.start_sample_collection, 1.5)
        else:
            # All samples collected - proceed to completion
            self.schedule_event(self.finish_sample_collection, 1.0)

    def retry_current_sample(self):
        """Retry recording current sample"""
        # Cancel any active sample timeout
        self.cancel_enrollment_timeout("sample_collection")

        # Reset recording state
        self.enrollment_context.pop("current_recording", None)

        # Ask if user wants to try again
        self.speak_dialog("retry_sample")
        self.set_context("AwaitingRetryConfirmation")

        # Set retry confirmation timeout
        timeout_duration = self.enrollment_timeouts.get("retry_confirmation", 30)
        self.set_enrollment_timeout(
            "retry_confirmation", timeout_duration, self.handle_retry_timeout
        )

    @intent_handler(
        IntentBuilder("RetryYes")
        .require("YesKeyword")
        .require("AwaitingRetryConfirmation")
        .build()
    )
    def handle_retry_yes(self, message):
        """Handle retry confirmation - yes"""
        self.cancel_enrollment_timeout("retry_confirmation")
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
        self.cancel_enrollment_timeout("retry_confirmation")
        self.remove_context("AwaitingRetryConfirmation")
        self.speak_dialog("enrollment_cancelled")
        self.reset_enrollment_context()

    @intent_handler(
        IntentBuilder("TimeoutContinue")
        .require("ContinueKeyword")
        .require("AwaitingTimeoutConfirmation")
        .build()
    )
    def handle_timeout_continue(self, message):
        """Handle continue response to timeout confirmation"""
        self.cancel_enrollment_timeout("timeout_confirmation")
        self.remove_context("AwaitingTimeoutConfirmation")
        timeout_type = self.enrollment_context.get("timeout_type", "")

        if timeout_type == "sample_final":
            # Continue with next sample or complete enrollment
            self.speak_dialog("timeout_continuing_samples")
            # "Continuing with enrollment. Let's try the next sample."
            self.skip_to_next_sample_or_complete()
        elif timeout_type == "session_final":
            # Reset session timeout and continue
            self.speak_dialog("timeout_continuing_session")
            # "Continuing enrollment. I've reset the session timer."
            # Reset the session timeout for another full duration
            session_timeout = self.enrollment_timeouts.get("overall_session", 600)
            self.set_enrollment_timeout(
                "overall_session", session_timeout, self.handle_session_timeout
            )

    @intent_handler(
        IntentBuilder("TimeoutAbort")
        .require("AbortKeyword")
        .require("AwaitingTimeoutConfirmation")
        .build()
    )
    def handle_timeout_abort(self, message):
        """Handle abort response to timeout confirmation"""
        self.cancel_enrollment_timeout("timeout_confirmation")
        self.remove_context("AwaitingTimeoutConfirmation")
        timeout_type = self.enrollment_context.get("timeout_type", "")

        if timeout_type == "sample_final":
            self.speak_dialog("enrollment_aborted_by_user")
            # "Enrollment aborted as requested."
        elif timeout_type == "session_final":
            self.speak_dialog("enrollment_session_aborted")
            # "Enrollment session aborted as requested."
            # Notify plugin to clean up
            if hasattr(self, "_bus") and self._bus is not None:
                self.bus.emit(
                    Message(
                        MessageBusEvents.SESSION_EXPIRED,
                        {
                            "session_id": self.enrollment_context.get("session_id"),
                            "user_name": self.enrollment_context.get("user_name"),
                        },
                    )
                )

        self.reset_enrollment_context()

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
        """Send enrollment request to voice identification plugin for processing"""
        user_name = self.enrollment_context.get("user_name")
        samples = self.enrollment_context.get("samples", [])

        if not user_name or not samples:
            LOG.error("Invalid enrollment context for processing")
            self.handle_enrollment_failed(
                ErrorCodes.PROCESSING_FAILED, "Invalid enrollment data"
            )
            return

        enrollment_id = str(uuid.uuid4())
        enrollment_data = {
            "user_id": user_name,  # Plugin expects 'user_id'
            "session_id": self.enrollment_context.get("session_id"),
            "enrollment_id": enrollment_id,
            "sample_count": len(samples),
            "sample_phrases": [sample["phrase"] for sample in samples],
            "timestamp": datetime.now().isoformat(),
        }

        # Store enrollment ID in context for response matching
        self.enrollment_context["enrollment_id"] = enrollment_id

        LOG.info(
            f"Requesting VoiceID plugin to process {len(samples)} samples for user: {user_name}"
        )

        # Send enrollment request to voice identification plugin
        # Plugin will handle all audio processing from its audio transformer
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

            self.reset_enrollment_context()
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

    def handle_sample_collected(self, message):
        """Handle notification from VoiceID plugin that a sample has been collected"""
        LOG.info(f"Received sample collected notification: {message.data}")

        sample_data = message.data
        sample_id = sample_data.get("sample_id")
        quality_ok = sample_data.get("quality_ok", True)

        # Verify this is for our current enrollment session
        current_recording = self.enrollment_context.get("current_recording", {})
        if current_recording.get("sample_id") != sample_id:
            LOG.warning(
                f"Received sample notification for unknown sample_id: {sample_id}"
            )
            return

        if quality_ok:
            # Process the successful sample
            self.process_audio_sample(current_recording)
        else:
            # Sample quality was poor, retry
            LOG.warning("VoiceID plugin reported poor sample quality")
            self.speak_dialog("sample_quality_poor")
            self.retry_current_sample()

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

    def converse(self, message=None):
        """Handle conversational context during enrollment - intercept global stops"""
        if not self.enrollment_context or self.get_enrollment_state() == "idle":
            return False  # Not in enrollment, let other skills handle

        utterance = (
            message.data.get("utterances", [""])[0].lower()
            if message and message.data.get("utterances")
            else ""
        )

        # Check for global abort/stop intents during enrollment
        abort_patterns = [
            "stop",
            "cancel",
            "quit",
            "abort",
            "exit",
            "nevermind",
            "never mind",
            "forget it",
            "not now",
            "end this",
            "stop enrollment",
            "cancel enrollment",
        ]

        # Check for restart/change name requests during enrollment
        restart_patterns = [
            "restart",
            "start over",
            "start again",
            "begin again",
            "restart enrollment",
            "change name",
            "different name",
            "wrong name",
            "use different name",
            "that's wrong",
            "that's not right",
            "not that name",
            "enroll as",
            "i want to restart",
            "let me restart",
            "can i restart",
        ]

        if any(pattern in utterance for pattern in restart_patterns):
            LOG.info(f"User requested enrollment restart: {utterance}")

            # Extract new name if provided
            new_name = self.extract_user_name_from_utterance(utterance)

            # Clean up current session
            self.cleanup_enrollment_session()

            # Start fresh enrollment
            if new_name:
                LOG.info(f"Restarting enrollment with new name: {new_name}")
                self.start_enrollment_flow(new_name, trigger="restart_with_name")
            else:
                self.speak_dialog("enrollment_restarted")
                self.start_enrollment_flow(None, trigger="restart_no_name")
            return True  # Consumed the utterance

        if any(pattern in utterance for pattern in abort_patterns):
            LOG.info(f"Global abort detected during enrollment: {utterance}")
            self.speak_dialog("enrollment_cancelled")
            self.cleanup_enrollment_session()
            return True  # Consumed the utterance

        return False  # Let normal intent handling continue

    def cleanup_enrollment_session(self):
        """Clean up enrollment session and notify plugin"""
        # Notify plugin to stop any ongoing sample collection
        if self.enrollment_context.get("current_recording"):
            self.stop_current_recording()

        # Notify plugin of session termination
        if hasattr(self, "_bus") and self._bus is not None:
            self.bus.emit(
                Message(
                    MessageBusEvents.SESSION_EXPIRED,
                    {
                        "session_id": self.enrollment_context.get("session_id"),
                        "user_name": self.enrollment_context.get("user_name"),
                        "reason": "user_abort",
                    },
                )
            )

        self.cancel_all_enrollment_timeouts()
        self.clear_enrollment_context()

    def stop(self):
        """Clean up when skill stops"""
        self.cancel_all_enrollment_timeouts()
        self.clear_enrollment_context()

    # ==========================================
    # TIMEOUT MANAGEMENT METHODS
    # ==========================================

    def set_enrollment_timeout(self, timeout_type: str, duration: int, callback):
        """Set a timeout with automatic cleanup"""
        # Cancel existing timer of this type
        self.cancel_enrollment_timeout(timeout_type)

        # Set new timer
        timer_id = self.schedule_event(callback, duration)
        self.active_timers[timeout_type] = timer_id

        LOG.debug(f"Set {timeout_type} timeout for {duration} seconds")

    def cancel_enrollment_timeout(self, timeout_type: str):
        """Cancel a specific timeout"""
        if timeout_type in self.active_timers:
            timer_id = self.active_timers.pop(timeout_type)
            self.cancel_scheduled_event(timer_id)
            LOG.debug(f"Cancelled {timeout_type} timeout")

    def cancel_all_enrollment_timeouts(self):
        """Cancel all active enrollment timeouts"""
        for timeout_type in list(self.active_timers.keys()):
            self.cancel_enrollment_timeout(timeout_type)
        LOG.debug("Cancelled all enrollment timeouts")

    # ==========================================
    # TIMEOUT HANDLERS
    # ==========================================

    def handle_confirmation_timeout(self, message=None):
        """Handle timeout when waiting for user confirmation"""
        retry_count = self.enrollment_context.get("confirmation_retry_count", 0)

        if retry_count < 2:  # Allow 2 retries
            self.speak_dialog("enrollment_timeout_confirmation")
            # "I didn't hear a response. Would you like to enroll your voice? Say yes or no."
            self.enrollment_context["confirmation_retry_count"] = retry_count + 1
            self.set_enrollment_timeout(
                "confirmation", 30, self.handle_confirmation_timeout
            )
        else:
            self.speak_dialog("enrollment_cancelled_timeout")
            # "Enrollment cancelled due to no response."
            self.reset_enrollment_context()

    def handle_name_collection_timeout(self, message=None):
        """Handle timeout when waiting for third-person name"""
        retry_count = self.enrollment_context.get("name_collection_retry_count", 0)

        if retry_count < 2:  # Allow 2 retries
            relationship = self.enrollment_context.get("relationship", "someone else")
            self.speak_dialog("ask_try_again")
            self.speak_dialog("third_person_enrollment", {"relationship": relationship})
            self.enrollment_context["name_collection_retry_count"] = retry_count + 1
            self.set_enrollment_timeout(
                "name_collection", 30, self.handle_name_collection_timeout
            )
        else:
            self.speak_dialog("enrollment_cancelled")
            self.reset_enrollment_context()

    def handle_sample_timeout(self, message=None):
        """Handle timeout during sample collection"""
        sample_retry_count = self.enrollment_context.get("sample_retry_count", 0)
        current_phrase = self.enrollment_context.get("current_phrase", "")

        if sample_retry_count < 2:  # Allow 2 retries per sample
            if sample_retry_count == 0:
                self.speak_dialog("sample_timeout_first", {"phrase": current_phrase})
            else:
                self.speak_dialog("sample_timeout_second", {"phrase": current_phrase})

            self.enrollment_context["sample_retry_count"] = sample_retry_count + 1
            self.restart_current_sample()
        else:
            # Ask for confirmation before skipping/aborting
            self.speak_dialog("sample_timeout_confirm_abort")
            # "Having trouble with that sample. Should I continue with enrollment or abort? Say continue or abort."
            self.set_context("AwaitingTimeoutConfirmation")
            self.enrollment_context["timeout_type"] = "sample_final"
            timeout_duration = self.enrollment_timeouts.get("retry_confirmation", 30)
            self.set_enrollment_timeout(
                "timeout_confirmation",
                timeout_duration,
                self.handle_timeout_confirmation_timeout,
            )

    def handle_session_timeout(self, message=None):
        """Handle overall enrollment session timeout"""
        # Ask for confirmation before expiring the session
        self.speak_dialog("session_timeout_confirm_abort")
        # "Your enrollment session is about to expire. Should I continue or abort enrollment? Say continue or abort."
        self.set_context("AwaitingTimeoutConfirmation")
        self.enrollment_context["timeout_type"] = "session_final"
        timeout_duration = self.enrollment_timeouts.get("retry_confirmation", 30)
        self.set_enrollment_timeout(
            "timeout_confirmation",
            timeout_duration,
            self.handle_timeout_confirmation_timeout,
        )

    def handle_retry_timeout(self, message=None):
        """Handle timeout on retry confirmation"""
        self.speak_dialog("enrollment_cancelled_timeout")
        # "Enrollment cancelled due to no response."
        self.reset_enrollment_context()

    def handle_timeout_confirmation_timeout(self, message=None):
        """Handle timeout when user doesn't respond to abort/continue confirmation"""
        # If no response to abort/continue, treat as abort
        timeout_type = self.enrollment_context.get("timeout_type", "")
        self.remove_context("AwaitingTimeoutConfirmation")

        if timeout_type == "sample_final":
            self.speak_dialog("enrollment_cancelled_no_response")
            # "No response received. Enrollment cancelled."
        elif timeout_type == "session_final":
            self.speak_dialog("enrollment_session_expired")
            # "Session expired. Enrollment cancelled."
            # Notify plugin to clean up
            if hasattr(self, "_bus") and self._bus is not None:
                self.bus.emit(
                    Message(
                        MessageBusEvents.SESSION_EXPIRED,
                        {
                            "session_id": self.enrollment_context.get("session_id"),
                            "user_name": self.enrollment_context.get("user_name"),
                        },
                    )
                )

        self.reset_enrollment_context()

    # ==========================================
    # TIMEOUT RECOVERY METHODS
    # ==========================================

    def restart_current_sample(self):
        """Restart collection of current sample after timeout"""
        current_phrase = self.enrollment_context.get("current_phrase", "")
        if current_phrase:
            # Restart sample collection with same phrase
            self.set_enrollment_timeout(
                "sample_collection",
                self.enrollment_timeouts["sample_collection"],
                self.handle_sample_timeout,
            )
            LOG.debug(f"Restarted sample collection for phrase: {current_phrase}")
        else:
            # Fallback to normal sample collection flow
            self.start_sample_collection()

    def skip_to_next_sample_or_complete(self):
        """Skip current sample and move to next or complete enrollment"""
        current_sample = self.enrollment_context.get("current_sample_index", 0)
        target_samples = self.enrollment_context.get("target_samples", 3)
        collected_samples = len(self.enrollment_context.get("samples", []))

        if collected_samples >= 2:  # Have at least 2 samples, can complete
            self.speak_dialog("enrollment_completing_partial")
            # "Completing enrollment with the samples we have."
            self.finish_sample_collection()
        elif current_sample + 1 < target_samples:
            # Move to next sample
            self.enrollment_context["current_sample_index"] = current_sample + 1
            self.enrollment_context["sample_retry_count"] = 0  # Reset retry count
            self.start_sample_collection()
        else:
            # No more samples and insufficient collected
            self.speak_dialog("enrollment_insufficient_samples")
            # "Not enough voice samples collected. Let's try again."
            self.offer_retry()

    def offer_retry(self):
        """Offer user option to retry enrollment"""
        self.speak_dialog("ask_try_again")
        # "Would you like to try enrolling your voice again? Say yes or no."
        self.set_context("AwaitingRetryConfirmation")
        self.set_enrollment_timeout("retry_confirmation", 30, self.handle_retry_timeout)

    def pause_enrollment(self):
        """Pause enrollment for user to resume later"""
        self.speak_dialog("enrollment_paused")
        # "Enrollment paused. Say 'continue enrollment' or 'enroll my voice' to resume."

        # Store partial progress
        self.enrollment_context["state"] = "paused"
        self.enrollment_context["paused_at"] = datetime.now().isoformat()

        # Set long-term timeout for paused state (1 hour)
        self.set_enrollment_timeout(
            "paused_session", 3600, self.expire_paused_enrollment
        )

    def expire_paused_enrollment(self, message=None):
        """Expire a paused enrollment after timeout"""
        self.speak_dialog("paused_enrollment_expired")
        # "Your paused enrollment has expired. Please start over."
        self.reset_enrollment_context()

    def reset_enrollment_context(self):
        """Reset enrollment context and cancel all timeouts"""
        self.cancel_all_enrollment_timeouts()
        self.clear_enrollment_context()
        LOG.info("Enrollment context reset due to timeout or cancellation")

    def shutdown(self):
        """Cleanup on shutdown"""
        LOG.info("OMVA Voice Enrollment Skill shutting down")
        self.clear_enrollment_context()


def create_skill():
    """Create skill instance (required by OVOS)"""
    return OMVAVoiceEnrollmentSkill()
