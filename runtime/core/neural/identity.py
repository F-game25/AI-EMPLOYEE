"""Per-machine identity — generates a stable UUID on first run.

Stored at ~/.ai-employee/state/identity.json.
Each machine gets a unique name, ID, and personality_seed.
"""
import hashlib, json, os, platform, socket, time, uuid
from pathlib import Path

NAMES = [
    'Athena', 'Orion', 'Nova', 'Atlas', 'Echo', 'Cipher',
    'Nexus', 'Pulse', 'Axiom', 'Vega', 'Lynx', 'Helix',
]

def _path() -> Path:
    base = Path(os.getenv('AI_HOME', Path.home() / '.ai-employee'))
    return base / 'state' / 'identity.json'

def _fingerprint() -> str:
    h = hashlib.sha256()
    h.update(socket.gethostname().encode())
    h.update(platform.processor().encode())
    h.update(str(os.cpu_count()).encode())
    return h.hexdigest()[:16]

def get_identity() -> dict:
    """Get or create the machine identity."""
    p = _path()
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            pass
    # First boot: generate identity
    fp = _fingerprint()
    name_idx = int(fp[:4], 16) % len(NAMES)
    identity = {
        'id': str(uuid.uuid4()),
        'fingerprint': fp,
        'name': NAMES[name_idx],
        'hostname': socket.gethostname(),
        'created_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'personality_seed': int(fp[4:8], 16),
        'first_boot': True,
    }
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(identity, indent=2))
    return identity
