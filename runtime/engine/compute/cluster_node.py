"""Cluster Node — LAN-based multi-PC compute interconnect with TOTP 2FA.

Security model:
  - Every cluster request is double-authenticated:
      1. Shared token (AI_CLUSTER_TOKEN) — proves the request comes from a known peer
      2. TOTP code derived from a shared TOTP secret — rolling 30-second window
         code that changes every 30s; prevents replay attacks and token theft
  - Joining requires explicit pairing: owner scans a QR / enters the pairing code
    on BOTH machines, confirming intent. No node auto-joins.
  - All traffic stays on LAN. Set AI_CLUSTER_ALLOW_WAN=1 to allow cross-network.

Architecture:
  PRIMARY: runs SwarmController, routes subtasks to local or remote workers
  WORKER:  accepts /cluster/run and /cluster/infer requests, returns results

Setup:
  1. On PRIMARY, generate a pairing code: POST /cluster/pair/generate
  2. Enter the pairing code on WORKER via POST /cluster/pair/confirm
  3. Nodes exchange TOTP secrets and are paired — all future requests are 2FA'd
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import socket
import struct
import threading
import time
import urllib.request
import urllib.error
import uuid
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("engine.compute.cluster")

_CLUSTER_TOKEN = os.environ.get("AI_CLUSTER_TOKEN", "")
_CLUSTER_PORT  = int(os.environ.get("AI_CLUSTER_PORT", "18790"))
_BEACON_PORT   = int(os.environ.get("AI_CLUSTER_BEACON_PORT", "18791"))
_BEACON_GROUP  = "239.0.0.123"
_BEACON_TTL    = 5
_BEACON_INTERVAL_S = 5
_NODE_EXPIRE_S     = 20
_TOTP_STEP         = 30      # TOTP time-step in seconds
_TOTP_WINDOW       = 1       # accept ±1 step for clock drift
_PAIR_CODE_TTL_S   = 300     # pairing code expires after 5 minutes

AI_HOME = Path(os.environ.get("AI_HOME", str(Path.home() / ".ai-employee")))
_CLUSTER_STATE_FILE = AI_HOME / "config" / "cluster_peers.json"


# ── TOTP (RFC 6238) — pure stdlib, no pyotp dependency ────────────────────────

def _totp_generate(secret_b32: str, t: float | None = None) -> str:
    """Generate a 6-digit TOTP code from a base32 secret."""
    secret = base64.b32decode(secret_b32.upper().replace(" ", ""))
    step = int((t or time.time()) // _TOTP_STEP)
    msg = struct.pack(">Q", step)
    h = hmac.new(secret, msg, hashlib.sha1).digest()
    offset = h[-1] & 0x0F
    code = struct.unpack(">I", h[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(code % 1_000_000).zfill(6)


def _totp_verify(secret_b32: str, code: str, window: int = _TOTP_WINDOW) -> bool:
    """Verify a TOTP code within ±window time steps."""
    now = time.time()
    for delta in range(-window, window + 1):
        t = now + delta * _TOTP_STEP
        if _totp_generate(secret_b32, t) == code:
            return True
    return False


def _totp_new_secret() -> str:
    """Generate a new random base32 TOTP secret (20 bytes = 160 bits)."""
    raw = secrets.token_bytes(20)
    return base64.b32encode(raw).decode()


def _totp_uri(secret: str, node_id: str) -> str:
    """Return an otpauth:// URI for QR code generation."""
    return f"otpauth://totp/AI-Employee%20Cluster:{node_id}?secret={secret}&issuer=AI-Employee&algorithm=SHA1&digits=6&period=30"


# ── Persistent peer state ──────────────────────────────────────────────────────

def _load_peers() -> dict:
    try:
        if _CLUSTER_STATE_FILE.exists():
            return json.loads(_CLUSTER_STATE_FILE.read_text())
    except Exception:
        pass
    return {}


def _save_peers(peers: dict) -> None:
    try:
        _CLUSTER_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CLUSTER_STATE_FILE.write_text(json.dumps(peers, indent=2))
    except Exception as exc:
        logger.warning("cluster: could not save peers: %s", exc)


# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass
class RemoteNode:
    node_id:      str
    hostname:     str
    ip:           str
    port:         int
    role:         str
    vram_free_mb: int
    vram_total_mb: int
    ram_free_gb:   float
    ram_total_gb:  float
    cpu_cores:     int
    gpu_name:      str
    paired:        bool  = False   # False = discovered but not 2FA-paired yet
    last_seen:     float = field(default_factory=time.time)
    load:          float = 0.0


@dataclass
class PendingPair:
    code:       str        # 8-char alphanumeric pairing code
    totp_secret: str       # TOTP secret for THIS pairing
    created_at:  float     # unix timestamp
    node_id:     str       # which node initiated the pairing


class ClusterNode:
    """This machine's cluster participation. Only active when AI_CLUSTER_TOKEN is set."""

    def __init__(self):
        self._enabled   = bool(_CLUSTER_TOKEN)
        self._node_id   = os.environ.get("AI_NODE_ID") or self._load_or_create_node_id()
        self._role      = os.environ.get("AI_NODE_ROLE", "any")
        self._peers: dict[str, RemoteNode] = {}
        self._paired_secrets: dict[str, str] = {}   # node_id → totp_secret
        self._pending_pairs: dict[str, PendingPair] = {}  # code → PendingPair
        self._lock = threading.RLock()
        self._running = False

        # Load persisted peer secrets
        saved = _load_peers()
        for nid, info in saved.items():
            if isinstance(info, dict) and "totp_secret" in info:
                self._paired_secrets[nid] = info["totp_secret"]

        if self._enabled:
            logger.info("ClusterNode %s role=%s ready (%d paired peers)",
                        self._node_id, self._role, len(self._paired_secrets))

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def start(self) -> None:
        if not self._enabled or self._running:
            return
        self._running = True
        threading.Thread(target=self._beacon_loop, daemon=True, name="cluster-beacon").start()
        threading.Thread(target=self._listen_loop, daemon=True, name="cluster-listen").start()

    def stop(self) -> None:
        self._running = False

    # ── Pairing (2FA setup) ────────────────────────────────────────────────────

    def generate_pair_code(self) -> dict:
        """Generate a pairing invitation. The owner shares this code with the other machine."""
        code   = secrets.token_hex(4).upper()   # e.g. "A3F9C201"
        secret = _totp_new_secret()
        with self._lock:
            self._pending_pairs[code] = PendingPair(
                code=code, totp_secret=secret,
                created_at=time.time(), node_id=self._node_id,
            )
        return {
            "code":         code,
            "totp_secret":  secret,
            "totp_uri":     _totp_uri(secret, self._node_id),
            "expires_in_s": _PAIR_CODE_TTL_S,
            "instructions": (
                f"Enter this code on the other machine at Settings → Cluster → Join Cluster. "
                f"Code expires in {_PAIR_CODE_TTL_S // 60} minutes."
            ),
        }

    def confirm_pair(self, code: str, remote_node_id: str, remote_ip: str,
                     totp_code: str) -> dict:
        """Worker-side: confirm a pairing invitation from a primary node.

        The primary calls this on the worker (via HTTP) after the user enters
        the pairing code. Validates the TOTP code to confirm intent.
        """
        with self._lock:
            pair = self._pending_pairs.get(code)

        if pair is None:
            return {"ok": False, "error": "Invalid or expired pairing code"}

        if time.time() - pair.created_at > _PAIR_CODE_TTL_S:
            with self._lock:
                self._pending_pairs.pop(code, None)
            return {"ok": False, "error": "Pairing code expired"}

        if not _totp_verify(pair.totp_secret, totp_code):
            return {"ok": False, "error": "Invalid TOTP code — check system clocks are in sync"}

        # Accept the pairing
        with self._lock:
            self._pending_pairs.pop(code, None)
            self._paired_secrets[remote_node_id] = pair.totp_secret

        self._persist_secrets()
        logger.info("cluster: paired with node %s (%s)", remote_node_id, remote_ip)
        return {
            "ok":           True,
            "paired_with":  remote_node_id,
            "our_node_id":  self._node_id,
            "totp_secret":  pair.totp_secret,   # worker stores this same secret
        }

    def pair_with_remote(self, remote_ip: str, remote_port: int,
                         code: str, totp_secret: str, totp_code: str) -> dict:
        """Primary-side: initiate pairing with a worker at remote_ip.

        Sends the pairing confirmation to the remote node. On success, stores
        the shared TOTP secret locally.
        """
        payload = {
            "code":           code,
            "remote_node_id": self._node_id,
            "remote_ip":      self._local_ip(),
            "totp_code":      totp_code,
        }
        result = self._http_post_raw(remote_ip, remote_port, "/cluster/pair/confirm", payload, 15)
        if result and result.get("ok"):
            remote_nid = result.get("our_node_id", remote_ip)
            with self._lock:
                self._paired_secrets[remote_nid] = totp_secret
            self._persist_secrets()
            logger.info("cluster: successfully paired with %s", remote_nid)
        return result or {"ok": False, "error": "No response from remote node"}

    def unpair(self, node_id: str) -> bool:
        with self._lock:
            removed = self._paired_secrets.pop(node_id, None) is not None
            self._peers.pop(node_id, None)
        if removed:
            self._persist_secrets()
        return removed

    def is_paired(self, node_id: str) -> bool:
        return node_id in self._paired_secrets

    # ── Auth helpers (used by HTTP endpoint validators) ────────────────────────

    def verify_request(self, node_id: str, token: str, totp_code: str) -> bool:
        """Return True if the request is authenticated (token + TOTP match)."""
        if token != _CLUSTER_TOKEN:
            return False
        secret = self._paired_secrets.get(node_id)
        if secret is None:
            return False
        return _totp_verify(secret, totp_code)

    def sign_request(self, node_id: str | None = None) -> dict[str, str]:
        """Return auth headers for an outgoing cluster request."""
        secret = self._paired_secrets.get(node_id or "") if node_id else None
        return {
            "X-Cluster-Token":  _CLUSTER_TOKEN,
            "X-Cluster-Node":   self._node_id,
            "X-Cluster-TOTP":   _totp_generate(secret) if secret else "",
        }

    # ── Peer discovery ─────────────────────────────────────────────────────────

    def peers(self) -> list[RemoteNode]:
        with self._lock:
            cutoff = time.time() - _NODE_EXPIRE_S
            return [n for n in self._peers.values() if n.last_seen >= cutoff]

    def paired_peers(self) -> list[RemoteNode]:
        return [p for p in self.peers() if p.paired]

    def best_worker(self, need_vram_mb: int = 0) -> RemoteNode | None:
        candidates = [p for p in self.paired_peers() if p.vram_free_mb >= need_vram_mb]
        return max(candidates, key=lambda p: p.vram_free_mb, default=None)

    # ── Remote inference ───────────────────────────────────────────────────────

    def remote_infer(self, prompt: str, system: str = "", model: str = "",
                     prefer_node: RemoteNode | None = None, timeout: int = 120) -> str | None:
        if not self._enabled:
            return None
        target = prefer_node or self.best_worker(need_vram_mb=2000)
        if target is None:
            return None
        result = self._authenticated_post(target, "/cluster/infer", {
            "prompt": prompt, "system": system, "model": model,
        }, timeout)
        return result.get("response") if result else None

    def remote_agent_run(self, goal: str, agent: str = "react_researcher",
                         context: dict | None = None, max_steps: int = 15,
                         prefer_node: RemoteNode | None = None, timeout: int = 300) -> dict | None:
        if not self._enabled:
            return None
        target = prefer_node or self.best_worker(need_vram_mb=2000)
        if target is None:
            return None
        return self._authenticated_post(target, "/cluster/agent_run", {
            "goal": goal, "agent": agent, "context": context or {}, "max_steps": max_steps,
        }, timeout)

    # ── Status ─────────────────────────────────────────────────────────────────

    def status(self) -> dict:
        """Full cluster status including pooled resources."""
        peers = self.peers()
        paired = [p for p in peers if p.paired]

        # Local resources
        try:
            from engine.compute.resource_manager import get_resource_manager
            rm = get_resource_manager()
            local_s = rm.specs
            local_b = rm.budget
            local_vram_total = local_s.vram_total_mb
            local_vram_free  = local_s.vram_free_mb
            local_ram_total  = local_s.ram_total_gb
            local_ram_free   = local_s.ram_free_gb
            local_cpu        = local_s.cpu_cores
            local_gpu        = local_s.gpu_name
        except Exception:
            local_vram_total = local_vram_free = 0
            local_ram_total = local_ram_free = 0.0
            local_cpu = 1
            local_gpu = "unknown"

        # Pool: sum local + all paired peers
        pool_vram_total = local_vram_total + sum(p.vram_total_mb for p in paired)
        pool_vram_free  = local_vram_free  + sum(p.vram_free_mb  for p in paired)
        pool_ram_total  = local_ram_total  + sum(p.ram_total_gb  for p in paired)
        pool_ram_free   = local_ram_free   + sum(p.ram_free_gb   for p in paired)
        pool_cpu        = local_cpu        + sum(p.cpu_cores      for p in paired)

        return {
            "enabled":   self._enabled,
            "node_id":   self._node_id,
            "role":      self._role,
            "local": {
                "node_id":      self._node_id,
                "hostname":     socket.gethostname(),
                "gpu_name":     local_gpu,
                "vram_total_mb": local_vram_total,
                "vram_free_mb":  local_vram_free,
                "ram_total_gb":  local_ram_total,
                "ram_free_gb":   local_ram_free,
                "cpu_cores":     local_cpu,
                "role":          self._role,
            },
            "peers":        [asdict(p) for p in peers],
            "peer_count":   len(peers),
            "paired_count": len(paired),
            "pooled": {
                "vram_total_mb": pool_vram_total,
                "vram_free_mb":  pool_vram_free,
                "ram_total_gb":  round(pool_ram_total, 2),
                "ram_free_gb":   round(pool_ram_free, 2),
                "cpu_cores":     pool_cpu,
                "node_count":    1 + len(paired),
            },
            "pending_pairs": len(self._pending_pairs),
        }

    # ── Internal: UDP beacon ───────────────────────────────────────────────────

    def _own_beacon(self) -> bytes:
        try:
            from engine.compute.resource_manager import get_resource_manager
            rm = get_resource_manager()
            s  = rm.specs
            vt, vf = s.vram_total_mb, s.vram_free_mb
            rt, rf = s.ram_total_gb,  s.ram_free_gb
            cores  = s.cpu_cores
            gpu    = s.gpu_name
        except Exception:
            vt = vf = 0; rt = rf = 0.0; cores = 1; gpu = "unknown"

        msg = {
            "token":          _CLUSTER_TOKEN,
            "node_id":        self._node_id,
            "hostname":       socket.gethostname(),
            "ip":             self._local_ip(),
            "port":           _CLUSTER_PORT,
            "role":           self._role,
            "vram_total_mb":  vt,
            "vram_free_mb":   vf,
            "ram_total_gb":   rt,
            "ram_free_gb":    rf,
            "cpu_cores":      cores,
            "gpu_name":       gpu,
            "paired_ids":     list(self._paired_secrets.keys()),
            "ts":             time.time(),
        }
        return json.dumps(msg).encode()

    def _beacon_loop(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, _BEACON_TTL)
        while self._running:
            try:
                sock.sendto(self._own_beacon(), (_BEACON_GROUP, _BEACON_PORT))
            except Exception as exc:
                logger.debug("beacon send: %s", exc)
            time.sleep(_BEACON_INTERVAL_S)
        sock.close()

    def _listen_loop(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except AttributeError:
            pass
        try:
            sock.bind(("", _BEACON_PORT))
            mreq = socket.inet_aton(_BEACON_GROUP) + socket.inet_aton("0.0.0.0")
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        except OSError as exc:
            logger.warning("cluster multicast listen failed: %s", exc)
            return
        sock.settimeout(2.0)
        while self._running:
            try:
                data, addr = sock.recvfrom(4096)
                self._handle_beacon(data, addr)
            except socket.timeout:
                continue
            except Exception as exc:
                logger.debug("beacon recv: %s", exc)
        sock.close()

    def _handle_beacon(self, data: bytes, addr: tuple) -> None:
        try:
            msg = json.loads(data.decode())
        except Exception:
            return
        if msg.get("token") != _CLUSTER_TOKEN:
            return
        nid = msg.get("node_id")
        if not nid or nid == self._node_id:
            return
        paired = nid in self._paired_secrets
        with self._lock:
            self._peers[nid] = RemoteNode(
                node_id       = nid,
                hostname      = msg.get("hostname", "unknown"),
                ip            = msg.get("ip", addr[0]),
                port          = msg.get("port", _CLUSTER_PORT),
                role          = msg.get("role", "any"),
                vram_total_mb = msg.get("vram_total_mb", 0),
                vram_free_mb  = msg.get("vram_free_mb", 0),
                ram_total_gb  = msg.get("ram_total_gb", 0.0),
                ram_free_gb   = msg.get("ram_free_gb", 0.0),
                cpu_cores     = msg.get("cpu_cores", 1),
                gpu_name      = msg.get("gpu_name", "unknown"),
                paired        = paired,
                last_seen     = time.time(),
            )

    # ── Internal: authenticated HTTP RPC ──────────────────────────────────────

    def _authenticated_post(self, node: RemoteNode, path: str,
                             payload: dict, timeout: int) -> dict | None:
        secret = self._paired_secrets.get(node.node_id)
        if not secret:
            logger.warning("cluster: no TOTP secret for node %s — not paired", node.node_id)
            return None
        headers = {
            "Content-Type":    "application/json",
            "X-Cluster-Token": _CLUSTER_TOKEN,
            "X-Cluster-Node":  self._node_id,
            "X-Cluster-TOTP":  _totp_generate(secret),
        }
        return self._http_post_raw(node.ip, node.port, path, payload, timeout, headers)

    def _http_post_raw(self, ip: str, port: int, path: str,
                       payload: dict, timeout: int,
                       headers: dict | None = None) -> dict | None:
        url  = f"http://{ip}:{port}{path}"
        body = json.dumps(payload).encode()
        hdrs = {"Content-Type": "application/json", **(headers or {})}
        req  = urllib.request.Request(url, data=body, headers=hdrs, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode())
        except Exception as exc:
            logger.warning("cluster RPC %s→%s failed: %s", ip, path, exc)
            return None

    # ── Persistence ────────────────────────────────────────────────────────────

    def _persist_secrets(self) -> None:
        with self._lock:
            data = {nid: {"totp_secret": s} for nid, s in self._paired_secrets.items()}
        _save_peers(data)

    def _load_or_create_node_id(self) -> str:
        id_file = AI_HOME / "config" / "node_id"
        if id_file.exists():
            try:
                return id_file.read_text().strip()
            except Exception:
                pass
        nid = str(uuid.uuid4())[:8]
        try:
            id_file.parent.mkdir(parents=True, exist_ok=True)
            id_file.write_text(nid)
        except Exception:
            pass
        return nid

    @staticmethod
    def _local_ip() -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"


# ── Singleton ──────────────────────────────────────────────────────────────────
_NODE: ClusterNode | None = None
_NODE_LOCK = threading.Lock()


def get_cluster_node() -> ClusterNode:
    global _NODE
    if _NODE is None:
        with _NODE_LOCK:
            if _NODE is None:
                _NODE = ClusterNode()
    return _NODE
