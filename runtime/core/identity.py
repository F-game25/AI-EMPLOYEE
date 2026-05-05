"""
Identity generator — creates per-install unique identity.
Generates tenant_id, instance_name, color_palette on first boot.
Stores at ~/.ai-employee/identity.json
"""
import json
import uuid
import colorsys
import random
import os
from datetime import datetime
from pathlib import Path


# Seeded wordlist for instance names (mythology + tech suffixes)
MYTHOLOGIES = [
    "Aurora", "Helios", "Artemis", "Hermes", "Athena", "Apollo", "Nova", "Zenith",
    "Orion", "Cassiopeia", "Andromeda", "Vega", "Sirius", "Polaris", "Rigel"
]

SUFFIXES = [
    "Prime", "Elite", "Core", "Nexus", "Gate", "Edge", "Pulse", "Flux",
    "Forge", "Storm", "Surge", "Cascade", "Epoch", "Void", "Crown"
]


def hsl_to_hex(h, s, l):
    """Convert HSL (0-1 range) to hex color."""
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return "#{:02x}{:02x}{:02x}".format(int(r * 255), int(g * 255), int(b * 255))


def generate_instance_name():
    """Generate a seeded instance name from mythology + suffix."""
    return f"{random.choice(MYTHOLOGIES)}-{random.choice(SUFFIXES)}"


def generate_color_palette():
    """Generate HSL-randomized premium color palette."""
    hue = random.uniform(0.7, 1.0)  # purples/blues (premium range)
    saturation = random.uniform(0.6, 0.9)

    return {
        "primary": hsl_to_hex(hue, saturation, random.uniform(0.35, 0.45)),
        "accent": hsl_to_hex(hue, saturation, random.uniform(0.5, 0.6)),
        "secondary": hsl_to_hex((hue + 0.15) % 1.0, saturation * 0.7, random.uniform(0.35, 0.45))
    }


def generate_identity(identity_file=None):
    """
    Generate new identity if not exists.
    Returns identity dict.
    """
    if identity_file is None:
        identity_file = Path.home() / ".ai-employee" / "identity.json"
    else:
        identity_file = Path(identity_file)

    # If already exists, load and return
    if identity_file.exists():
        with open(identity_file) as f:
            return json.load(f)

    # Generate new identity
    identity = {
        "tenant_id": f"tnt_{uuid.uuid4().hex[:12]}",
        "instance_name": generate_instance_name(),
        "user_chosen": None,
        "color_palette": generate_color_palette(),
        "voice_preset": "professional",
        "emergent": {
            "vocabulary_signature": [],
            "favorite_agents": [],
            "work_pattern": None,
            "tone_drift": 0.0
        },
        "created_at": datetime.utcnow().isoformat() + "Z",
        "evolution_log": []
    }

    # Write to file
    identity_file.parent.mkdir(parents=True, exist_ok=True)
    with open(identity_file, 'w') as f:
        json.dump(identity, f, indent=2)

    return identity


def load_identity(identity_file=None):
    """Load existing identity from file."""
    if identity_file is None:
        identity_file = Path.home() / ".ai-employee" / "identity.json"
    else:
        identity_file = Path(identity_file)

    if not identity_file.exists():
        return None

    with open(identity_file) as f:
        return json.load(f)


def finalize_identity(user_chosen=None, voice_preset=None, color_palette=None, identity_file=None):
    """
    Update identity with user choices from onboarding.
    Called after user completes onboarding modal.
    """
    if identity_file is None:
        identity_file = Path.home() / ".ai-employee" / "identity.json"
    else:
        identity_file = Path(identity_file)

    identity = load_identity(identity_file)
    if not identity:
        identity = generate_identity(identity_file)

    # Apply user choices
    if user_chosen:
        identity["user_chosen"] = user_chosen
    if voice_preset:
        identity["voice_preset"] = voice_preset
    if color_palette:
        identity["color_palette"] = color_palette

    # Log the finalization event
    identity["evolution_log"].append({
        "event": "identity_finalized",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "user_chosen": user_chosen,
        "voice_preset": voice_preset
    })

    # Write back
    with open(identity_file, 'w') as f:
        json.dump(identity, f, indent=2)

    return identity


if __name__ == "__main__":
    # Quick test
    ident = generate_identity()
    print(f"Generated identity: {ident['instance_name']}")
    print(f"Tenant: {ident['tenant_id']}")
    print(f"Colors: {ident['color_palette']}")
