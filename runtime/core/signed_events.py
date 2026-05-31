"""Signed Events — HMAC-based event integrity verification

All events published to the bus must be signed to ensure:
  - Integrity: event has not been tampered with
  - Authenticity: event came from a trusted component
  - Non-repudiation: source cannot deny publishing the event

Event signature includes:
  - event_id (unique identifier)
  - event_type (classification)
  - timestamp (when event was created)
  - payload hash (SHA-256 of JSON-serialized payload)
  - signature (HMAC-SHA256 of all above)
"""

import hashlib
import hmac
import json
import logging
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

LOG = '[SignedEvents]'


class EventSigner:
    """Sign and verify events using HMAC-SHA256"""

    def __init__(self, hmac_secret: str):
        """
        Initialize with HMAC secret key.

        Args:
            hmac_secret: Secret key for HMAC (32+ bytes recommended)

        Raises:
            ValueError: If secret is too short
        """
        if not hmac_secret or len(hmac_secret) < 32:
            raise ValueError(
                f"HMAC secret must be 32+ chars (got {len(hmac_secret)})"
            )
        self.hmac_secret = hmac_secret.encode() if isinstance(hmac_secret, str) else hmac_secret

    def sign_event(
        self,
        event_type: str,
        payload: Dict[str, Any],
        event_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a signed event.

        Args:
            event_type: Event classification (e.g., 'task_completed', 'error')
            payload: Event data (will be JSON-serialized and hashed)
            event_id: Optional event ID; generated if not provided

        Returns:
            Signed event dict with signature field
        """
        if not event_id:
            event_id = str(uuid.uuid4())

        timestamp = datetime.now(timezone.utc).isoformat()

        # Serialize payload to canonical JSON (deterministic)
        payload_json = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        payload_hash = hashlib.sha256(payload_json.encode()).hexdigest()

        # Build message to sign: event_id | event_type | timestamp | payload_hash
        message = f"{event_id}|{event_type}|{timestamp}|{payload_hash}"

        # Compute HMAC signature
        signature = hmac.new(
            self.hmac_secret,
            message.encode(),
            hashlib.sha256
        ).hexdigest()

        return {
            'event_id': event_id,
            'event_type': event_type,
            'timestamp': timestamp,
            'payload': payload,
            'payload_hash': payload_hash,
            'signature': signature,
            'signed_at': timestamp,
        }

    def verify_event(self, event: Dict[str, Any]) -> bool:
        """
        Verify event signature.

        Args:
            event: Signed event dict (must include signature field)

        Returns:
            True if signature is valid

        Raises:
            ValueError: If event is malformed or signature is invalid
        """
        # Validate event structure
        required = ['event_id', 'event_type', 'timestamp', 'payload', 'signature']
        for field in required:
            if field not in event:
                raise ValueError(f"Event missing required field: {field}")

        # Reconstruct the message
        message = f"{event['event_id']}|{event['event_type']}|{event['timestamp']}|{event['payload_hash']}"

        # Verify payload_hash matches current payload
        payload_json = json.dumps(event['payload'], sort_keys=True, separators=(',', ':'))
        computed_hash = hashlib.sha256(payload_json.encode()).hexdigest()

        if computed_hash != event.get('payload_hash'):
            logger.warning(
                f"{LOG} Payload hash mismatch for event {event['event_id']}"
            )
            return False

        # Compute expected signature
        expected_signature = hmac.new(
            self.hmac_secret,
            message.encode(),
            hashlib.sha256
        ).hexdigest()

        # Constant-time comparison to prevent timing attacks
        if not hmac.compare_digest(expected_signature, event['signature']):
            logger.warning(
                f"{LOG} Invalid signature for event {event['event_id']}"
            )
            return False

        return True

    def batch_sign_events(
        self,
        events: list,
        event_type: str,
    ) -> list:
        """
        Sign multiple events in one call.

        Args:
            events: List of payloads (dicts)
            event_type: Event type for all events in batch

        Returns:
            List of signed event dicts
        """
        return [
            self.sign_event(event_type, event)
            for event in events
        ]

    def batch_verify_events(self, events: list) -> Dict[str, Any]:
        """
        Verify multiple events and report results.

        Args:
            events: List of signed event dicts

        Returns:
            {
                'valid': [event_id, ...],
                'invalid': [event_id, ...],
                'summary': { 'total': int, 'valid': int, 'invalid': int }
            }
        """
        valid = []
        invalid = []

        for event in events:
            try:
                if self.verify_event(event):
                    valid.append(event['event_id'])
                else:
                    invalid.append(event['event_id'])
            except (ValueError, KeyError) as e:
                logger.warning(f"{LOG} Event verification error: {e}")
                event_id = event.get('event_id', '<unknown>')
                invalid.append(event_id)

        return {
            'valid': valid,
            'invalid': invalid,
            'summary': {
                'total': len(events),
                'valid': len(valid),
                'invalid': len(invalid),
            },
        }


class SignedEventValidator:
    """Middleware to validate signed events before processing"""

    def __init__(self, signer: EventSigner):
        self.signer = signer

    def validate_and_process(self, event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Validate event signature and return cleaned payload.

        Args:
            event: Signed event dict

        Returns:
            Event payload if valid, None if invalid

        Raises:
            ValueError: If event is malformed
        """
        try:
            if not self.signer.verify_event(event):
                logger.error(
                    f"{LOG} Event validation failed: {event.get('event_id', '<unknown>')}"
                )
                return None
            return event
        except ValueError as e:
            logger.error(f"{LOG} Event validation error: {e}")
            return None

    def wrap_consumer(self, consumer_fn):
        """
        Decorator to validate events before they reach consumer.

        Usage:
            validator = SignedEventValidator(signer)
            @validator.wrap_consumer
            def handle_task_event(event):
                print(f"Task completed: {event['payload']}")

        Args:
            consumer_fn: Function that processes event payload

        Returns:
            Wrapper function
        """
        def wrapper(event):
            validated = self.validate_and_process(event)
            if validated:
                return consumer_fn(validated['payload'])
            else:
                logger.warning(
                    f"{LOG} Dropping invalid event: {event.get('event_id')}"
                )
                return None
        return wrapper


# Global signer instance (initialize in main)
_signer: Optional[EventSigner] = None


def init_event_signer(hmac_secret: str) -> EventSigner:
    """Initialize global event signer."""
    global _signer
    _signer = EventSigner(hmac_secret)
    return _signer


def get_event_signer() -> EventSigner:
    """Get global event signer."""
    if _signer is None:
        raise RuntimeError(
            "Event signer not initialized. Call init_event_signer() first."
        )
    return _signer
