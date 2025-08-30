# OMVA Skill Voice Enrollment

Natural voice interface for enrolling user voices with semantic intent recognition and SpeechBrain integration.

## Description

This skill provides a conversational interface for voice enrollment in the OMVA voice identification system. Users can naturally express their intent to enroll their voice using various phrases like:

- "Enroll my voice"
- "Save my voice"  
- "Remember me"
- "Enroll my voice as John"
- "Register my voice as Mary Smith"
- "Learn my voice"
- "Add my voice to the system"

## Features

- **Semantic Intent Recognition**: Understands 25+ variations of enrollment requests
- **Flexible Name Collection**: Supports both explicit names ("as John") and prompted name collection
- **Confirmation Dialog**: Optional confirmation before starting enrollment process
- **Robust Name Validation**: Validates and cleans user names with proper capitalization
- **Multi-turn Conversations**: Maintains context across enrollment steps
- **Error Recovery**: Provides helpful guidance for audio quality issues and failures
- **SpeechBrain Integration**: Uses ECAPA-TDNN model for voice identification

## Usage Examples

### Basic Enrollment
```
User: "Enroll my voice"
Assistant: "I'd be happy to help you enroll your voice! This will help me recognize and identify you in the future. Would you like to proceed?"
User: "Yes"
Assistant: "What name should I use for your voice profile?"
User: "John"
Assistant: "Perfect! I'll use the name John for your voice profile. Great! Let's collect 3 voice samples now."
```

### Enrollment with Name
```
User: "Save my voice as Mary Smith"
Assistant: "I'd be happy to enroll your voice, Mary Smith! This will help me recognize and identify you in the future. Should I proceed with the enrollment?"
User: "Yes" 
Assistant: "Great Mary Smith! Let's collect 3 voice samples now. I'll tell you what to say for each one."
```

## Requirements

### Python Dependencies
- ovos-workshop>=0.0.15,<4.0.0
- ovos-utils>=0.0.32,<1.0.0
- ovos-bus-client>=0.0.7,<2.0.0
- adapt-parser>=0.3.4
- requests>=2.28.0

### Skill Dependencies
- ovos-audio-transformer-plugin-omva-voiceid

## Configuration

The skill can be configured through the settings interface:

- **target_samples**: Number of voice samples to collect (default: 3)
- **min_audio_duration**: Minimum audio duration in seconds (default: 3.0)
- **max_audio_duration**: Maximum audio duration in seconds (default: 10.0)
- **quality_threshold**: Audio quality threshold 0.0-1.0 (default: 0.7)
- **confirmation_required**: Whether to require confirmation (default: true)
- **replace_existing_profiles**: Allow replacing existing profiles (default: false)

## Intent Examples

The skill recognizes these types of enrollment requests:

### Primary Intents
- "enroll my voice"
- "save my voice"
- "remember me" 
- "register my voice"
- "learn my voice"
- "add my voice"
- "set up voice recognition"

### With Name Specification
- "enroll my voice as [Name]"
- "save my voice as [Name]"
- "remember me as [Name]"
- "register my voice as [Name]"

### Confirmation Responses
- "yes", "yeah", "sure", "okay", "proceed"
- "no", "cancel", "stop", "abort"

## Installation

1. Install the skill:
```bash
pip install omva-skill-voice-enrollment
```

2. Ensure the OMVA voice identification plugin is installed:
```bash
pip install ovos-audio-transformer-plugin-omva-voiceid
```

3. The skill will be automatically loaded by OVOS.

## Development

### Directory Structure
```
omva-skill-voice-enrollment/
├── __init__.py                     # Main skill implementation
├── skill.json                     # Skill metadata  
├── setup.py                       # Package configuration
├── version.py                     # Version information
├── settingsmeta.json              # Settings configuration
├── requirements.txt               # Python dependencies
├── README.md                      # Documentation
├── locale/                        # Localization files
│   └── en-us/
│       ├── dialog/               # Response templates
│       │   ├── enrollment_start_with_name.dialog
│       │   ├── enrollment_start_no_name.dialog
│       │   ├── enrollment_cancelled.dialog
│       │   ├── request_name.dialog
│       │   ├── ready_for_samples.dialog
│       │   ├── name_confirmed.dialog
│       │   └── name_invalid.dialog
│       └── vocab/                # Intent definitions
│           ├── EnrollVoice.intent
│           ├── EnrollKeyword.entity
│           ├── VoiceKeyword.entity
│           ├── RememberKeyword.entity
│           ├── MeKeyword.entity
│           ├── YesKeyword.entity
│           └── NoKeyword.entity
└── validate.py                   # Validation script
```

### Testing

Run the validation script to test the skill implementation:

```bash
cd omva-skill-voice-enrollment
python validate.py
```

## License

Apache License 2.0

## Credits

- OMVA Team

## Integration

This skill integrates with:
- **OVOS Framework**: Core skill platform
- **SpeechBrain**: ECAPA-TDNN voice identification model  
- **OMVA Voice ID Plugin**: Audio transformer for voice processing
- **OVOS Message Bus**: Inter-component communication