# OMVA Voice ID Plugin - Technical Implementation Guide (Mock-Based Development)

## Quick Start Implementation Tasks

### ✅ Task 1: Mock Testing Framework - COMPLETED
**Priority: HIGH | Status: COMPLETED**

Created comprehensive mock plugin implementation in `tests/mock_voiceid_plugin.py` that simulates all plugin API endpoints based on technical documentation.

**Features Included:**
- Complete message bus API simulation
- User enrollment and management  
- Speaker verification
- Real-time voice identification events
- Statistics and monitoring
- Error response simulation
- Test harness for skill validation

### ✅ Task 2: Message Bus Communication Verification - COMPLETED  
**Priority: HIGH | Status: COMPLETED**

Mock framework provides immediate verification of message bus patterns without requiring actual plugin installation.

**Test Usage:**
```bash
cd /root/omva/ovos-skill-omva-enroll-voice  
python tests/mock_voiceid_plugin.py
# Validates all API communication patterns
```

### Task 3: Add Missing Real-time Identification Handlers
**Priority: HIGH | Estimated Time: 30 minutes**

The skill currently handles enrollment responses but lacks real-time identification handlers. Add these to `__init__.py`:

```python
def setup_voice_id_integration(self):
    """Setup integration with voice identification plugin"""
    # Existing code...
    if hasattr(self, "_bus") and self._bus is not None:
        # Existing handlers
        self.bus.on("ovos.voiceid.enroll.response", self.handle_enrollment_response)
        self.bus.on("ovos.voiceid.users.response", self.handle_users_response)
        
        # NEW: Real-time identification handlers
        self.bus.on("ovos.voice.identified", self.handle_voice_identified)
        self.bus.on("ovos.voice.unknown", self.handle_voice_unknown)
        
        LOG.debug("Voice ID integration setup complete")

def handle_voice_identified(self, message):
    """Handle real-time voice identification events"""
    data = message.data
    speaker_id = data.get("speaker_id")
    confidence = data.get("confidence", 0.0)
    
    LOG.info(f"Voice identified: {speaker_id} (confidence: {confidence:.3f})")
    
    # Store current speaker context
    self.current_speaker = speaker_id
    self.speaker_confidence = confidence
    
    # Optional: Announce identification (configurable)
    if self.settings.get("announce_identification", False):
        if confidence > 0.9:
            self.speak(f"Hello {speaker_id}")

def handle_voice_unknown(self, message):
    """Handle unknown voice detection events"""
    data = message.data
    confidence = data.get("confidence", 0.0)
    
    LOG.info(f"Unknown voice detected (confidence: {confidence:.3f})")
    
    # Clear current speaker context  
    self.current_speaker = None
    self.speaker_confidence = confidence
    
    # Optional: Offer enrollment for unknown speakers
    if self.settings.get("offer_enrollment_to_unknown", False) and confidence > 0.3:
        self.speak("I don't recognize your voice. Would you like to enroll?")
        self.set_context("OfferingEnrollment")
```

**Test with Mock:**
```python
# Test real-time identification
from tests.mock_voiceid_plugin import MockVoiceIDPlugin
mock_plugin = MockVoiceIDPlugin(bus)
mock_plugin.simulate_voice_identification("test_user", 0.89)
```

### Task 6: Add Speaker Verification Capability
**Priority: MEDIUM | Estimated Time: 1-2 hours**

Add speaker verification intent and handler:

```python
@intent_handler(
    IntentBuilder("VerifySpeaker")
    .require("VerifyKeyword")
    .require("VoiceKeyword")
    .build()
)
def handle_verify_speaker(self, message):
    """Handle speaker verification requests"""
    self.speak("I'll need two audio samples to compare. Please say something first.")
    
    # Record first sample
    audio1 = self.record_audio_sample("First sample")
    if not audio1:
        self.speak("Failed to record first sample")
        return
        
    self.speak("Now please say something different for the second sample")
    
    # Record second sample  
    audio2 = self.record_audio_sample("Second sample")
    if not audio2:
        self.speak("Failed to record second sample")
        return
    
    # Send verification request
    self.bus.emit(Message("ovos.voiceid.verify_speakers", {
        "audio_sample1": audio1.hex(),
        "audio_sample2": audio2.hex()
    }))
    
    # Set context to wait for response
    self.set_context("AwaitingVerification")

def handle_verification_response(self, message):
    """Handle speaker verification response"""
    data = message.data
    is_same = data.get("is_same_speaker", False)
    similarity = data.get("similarity_score", 0.0)
    
    if is_same:
        self.speak(f"Yes, both samples are from the same speaker. Similarity score: {similarity:.2f}")
    else:
        self.speak(f"No, these are from different speakers. Similarity score: {similarity:.2f}")
```

### Task 7: Enhanced Error Handling
**Priority: HIGH | Estimated Time: 2 hours**

Improve the existing error handling with more specific cases:

```python
def handle_enrollment_response(self, message):
    """Enhanced enrollment response handler"""
    data = message.data
    status = data.get("status", "error")
    user_id = data.get("user_id", "Unknown")
    
    if status == "success":
        # Existing success handling...
        samples_processed = data.get("samples_processed", 0)
        
        # Get updated user count for better feedback
        self.bus.emit(Message("ovos.voiceid.list_users", {}))
        
        self.speak_dialog("enrollment_success", {
            "name": user_id,
            "samples": samples_processed,
            "total_users": 1  # Will be updated when user list response arrives
        })
        
    else:
        # Enhanced error handling
        error_message = data.get("message", "Unknown error")
        error_code = self.map_plugin_error_to_skill_error(error_message)
        
        LOG.error(f"Enrollment failed: {error_code} - {error_message}")
        
        # Provide specific guidance based on error type
        self.handle_enrollment_failed(error_code, error_message)
        
        # Store failure info for analytics
        self.enrollment_context["last_error"] = {
            "code": error_code,
            "message": error_message,
            "timestamp": datetime.now().isoformat()
        }

def map_plugin_error_to_skill_error(self, plugin_error: str) -> str:
    """Map plugin errors to skill error codes"""
    error_mapping = {
        "User ID is required": ErrorCodes.INVALID_NAME,
        "Audio samples are required": ErrorCodes.SAMPLE_COUNT_INSUFFICIENT,
        "Voice processor not initialized": ErrorCodes.PLUGIN_UNAVAILABLE,
        "User already exists": ErrorCodes.USER_EXISTS,
        "Audio quality too low": ErrorCodes.AUDIO_QUALITY_POOR,
        "Processing timeout": ErrorCodes.PROCESSING_FAILED,
    }
    
    for plugin_msg, skill_code in error_mapping.items():
        if plugin_msg.lower() in plugin_error.lower():
            return skill_code
    
    return ErrorCodes.PROCESSING_FAILED  # Default fallback
```

### Task 8: Plugin Health Monitoring
**Priority: MEDIUM | Estimated Time: 1 hour**

Add plugin health monitoring capabilities:

```python
def initialize(self):
    """Enhanced initialization with health monitoring"""
    LOG.info("Initializing OMVA Voice Enrollment Skill")
    self.setup_voice_id_integration()
    self.load_settings()
    
    # NEW: Plugin health monitoring
    self.plugin_healthy = False
    self.last_health_check = None
    self.schedule_event(self.check_plugin_health, 10.0, name="InitialHealthCheck")

def check_plugin_health(self, message=None):
    """Check if voice ID plugin is healthy"""
    self.health_check_pending = True
    self.health_check_start = time.time()
    
    # Request plugin stats to check health
    self.bus.emit(Message("ovos.voiceid.get_stats", {
        "health_check": True,
        "timestamp": time.time()
    }))
    
    # Set timeout for health check
    self.schedule_event(self.health_check_timeout, 5.0, name="HealthCheckTimeout")

def handle_stats_response(self, message):
    """Handle plugin statistics response"""
    data = message.data
    
    if hasattr(self, 'health_check_pending') and self.health_check_pending:
        # This is a health check response
        self.plugin_healthy = True
        self.health_check_pending = False
        self.last_health_check = time.time()
        
        plugin_version = data.get("plugin_version", "unknown")
        enrolled_users = data.get("enrolled_users", 0)
        
        LOG.info(f"Plugin healthy: v{plugin_version}, {enrolled_users} users enrolled")
        
        # Cancel timeout
        self.cancel_scheduled_event("HealthCheckTimeout")
    
    # Schedule next health check (every 5 minutes)
    self.schedule_event(self.check_plugin_health, 300.0, name="RegularHealthCheck")

def health_check_timeout(self, message):
    """Handle health check timeout"""
    if hasattr(self, 'health_check_pending') and self.health_check_pending:
        self.plugin_healthy = False
        self.health_check_pending = False
        
        LOG.warning("Plugin health check timed out - plugin may be unavailable")
        
        # Retry health check in 1 minute
        self.schedule_event(self.check_plugin_health, 60.0, name="RetryHealthCheck")
```

### Task 9: User Management Enhancements
**Priority: MEDIUM | Estimated Time: 1-2 hours**

Add user management intents:

```python
@intent_handler(
    IntentBuilder("DeleteVoiceProfile")
    .require("DeleteKeyword")
    .require("VoiceKeyword") 
    .optionally("UserName")
    .build()
)
def handle_delete_voice_profile(self, message):
    """Handle voice profile deletion"""
    user_name = message.data.get("UserName")
    
    if not user_name:
        user_name = self.get_response("Which user's voice profile should I delete?")
        
    if not user_name:
        self.speak("I need a user name to delete a voice profile")
        return
    
    # Confirm deletion
    confirm = self.ask_yesno(f"Are you sure you want to delete {user_name}'s voice profile?")
    
    if confirm == "yes":
        self.bus.emit(Message("ovos.voiceid.remove_user", {
            "user_id": user_name.lower().replace(" ", "_")
        }))
        self.set_context("AwaitingDeletionResponse")
        self.pending_deletion_user = user_name
    else:
        self.speak("Voice profile deletion cancelled")

def handle_deletion_response(self, message):
    """Handle user deletion response"""
    data = message.data
    if data.get("status") == "success":
        user_name = getattr(self, 'pending_deletion_user', 'User')
        self.speak(f"{user_name}'s voice profile has been deleted")
    else:
        error_msg = data.get("message", "Unknown error")
        self.speak(f"Failed to delete voice profile: {error_msg}")
    
    # Clean up
    if hasattr(self, 'pending_deletion_user'):
        delattr(self, 'pending_deletion_user')
```

### Task 10: Testing & Validation Scripts
**Priority: HIGH | Estimated Time: 2-3 hours**

Create comprehensive test scripts:

```python
# tests/test_integration.py
#!/usr/bin/env python3
"""Integration tests for OMVA Voice ID Plugin"""

import unittest
from unittest.mock import Mock, patch
import time
import tempfile
import wave
import numpy as np
from ovos_bus_client.message import Message

class TestVoiceIDIntegration(unittest.TestCase):
    
    def setUp(self):
        """Set up test fixtures"""
        from omva_skill_voice_enrollment import OMVAVoiceEnrollmentSkill
        
        self.skill = OMVAVoiceEnrollmentSkill()
        self.skill.bus = Mock()
        self.skill.initialize()
    
    def test_plugin_communication(self):
        """Test message bus communication with plugin"""
        # Test stats request
        self.skill.bus.emit.assert_called()
        
        # Simulate plugin response
        stats_message = Message("ovos.voiceid.stats.response", {
            "plugin_version": "0.0.1a1",
            "enrolled_users": 0,
            "total_processed": 0
        })
        
        self.skill.handle_stats_response(stats_message)
        self.assertTrue(self.skill.plugin_healthy)
    
    def test_audio_processing(self):
        """Test audio processing pipeline"""
        # Create test audio file
        test_audio = self.create_test_audio()
        
        # Test quality validation
        quality_result = self.skill.enhanced_audio_validation(test_audio)
        self.assertIn("quality_score", quality_result)
        self.assertIsInstance(quality_result["suitable"], bool)
    
    def test_enrollment_flow(self):
        """Test complete enrollment workflow"""
        # Simulate enrollment intent
        intent_message = Message("test.intent", {
            "utterance": "enroll my voice as test_user"
        })
        
        # Extract name
        name = self.skill.extract_user_name_from_utterance(intent_message.data["utterance"])
        self.assertEqual(name, "test_user")
        
        # Test enrollment start
        self.skill.start_enrollment_flow(name, "test")
        self.assertEqual(self.skill.enrollment_context["user_name"], name)
    
    def create_test_audio(self):
        """Create a test audio file"""
        temp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        
        # Generate test audio (1 second of sine wave)
        sample_rate = 16000
        duration = 1.0
        frequency = 440.0  # A4
        
        t = np.linspace(0, duration, int(sample_rate * duration))
        audio_data = (np.sin(2 * np.pi * frequency * t) * 32767).astype(np.int16)
        
        with wave.open(temp_file.name, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(audio_data.tobytes())
        
        return temp_file.name

if __name__ == "__main__":
    unittest.main()
```

## Implementation Priority Order (Mock-Based)

1. ✅ **Mock Testing Framework** - COMPLETED  
2. **Real-time Identification Handlers** (Task 3) - Add voice event handlers
3. **Enhanced Audio Processing** (Task 4) - Improve quality validation
4. **Error Handling Enhancement** (Task 5) - Better error mapping and recovery
5. **Speaker Verification** (Task 6) - Two-sample comparison feature
6. **User Management Enhancement** (Task 7) - Profile deletion, updates
7. **Comprehensive Testing** (Task 8) - Full workflow validation
8. **Performance Optimization** (Task 9) - Memory usage, cleanup

## Success Metrics (Mock-Validated)

- [ ] Mock plugin responds to all API calls correctly
- [ ] Enrollment workflow completes with mock responses  
- [ ] Voice identification events are handled properly
- [ ] Error messages are helpful and actionable
- [ ] System handles mock failures gracefully
- [ ] Audio processing validates quality effectively
- [ ] All workflows tested with mock framework

## Next Steps

1. **Start with Task 3** - Add real-time identification handlers
2. **Test with mock framework** - Validate each addition
3. **Iterate quickly** - No plugin dependency slows development
4. **Focus on user experience** - Dialog and error handling
