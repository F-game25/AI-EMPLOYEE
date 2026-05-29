use serde::{Deserialize, Serialize};
use std::fs;
use std::net::TcpStream;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};
use tauri::{AppHandle, Emitter, Manager, State};

// ── Runtime route ─────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RuntimeRoute {
    pub node_port: u16,
    pub python_port: u16,
    pub host: String,
    pub ui_origin: String,
    pub dashboard_url: String,
}

impl Default for RuntimeRoute {
    fn default() -> Self {
        let node_port = env_port("PROBLEM_SOLVER_UI_PORT")
            .or_else(|| env_port("PORT"))
            .unwrap_or(8787);
        let python_port = env_port("PYTHON_BACKEND_PORT")
            .or_else(|| env_port("AI_BACKEND_PORT"))
            .unwrap_or(18790);
        let host = std::env::var("UI_HOST").unwrap_or_else(|_| "127.0.0.1".into());
        let ui_origin = format!("http://{}:{}", host, node_port);
        let dashboard_url = format!("{}/?tauri=1", ui_origin);
        Self { node_port, python_port, host, ui_origin, dashboard_url }
    }
}

fn env_port(name: &str) -> Option<u16> {
    std::env::var(name).ok()?.parse().ok()
}

// ── Shared launcher state ─────────────────────────────────────────────────────

#[derive(Debug, Default)]
pub struct LauncherState {
    pub route: RuntimeRoute,
    pub launch_status: LaunchStatus,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct LaunchStatus {
    pub state: String,
    pub phase: String,
    pub message: String,
    pub last_error: Option<String>,
}

pub struct AppState(pub Arc<Mutex<LauncherState>>);

// ── Watchdog state (shared across health-poll loop + commands) ────────────────

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct WatchdogStatus {
    pub node_ok: bool,
    pub python_ok: bool,
    pub consecutive_node_failures: u32,
    pub consecutive_python_failures: u32,
    pub restarts_attempted: u32,
    pub last_restart: Option<String>,
    pub status: String,  // healthy | degraded | restarting
}

pub struct WatchdogState(pub Arc<Mutex<WatchdogStatus>>);

// ── Path resolution ───────────────────────────────────────────────────────────

fn resolve_repo_dir() -> PathBuf {
    if let Ok(v) = std::env::var("AI_EMPLOYEE_REPO_DIR") {
        let p = PathBuf::from(v);
        if p.join("backend").join("server.js").exists() { return p; }
    }
    let exe = std::env::current_exe().unwrap_or_default();
    let mut dir = exe.parent().map(|p| p.to_path_buf()).unwrap_or_default();
    for _ in 0..10 {
        if dir.join("backend").join("server.js").exists() { return dir; }
        match dir.parent() {
            Some(p) => dir = p.to_path_buf(),
            None => break,
        }
    }
    std::env::current_dir().unwrap_or_default()
}

fn resolve_app_home() -> PathBuf {
    if let Ok(v) = std::env::var("AI_EMPLOYEE_HOME") { return PathBuf::from(v); }
    if let Ok(v) = std::env::var("AI_HOME") { return PathBuf::from(v); }
    let home = std::env::var("HOME").unwrap_or_else(|_| "/tmp".into());
    PathBuf::from(home).join(".ai-employee")
}

fn ensure_dirs(app_home: &Path) {
    for sub in &["state", "logs", "run", "config", "cache"] {
        let _ = fs::create_dir_all(app_home.join(sub));
    }
}

// ── .env loader ───────────────────────────────────────────────────────────────

fn load_dot_env(path: &Path) {
    let Ok(contents) = fs::read_to_string(path) else { return };
    for line in contents.lines() {
        let t = line.trim();
        if t.is_empty() || t.starts_with('#') { continue; }
        if let Some(idx) = t.find('=') {
            let key = t[..idx].trim();
            let raw = t[idx + 1..].trim();
            let val = raw.trim_matches('"').trim_matches('\'');
            if std::env::var(key).is_err() {
                std::env::set_var(key, val);
            }
        }
    }
}

// ── Update settings reader (for watchdog config) ──────────────────────────────

#[derive(Debug, Clone, Deserialize)]
struct UpdateSettings {
    watchdog_enabled: Option<bool>,
    watchdog_interval_seconds: Option<u64>,
    watchdog_max_failures: Option<u32>,
}

fn load_update_settings(app_home: &Path) -> UpdateSettings {
    let path = app_home.join("state").join("update-settings.json");
    if let Ok(raw) = fs::read_to_string(&path) {
        if let Ok(s) = serde_json::from_str::<UpdateSettings>(&raw) {
            return s;
        }
    }
    UpdateSettings { watchdog_enabled: None, watchdog_interval_seconds: None, watchdog_max_failures: None }
}

// ── TCP / HTTP probes ─────────────────────────────────────────────────────────

fn tcp_probe(host: &str, port: u16, timeout_ms: u64) -> bool {
    let addr = format!("{}:{}", host, port);
    TcpStream::connect_timeout(
        &addr.parse().unwrap_or_else(|_| "127.0.0.1:80".parse().unwrap()),
        Duration::from_millis(timeout_ms),
    ).is_ok()
}

async fn http_probe(url: &str, timeout_ms: u64) -> bool {
    let client = reqwest::Client::builder()
        .timeout(Duration::from_millis(timeout_ms))
        .build()
        .unwrap_or_default();
    matches!(client.get(url).send().await, Ok(r) if r.status().is_success())
}

fn backend_running(port: u16) -> bool {
    tcp_probe("127.0.0.1", port, 300)
}

fn spawn_backends(repo_dir: &Path) {
    let _ = std::process::Command::new("bash")
        .arg(repo_dir.join("start.sh"))
        .current_dir(repo_dir)
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .spawn();
}

async fn wait_until_healthy(url: &str, cap_ms: u64) -> bool {
    let started = Instant::now();
    let delays = [500u64, 500, 1000, 1000, 2000, 2000, 4000, 4000];
    let mut attempt = 0usize;
    while started.elapsed().as_millis() < cap_ms as u128 {
        if http_probe(url, 2500).await { return true; }
        let delay = delays[attempt.min(delays.len() - 1)];
        tokio::time::sleep(Duration::from_millis(delay)).await;
        attempt += 1;
    }
    false
}

// ── Backend restart (called by watchdog when health fails repeatedly) ─────────

async fn restart_backends(repo_dir: &PathBuf) {
    let start_sh = repo_dir.join("start.sh");
    if !start_sh.exists() { return; }
    let _ = std::process::Command::new("bash")
        .arg(&start_sh)
        .arg("--restart-only")
        .current_dir(repo_dir)
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .spawn();
    // Give backends time to come up before next health check
    tokio::time::sleep(Duration::from_secs(8)).await;
}

// ── Tauri commands ────────────────────────────────────────────────────────────

#[tauri::command]
async fn check_health(state: State<'_, AppState>) -> Result<bool, String> {
    let url = {
        let s = state.0.lock().map_err(|e| e.to_string())?;
        s.route.ui_origin.clone()
    };
    Ok(http_probe(&format!("{}/health", url), 2500).await)
}

#[tauri::command]
async fn check_port(state: State<'_, AppState>) -> Result<bool, String> {
    let (host, port) = {
        let s = state.0.lock().map_err(|e| e.to_string())?;
        (s.route.host.clone(), s.route.node_port)
    };
    Ok(tcp_probe(&host, port, 1000))
}

#[tauri::command]
fn get_runtime_route(state: State<'_, AppState>) -> Result<RuntimeRoute, String> {
    let s = state.0.lock().map_err(|e| e.to_string())?;
    Ok(s.route.clone())
}

#[tauri::command]
fn get_backend_port(state: State<'_, AppState>) -> Result<u16, String> {
    let s = state.0.lock().map_err(|e| e.to_string())?;
    Ok(s.route.node_port)
}

#[tauri::command]
fn load_runtime_lock(state: State<'_, AppState>) -> Result<serde_json::Value, String> {
    let app_home = resolve_app_home();
    let lock_path = app_home.join("run").join("runtime-lock.json");
    let raw = fs::read_to_string(&lock_path).map_err(|e| format!("lock read error: {}", e))?;
    let lock: serde_json::Value = serde_json::from_str(&raw).map_err(|e| format!("lock parse error: {}", e))?;
    if let (Some(node_port), Some(ui_origin)) = (
        lock.get("ports").and_then(|p| p.get("node")).and_then(|v| v.as_u64()),
        lock.get("uiOrigin").and_then(|v| v.as_str()),
    ) {
        let python_port = lock.get("ports").and_then(|p| p.get("python"))
            .and_then(|v| v.as_u64()).unwrap_or(18790) as u16;
        let dashboard_url = lock.get("dashboardUrl").and_then(|v| v.as_str())
            .map(|s| s.replace("?electron=1", "?tauri=1"))
            .unwrap_or_else(|| format!("{}/?tauri=1", ui_origin));
        let mut s = state.0.lock().map_err(|e| e.to_string())?;
        s.route.node_port = node_port as u16;
        s.route.python_port = python_port;
        s.route.ui_origin = ui_origin.to_string();
        s.route.dashboard_url = dashboard_url;
    }
    Ok(lock)
}

#[tauri::command]
fn get_launch_status(state: State<'_, AppState>) -> Result<LaunchStatus, String> {
    let s = state.0.lock().map_err(|e| e.to_string())?;
    Ok(s.launch_status.clone())
}

#[tauri::command]
fn get_paths() -> Result<serde_json::Value, String> {
    let repo = resolve_repo_dir();
    let home = resolve_app_home();
    Ok(serde_json::json!({
        "repoDir":  repo,
        "appHome":  home,
        "stateDir": home.join("state"),
        "logDir":   home.join("logs"),
        "runDir":   home.join("run"),
    }))
}

#[tauri::command]
fn get_watchdog_status(wd: State<'_, WatchdogState>) -> Result<WatchdogStatus, String> {
    let s = wd.0.lock().map_err(|e| e.to_string())?;
    Ok(s.clone())
}

#[tauri::command]
async fn restart_backends_cmd(state: State<'_, AppState>) -> Result<bool, String> {
    let _ = state; // ensures we hold the state type reference
    let repo = resolve_repo_dir();
    restart_backends(&repo).await;
    Ok(true)
}

// ── Background health-poll + watchdog loop ────────────────────────────────────

async fn health_poll_loop(
    app: AppHandle,
    state: Arc<Mutex<LauncherState>>,
    wd: Arc<Mutex<WatchdogStatus>>,
    app_home: PathBuf,
) {
    let max_failures_default = 3u32;
    let poll_interval_default = 5u64; // seconds (fast poll — catchup to Node watchdog)

    loop {
        // Re-read watchdog config on every tick so UI changes apply immediately
        let us = load_update_settings(&app_home);
        let watchdog_enabled    = us.watchdog_enabled.unwrap_or(true);
        let poll_secs           = us.watchdog_interval_seconds.unwrap_or(30).min(300).max(5);
        let max_node_failures   = us.watchdog_max_failures.unwrap_or(max_failures_default);

        let (url, node_port, python_port, host) = {
            let s = state.lock().unwrap();
            (
                s.route.ui_origin.clone(),
                s.route.node_port,
                s.route.python_port,
                s.route.host.clone(),
            )
        };

        let node_ok   = http_probe(&format!("{}/health", url), 2500).await;
        let python_ok = tcp_probe(&host, python_port, 1000);

        // Emit to webview
        let _ = app.emit("backend-health", serde_json::json!({
            "node_ok":    node_ok,
            "python_ok":  python_ok,
            "node_port":  node_port,
            "python_port": python_port,
            "ts": std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap_or_default()
                .as_millis() as u64,
        }));

        // Watchdog restart logic
        if watchdog_enabled {
            let should_restart = {
                let mut w = wd.lock().unwrap();
                w.node_ok   = node_ok;
                w.python_ok = python_ok;

                if node_ok {
                    w.consecutive_node_failures = 0;
                    w.status = if python_ok { "healthy".into() } else { "degraded".into() };
                } else {
                    w.consecutive_node_failures += 1;
                    w.status = if w.consecutive_node_failures >= max_node_failures {
                        "restarting".into()
                    } else {
                        "degraded".into()
                    };
                }
                w.consecutive_node_failures >= max_node_failures
            };

            if should_restart {
                let _ = app.emit("watchdog:restarting", serde_json::json!({ "reason": "node_health_failed" }));
                let repo = resolve_repo_dir();
                restart_backends(&repo).await;
                {
                    let mut w = wd.lock().unwrap();
                    w.consecutive_node_failures = 0;
                    w.restarts_attempted += 1;
                    w.last_restart = Some(chrono_now());
                    w.status = "healthy".into();
                }
                let _ = app.emit("watchdog:restarted", serde_json::json!({}));
                // After restart, wait for healthy before continuing normal polling
                let health_url = format!("{}/health", url);
                wait_until_healthy(&health_url, 30_000).await;
            }
        }

        tokio::time::sleep(Duration::from_secs(poll_secs.min(poll_interval_default))).await;
    }
}

fn chrono_now() -> String {
    use std::time::{SystemTime, UNIX_EPOCH};
    let secs = SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs();
    // Simple ISO-8601 UTC approximation without chrono dependency
    let s = secs % 60;
    let m = (secs / 60) % 60;
    let h = (secs / 3600) % 24;
    let days = secs / 86400;
    // Days since 1970-01-01 to YYYY-MM-DD (approximate — good enough for log display)
    let y400 = days / 146097;
    let r = days % 146097;
    let y = 1970 + y400 * 400 + r / 365;
    format!("{:04}-??-?? {:02}:{:02}:{:02}Z", y, h, m, s)
}

// ── App entry point ───────────────────────────────────────────────────────────

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app_home = resolve_app_home();
    ensure_dirs(&app_home);
    load_dot_env(&app_home.join(".env"));

    let initial_state = {
        let mut route = RuntimeRoute::default();
        let lock_path = app_home.join("run").join("runtime-lock.json");
        if let Ok(raw) = fs::read_to_string(&lock_path) {
            if let Ok(lock) = serde_json::from_str::<serde_json::Value>(&raw) {
                if let (Some(np), Some(origin)) = (
                    lock.get("ports").and_then(|p| p.get("node")).and_then(|v| v.as_u64()),
                    lock.get("uiOrigin").and_then(|v| v.as_str()),
                ) {
                    let pp = lock.get("ports").and_then(|p| p.get("python"))
                        .and_then(|v| v.as_u64()).unwrap_or(18790) as u16;
                    let du = lock.get("dashboardUrl").and_then(|v| v.as_str())
                        .map(|s| s.replace("?electron=1", "?tauri=1"))
                        .unwrap_or_else(|| format!("{}/?tauri=1", origin));
                    route.node_port = np as u16;
                    route.python_port = pp;
                    route.ui_origin = origin.to_string();
                    route.dashboard_url = du;
                }
            }
        }
        Arc::new(Mutex::new(LauncherState {
            route,
            launch_status: LaunchStatus {
                state: "starting".into(),
                phase: "boot".into(),
                message: "Starting backends…".into(),
                last_error: None,
            },
        }))
    };

    let watchdog_state = Arc::new(Mutex::new(WatchdogStatus {
        status: "idle".into(),
        ..Default::default()
    }));

    let state_for_boot = Arc::clone(&initial_state);
    let wd_for_loop    = Arc::clone(&watchdog_state);
    let app_home_clone = app_home.clone();

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_http::init())
        .manage(AppState(initial_state))
        .manage(WatchdogState(watchdog_state))
        .invoke_handler(tauri::generate_handler![
            check_health,
            check_port,
            get_runtime_route,
            get_backend_port,
            load_runtime_lock,
            get_launch_status,
            get_paths,
            get_watchdog_status,
            restart_backends_cmd,
        ])
        .setup(move |app| {
            let app_handle = app.handle().clone();

            tauri::async_runtime::spawn(async move {
                let (health_url, node_port) = {
                    let s = state_for_boot.lock().unwrap();
                    (format!("{}/health", s.route.ui_origin), s.route.node_port)
                };

                if !backend_running(node_port) {
                    let repo = resolve_repo_dir();
                    spawn_backends(&repo);
                }

                // Wait up to 45s for Node health endpoint
                wait_until_healthy(&health_url, 45_000).await;

                // Show window (created hidden via tauri.conf.json)
                if let Some(win) = app_handle.get_webview_window("main") {
                    let _ = win.show();
                    let _ = win.set_focus();
                }

                {
                    let mut s = state_for_boot.lock().unwrap();
                    s.launch_status.state = "running".into();
                    s.launch_status.phase = "ready".into();
                    s.launch_status.message = "Nexus OS ready".into();
                }

                health_poll_loop(app_handle, state_for_boot, wd_for_loop, app_home_clone).await;
            });

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application")
}
