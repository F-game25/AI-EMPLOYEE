// Nexus OS — desktop shell (Aethernus Nexus)
//
// M1 goal: never show a white screen. The splash window appears instantly and
// streams live boot phases + logs. The Rust shell spawns the Node gateway +
// Python AI backend with the correct environment (incl. JWT_SECRET_KEY, which
// backend/server.js requires or it fatals), then GATES on /api/health before
// creating + showing the dashboard window. Any failure shows a diagnostics
// view with Retry / Open Logs instead of a dead WebView.

use std::collections::VecDeque;
use std::io::Write as _;
use std::path::{Path, PathBuf};
use std::process::Stdio;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use serde_json::json;
use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Emitter, Manager, RunEvent};
use tokio::io::{AsyncBufReadExt, AsyncRead, BufReader};
use tokio::net::TcpStream;
use tokio::process::{Child, Command};
use tokio::time::{sleep, timeout};

const MAX_LOG_LINES: usize = 200;

struct ChildProc {
    name: String,
    child: Child,
}

struct AppState {
    repo_dir: PathBuf,
    app_home: PathBuf,
    node_port: u16,
    python_port: u16,
    children: Mutex<Vec<ChildProc>>,
    logs: Mutex<VecDeque<String>>,
    phases_done: Mutex<Vec<String>>,
    failed: Mutex<Option<String>>,
    booting: Mutex<bool>,
}

type SharedState = Arc<AppState>;

// ── Path / env resolution (no hardcoded paths) ───────────────────────────────

fn resolve_repo_dir() -> PathBuf {
    if let Ok(d) = std::env::var("AI_EMPLOYEE_REPO_DIR") {
        let p = PathBuf::from(d);
        if p.join("backend/server.js").exists() {
            return p;
        }
    }
    let mut roots: Vec<PathBuf> = Vec::new();
    if let Ok(exe) = std::env::current_exe() {
        if let Some(p) = exe.parent() {
            roots.push(p.to_path_buf());
        }
    }
    if let Ok(cwd) = std::env::current_dir() {
        roots.push(cwd);
    }
    for start in roots {
        let mut cur: Option<&Path> = Some(start.as_path());
        while let Some(d) = cur {
            if d.join("backend/server.js").exists() && d.join("frontend/dist/index.html").exists() {
                return d.to_path_buf();
            }
            cur = d.parent();
        }
    }
    std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."))
}

fn resolve_app_home() -> PathBuf {
    for k in ["AI_EMPLOYEE_HOME", "AI_HOME"] {
        if let Ok(v) = std::env::var(k) {
            if !v.is_empty() {
                return PathBuf::from(v);
            }
        }
    }
    let home = std::env::var("HOME")
        .or_else(|_| std::env::var("USERPROFILE"))
        .unwrap_or_else(|_| ".".into());
    PathBuf::from(home).join(".ai-employee")
}

fn ensure_dirs(app_home: &Path) {
    for d in ["state", "logs", "run", "config"] {
        let _ = std::fs::create_dir_all(app_home.join(d));
    }
}

fn env_port(keys: &[&str], default: u16) -> u16 {
    for k in keys {
        if let Ok(v) = std::env::var(k) {
            if let Ok(n) = v.parse::<u16>() {
                if n > 0 {
                    return n;
                }
            }
        }
    }
    default
}

fn load_dotenv(path: &Path) -> Vec<(String, String)> {
    let mut out = Vec::new();
    if let Ok(txt) = std::fs::read_to_string(path) {
        for line in txt.lines() {
            let t = line.trim();
            if t.is_empty() || t.starts_with('#') {
                continue;
            }
            if let Some(i) = t.find('=') {
                let k = t[..i].trim().to_string();
                let mut v = t[i + 1..].trim().to_string();
                if (v.starts_with('"') && v.ends_with('"') && v.len() >= 2)
                    || (v.starts_with('\'') && v.ends_with('\'') && v.len() >= 2)
                {
                    v = v[1..v.len() - 1].to_string();
                }
                if !k.is_empty() {
                    out.push((k, v));
                }
            }
        }
    }
    out
}

fn rand_hex(n_bytes: usize) -> String {
    let mut buf = vec![0u8; n_bytes];
    getrandom::getrandom(&mut buf).expect("secure RNG unavailable");
    buf.iter().map(|b| format!("{:02x}", b)).collect()
}

/// backend/server.js fatals if JWT_SECRET_KEY is unset. Mirror the launcher:
/// reuse an existing secret from ~/.ai-employee/.env or env, else generate one
/// and persist it (never printed, never committed).
fn ensure_jwt_secret(app_home: &Path) -> String {
    let envf = app_home.join(".env");
    for (k, v) in load_dotenv(&envf) {
        if k == "JWT_SECRET_KEY" && !v.is_empty() {
            return v;
        }
    }
    if let Ok(v) = std::env::var("JWT_SECRET_KEY") {
        if !v.is_empty() {
            return v;
        }
    }
    let secret = rand_hex(32);
    let _ = std::fs::create_dir_all(app_home);
    let prefix = if envf.exists() { "\n" } else { "" };
    if let Ok(mut f) = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&envf)
    {
        let _ = write!(f, "{}JWT_SECRET_KEY={}\n", prefix, secret);
    }
    secret
}

fn push_env(env: &mut Vec<(String, String)>, key: &str, val: String) {
    env.push((key.to_string(), val));
}

fn set_if_absent(env: &mut Vec<(String, String)>, key: &str, val: &str) {
    if !env.iter().any(|(k, _)| k == key) {
        env.push((key.to_string(), val.to_string()));
    }
}

/// Base environment shared by Node + Python children. Starts from the user's
/// ~/.ai-employee/.env (API keys, overrides), then layers the canonical paths.
fn base_env(state: &SharedState) -> Vec<(String, String)> {
    let mut env = load_dotenv(&state.app_home.join(".env"));
    set_if_absent(&mut env, "JWT_SECRET_KEY", &ensure_jwt_secret(&state.app_home));
    push_env(&mut env, "AI_HOME", state.app_home.display().to_string());
    push_env(&mut env, "AI_EMPLOYEE_HOME", state.app_home.display().to_string());
    push_env(&mut env, "STATE_DIR", state.app_home.join("state").display().to_string());
    push_env(&mut env, "LOG_DIR", state.app_home.join("logs").display().to_string());
    push_env(&mut env, "RUN_DIR", state.app_home.join("run").display().to_string());
    push_env(&mut env, "AI_EMPLOYEE_REPO_DIR", state.repo_dir.display().to_string());
    push_env(&mut env, "LISTEN_HOST", "127.0.0.1".to_string());
    set_if_absent(&mut env, "AI_EMPLOYEE_OFFLINE", "1");
    let pw = state.repo_dir.join("runtime/browsers/playwright");
    if pw.exists() {
        push_env(&mut env, "PLAYWRIGHT_BROWSERS_PATH", pw.display().to_string());
    }
    env
}

fn which_runtime(cands: &[&str]) -> Option<String> {
    for c in cands {
        let ok = std::process::Command::new(c)
            .arg("--version")
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .map(|s| s.success())
            .unwrap_or(false);
        if ok {
            return Some(c.to_string());
        }
    }
    None
}

// ── Event helpers (drive the splash) ─────────────────────────────────────────

fn strip_ansi(s: &str) -> String {
    // Minimal CSI escape stripping so the splash log stays readable.
    let mut out = String::with_capacity(s.len());
    let bytes = s.as_bytes();
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == 0x1B && i + 1 < bytes.len() && bytes[i + 1] == b'[' {
            i += 2;
            while i < bytes.len() && !(bytes[i] as char).is_ascii_alphabetic() {
                i += 1;
            }
            if i < bytes.len() {
                i += 1;
            }
        } else {
            out.push(bytes[i] as char);
            i += 1;
        }
    }
    out
}

fn emit_log(app: &AppHandle, state: &SharedState, name: &str, line: &str, level: &str) {
    let entry = format!("[{}] {}", name, line);
    {
        let mut logs = state.logs.lock().unwrap();
        logs.push_back(entry.clone());
        while logs.len() > MAX_LOG_LINES {
            logs.pop_front();
        }
    }
    let _ = app.emit("boot://log", json!({ "line": entry, "level": level }));
}

fn emit_status(app: &AppHandle, message: &str) {
    let _ = app.emit("boot://status", json!({ "message": message }));
}

fn emit_phase(app: &AppHandle, state: &SharedState, phase: &str, label: &str) {
    {
        let mut d = state.phases_done.lock().unwrap();
        if !d.iter().any(|p| p == phase) {
            d.push(phase.to_string());
        }
    }
    let _ = app.emit(
        "boot://phase",
        json!({ "phase": phase, "label": label, "status": "ok" }),
    );
}

fn emit_fail(app: &AppHandle, state: &SharedState, phase: &str, reason: &str) {
    *state.failed.lock().unwrap() = Some(reason.to_string());
    let _ = app.emit("boot://fail", json!({ "phase": phase, "reason": reason }));
}

// ── Process spawning + log streaming ─────────────────────────────────────────

fn spawn_reader<R>(app: AppHandle, state: SharedState, name: String, reader: R, log_path: PathBuf, is_err: bool)
where
    R: AsyncRead + Unpin + Send + 'static,
{
    tauri::async_runtime::spawn(async move {
        let mut file = std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(&log_path)
            .ok();
        let mut lines = BufReader::new(reader).lines();
        while let Ok(Some(line)) = lines.next_line().await {
            if let Some(f) = file.as_mut() {
                let _ = writeln!(f, "{}", line);
            }
            let clean = strip_ansi(&line);
            if clean.trim().is_empty() {
                continue;
            }
            emit_log(&app, &state, &name, &clean, if is_err { "warn" } else { "info" });
        }
    });
}

fn spawn_service(
    app: &AppHandle,
    state: &SharedState,
    name: &str,
    program: &str,
    args: &[String],
    envs: &[(String, String)],
    cwd: &Path,
    log_file: &Path,
) -> std::io::Result<Child> {
    let mut cmd = Command::new(program);
    cmd.args(args)
        .current_dir(cwd)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .kill_on_drop(true);
    for (k, v) in envs {
        cmd.env(k, v);
    }
    let mut child = cmd.spawn()?;
    if let Some(out) = child.stdout.take() {
        spawn_reader(app.clone(), state.clone(), name.to_string(), out, log_file.to_path_buf(), false);
    }
    if let Some(err) = child.stderr.take() {
        spawn_reader(app.clone(), state.clone(), name.to_string(), err, log_file.to_path_buf(), true);
    }
    Ok(child)
}

fn node_crashed(state: &SharedState) -> Option<String> {
    let mut ch = state.children.lock().unwrap();
    for cp in ch.iter_mut() {
        if cp.name == "node" {
            if let Ok(Some(status)) = cp.child.try_wait() {
                let logs = state.logs.lock().unwrap();
                let mut tail: Vec<String> = logs.iter().rev().take(10).cloned().collect();
                tail.reverse();
                return Some(format!("Node gateway exited ({}).\n{}", status, tail.join("\n")));
            }
        }
    }
    None
}

fn kill_children(app: &AppHandle) {
    let state = app.state::<SharedState>();
    let mut ch = state.children.lock().unwrap();
    for cp in ch.iter_mut() {
        let _ = cp.child.start_kill();
    }
    ch.clear();
}

// ── Readiness probes ─────────────────────────────────────────────────────────

async fn tcp_open(host: &str, port: u16) -> bool {
    matches!(
        timeout(Duration::from_millis(800), TcpStream::connect((host, port))).await,
        Ok(Ok(_))
    )
}

async fn http_ok(url: &str) -> bool {
    let client = match reqwest::Client::builder().timeout(Duration::from_secs(3)).build() {
        Ok(c) => c,
        Err(_) => return false,
    };
    matches!(client.get(url).send().await, Ok(r) if r.status().is_success())
}

struct ReadinessInfo {
    python_ready: bool,
    frontend_ready: bool,
}

/// GET /api/readiness (unauthenticated). Returns None if it can't be read.
async fn fetch_readiness(origin: &str) -> Option<ReadinessInfo> {
    let client = reqwest::Client::builder().timeout(Duration::from_secs(3)).build().ok()?;
    let resp = client.get(format!("{}/api/readiness", origin)).send().await.ok()?;
    if !resp.status().is_success() {
        return None;
    }
    let v: serde_json::Value = resp.json().await.ok()?;
    Some(ReadinessInfo {
        python_ready: v.get("pythonReady").and_then(|x| x.as_bool()).unwrap_or(false),
        frontend_ready: v.get("frontendIndex").and_then(|x| x.as_bool()).unwrap_or(true),
    })
}

async fn wait_tcp(state: &SharedState, host: &str, port: u16, cap_s: u64) -> bool {
    let start = Instant::now();
    let mut delay = 150u64;
    while start.elapsed() < Duration::from_secs(cap_s) {
        if node_crashed(state).is_some() {
            return false;
        }
        if tcp_open(host, port).await {
            return true;
        }
        sleep(Duration::from_millis(delay)).await;
        delay = (delay * 2).min(2000);
    }
    false
}

async fn wait_http(state: &SharedState, url: &str, cap_s: u64) -> bool {
    let start = Instant::now();
    let mut delay = 200u64;
    while start.elapsed() < Duration::from_secs(cap_s) {
        if node_crashed(state).is_some() {
            return false;
        }
        if http_ok(url).await {
            return true;
        }
        sleep(Duration::from_millis(delay)).await;
        delay = (delay * 2).min(2500);
    }
    false
}

// ── Dashboard handoff ────────────────────────────────────────────────────────
// Single window: it starts on splash.html and NAVIGATES in place to the dashboard
// once the runtime is ready. No second window is ever created — this is what keeps
// the boot flicker-free (one window, dark background, content swaps splash→dashboard).

fn open_main(app: &AppHandle, origin: &str) {
    let url: tauri::Url = match format!("{}/", origin).parse() {
        Ok(u) => u,
        Err(e) => {
            let state = app.state::<SharedState>().inner().clone();
            emit_fail(app, &state, "dashboard", &format!("Invalid dashboard URL: {}", e));
            return;
        }
    };
    if let Some(w) = app.get_webview_window("main") {
        let _ = w.navigate(url);
        let _ = w.show();
        let _ = w.set_focus();
        let _ = app.emit("boot://ready", ());
    } else {
        let state = app.state::<SharedState>().inner().clone();
        emit_fail(app, &state, "dashboard", "Main window is missing");
    }
}

// ── Boot sequence ────────────────────────────────────────────────────────────

async fn boot(app: AppHandle) {
    let state = app.state::<SharedState>().inner().clone();

    {
        let mut b = state.booting.lock().unwrap();
        if *b {
            return;
        }
        *b = true;
    }
    *state.failed.lock().unwrap() = None;
    state.phases_done.lock().unwrap().clear();

    let host = "127.0.0.1";

    // Pre-flight: runtime files + binaries present.
    emit_status(&app, "Running pre-flight checks");
    if !state.repo_dir.join("backend/server.js").exists()
        || !state.repo_dir.join("frontend/dist/index.html").exists()
    {
        emit_fail(
            &app,
            &state,
            "preflight",
            &format!("Runtime files not found under {}", state.repo_dir.display()),
        );
        *state.booting.lock().unwrap() = false;
        return;
    }
    let node = which_runtime(&["node"]);
    let python = which_runtime(&["python3", "python"]);
    if node.is_none() {
        emit_fail(&app, &state, "preflight", "Node.js not found on PATH");
        *state.booting.lock().unwrap() = false;
        return;
    }
    emit_phase(&app, &state, "preflight", "Pre-flight OK");

    // Optional debug hold so the boot splash can be observed (default off, env-gated).
    if let Ok(ms) = std::env::var("NEXUS_BOOT_DELAY_MS") {
        if let Ok(n) = ms.parse::<u64>() {
            if n > 0 {
                emit_status(&app, "Boot delay (debug hold)");
                sleep(Duration::from_millis(n)).await;
            }
        }
    }

    let base = base_env(&state);

    // Spawn services.
    emit_status(&app, "Spawning backend services");

    if let Some(py) = python {
        let mut envs = base.clone();
        push_env(&mut envs, "PROBLEM_SOLVER_UI_PORT", state.python_port.to_string());
        push_env(&mut envs, "PYTHON_BACKEND_PORT", state.python_port.to_string());
        push_env(&mut envs, "PROBLEM_SOLVER_UI_HOST", "127.0.0.1".to_string());
        let server_py = state.repo_dir.join("runtime/agents/problem-solver-ui/server.py");
        let logf = state.app_home.join("logs/python-backend.log");
        match spawn_service(
            &app,
            &state,
            "python",
            &py,
            &[server_py.to_string_lossy().to_string()],
            &envs,
            &state.repo_dir,
            &logf,
        ) {
            Ok(c) => state.children.lock().unwrap().push(ChildProc { name: "python".into(), child: c }),
            Err(e) => emit_log(&app, &state, "python", &format!("spawn failed: {}", e), "warn"),
        }
    } else {
        emit_log(&app, &state, "launcher", "Python 3 not found — AI backend will be unavailable", "warn");
    }

    let mut nenvs = base.clone();
    push_env(&mut nenvs, "PORT", state.node_port.to_string());
    push_env(&mut nenvs, "PROBLEM_SOLVER_UI_PORT", state.node_port.to_string());
    push_env(&mut nenvs, "PYTHON_BACKEND_PORT", state.python_port.to_string());
    // NOTE: deliberately NOT setting NODE_ENV=production. The canonical start.sh
    // runtime runs without it; production mode additionally requires
    // SETTINGS_ENCRYPTION_KEY (backend/routes/settings.js). Enabling production +
    // a managed encryption key is a separate security-hardening milestone applied
    // uniformly to start.sh and this shell — not a silent M1 change.
    let server_js = state.repo_dir.join("backend/server.js");
    let nlog = state.app_home.join("logs/server.log");
    match spawn_service(
        &app,
        &state,
        "node",
        &node.unwrap(),
        &[server_js.to_string_lossy().to_string()],
        &nenvs,
        &state.repo_dir,
        &nlog,
    ) {
        Ok(c) => {
            state.children.lock().unwrap().push(ChildProc { name: "node".into(), child: c });
            emit_phase(&app, &state, "backend-spawn", "Services spawned");
        }
        Err(e) => {
            emit_fail(&app, &state, "backend-spawn", &format!("Failed to spawn Node gateway: {}", e));
            *state.booting.lock().unwrap() = false;
            return;
        }
    }

    // Gate: wait for the Node gateway to bind, then pass health.
    emit_status(&app, &format!("Waiting for gateway on :{}", state.node_port));
    if !wait_tcp(&state, host, state.node_port, 60).await {
        let reason = node_crashed(&state)
            .unwrap_or_else(|| format!("Gateway did not bind :{} within 60s", state.node_port));
        emit_fail(&app, &state, "node-port-bound", &reason);
        *state.booting.lock().unwrap() = false;
        return;
    }
    emit_phase(&app, &state, "node-port-bound", "Gateway listening");

    let origin = format!("http://{}:{}", host, state.node_port);
    emit_status(&app, "Verifying health");
    // /health is the unauthenticated liveness endpoint (/api/health requires auth).
    if !wait_http(&state, &format!("{}/health", origin), 45).await {
        let reason = node_crashed(&state)
            .unwrap_or_else(|| "/health did not pass within 45s".to_string());
        emit_fail(&app, &state, "health-ok", &reason);
        *state.booting.lock().unwrap() = false;
        return;
    }
    emit_phase(&app, &state, "health-ok", "Health passing");

    // /api/readiness (unauthenticated) confirms the frontend is served + reports
    // whether the Python AI backend is up. Python is optional → degraded mode.
    if let Some(rd) = fetch_readiness(&origin).await {
        if !rd.frontend_ready {
            emit_log(&app, &state, "launcher", "Frontend bundle not reported ready — opening anyway", "warn");
        }
        if !rd.python_ready {
            emit_log(&app, &state, "launcher", "Python AI backend not ready — opening in degraded mode", "warn");
        }
    }

    emit_status(&app, "Opening dashboard");
    open_main(&app, &origin);
    emit_phase(&app, &state, "dashboard", "Dashboard");

    *state.booting.lock().unwrap() = false;
}

// ── Commands (called from the splash) ────────────────────────────────────────

#[tauri::command]
async fn retry_boot(app: AppHandle) {
    kill_children(&app);
    {
        let st = app.state::<SharedState>();
        *st.booting.lock().unwrap() = false;
    }
    boot(app).await;
}

#[tauri::command]
fn open_logs_folder(app: AppHandle) -> Result<(), String> {
    let st = app.state::<SharedState>();
    let dir = st.app_home.join("logs");
    let _ = std::fs::create_dir_all(&dir);
    let opener = if cfg!(target_os = "windows") {
        "explorer"
    } else if cfg!(target_os = "macos") {
        "open"
    } else {
        "xdg-open"
    };
    std::process::Command::new(opener)
        .arg(&dir)
        .spawn()
        .map(|_| ())
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn get_boot_state(app: AppHandle) -> serde_json::Value {
    let st = app.state::<SharedState>();
    let logs: Vec<String> = st.logs.lock().unwrap().iter().cloned().collect();
    let phases: Vec<String> = st.phases_done.lock().unwrap().clone();
    let failed = st.failed.lock().unwrap().clone();
    json!({
        "version": env!("CARGO_PKG_VERSION"),
        "recent_logs": logs,
        "phases_done": phases,
        "failed": failed.is_some(),
        "fail_reason": failed,
        "node_port": st.node_port,
        "python_port": st.python_port,
    })
}

#[tauri::command]
fn quit_app(app: AppHandle) {
    kill_children(&app);
    app.exit(0);
}

// ── Tray ─────────────────────────────────────────────────────────────────────

fn focus_any(app: &AppHandle) {
    if let Some(w) = app.get_webview_window("main") {
        let _ = w.show();
        let _ = w.set_focus();
    }
}

fn build_tray(app: &tauri::App) -> tauri::Result<()> {
    let quit = MenuItem::with_id(app, "quit", "Quit Nexus OS", true, None::<&str>)?;
    let show = MenuItem::with_id(app, "show", "Show Dashboard", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&show, &quit])?;
    TrayIconBuilder::new()
        .menu(&menu)
        .on_menu_event(|app, event| match event.id.as_ref() {
            "quit" => {
                kill_children(app);
                app.exit(0);
            }
            "show" => focus_any(app),
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                focus_any(tray.app_handle());
            }
        })
        .build(app)?;
    Ok(())
}

// ── Entrypoint ───────────────────────────────────────────────────────────────

pub fn run() {
    let repo_dir = resolve_repo_dir();
    let app_home = resolve_app_home();
    ensure_dirs(&app_home);
    let node_port = env_port(&["PROBLEM_SOLVER_UI_PORT", "PORT"], 8787);
    let python_port = env_port(&["PYTHON_BACKEND_PORT", "AI_BACKEND_PORT"], 18790);

    let state: SharedState = Arc::new(AppState {
        repo_dir,
        app_home,
        node_port,
        python_port,
        children: Mutex::new(Vec::new()),
        logs: Mutex::new(VecDeque::new()),
        phases_done: Mutex::new(Vec::new()),
        failed: Mutex::new(None),
        booting: Mutex::new(false),
    });

    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            focus_any(app);
        }))
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_http::init())
        .plugin(tauri_plugin_notification::init())
        .manage(state)
        .setup(|app| {
            build_tray(app)?;
            let handle = app.handle().clone();
            tauri::async_runtime::spawn(boot(handle));
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            retry_boot,
            open_logs_folder,
            get_boot_state,
            quit_app
        ])
        .build(tauri::generate_context!())
        .expect("error while building Nexus OS")
        .run(|app, event| {
            if matches!(event, RunEvent::ExitRequested { .. } | RunEvent::Exit) {
                kill_children(app);
            }
        });
}
