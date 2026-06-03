use tauri::{
    AppHandle, Manager, RunEvent,
    tray::{TrayIconBuilder, TrayIconEvent, MouseButton, MouseButtonState},
    menu::{Menu, MenuItem},
};
use tauri_plugin_shell::ShellExt;
use std::sync::{Arc, Mutex};

#[derive(Default)]
struct AppState {
    backends_started: bool,
}

#[tauri::command]
async fn get_backend_status(app: AppHandle) -> serde_json::Value {
    let client = reqwest::Client::new();
    let node_ok = client.get("http://localhost:8787/health").timeout(std::time::Duration::from_secs(2)).send().await.is_ok();
    let py_ok = client.get("http://127.0.0.1:18790/health").timeout(std::time::Duration::from_secs(2)).send().await.is_ok();
    serde_json::json!({ "node": node_ok, "python": py_ok, "ready": node_ok })
}

#[tauri::command]
async fn check_first_run(app: AppHandle) -> bool {
    let state_dir = app.path().app_data_dir().unwrap_or_default();
    !state_dir.join("onboarding_complete").exists()
}

#[tauri::command]
async fn complete_onboarding(app: AppHandle) -> Result<(), String> {
    let state_dir = app.path().app_data_dir().map_err(|e| e.to_string())?;
    std::fs::create_dir_all(&state_dir).map_err(|e| e.to_string())?;
    std::fs::write(state_dir.join("onboarding_complete"), b"1").map_err(|e| e.to_string())?;
    Ok(())
}

fn start_backends(app: &AppHandle) {
    let shell = app.shell();
    // Start Node.js backend
    let _ = shell
        .command("node")
        .args(["backend/server.js"])
        .env("PORT", "8787")
        .env("NODE_ENV", "production")
        .spawn();
    // Start Python backend
    let _ = shell
        .command("python3")
        .args(["-m", "uvicorn", "runtime.agents.problem-solver-ui.server:app",
               "--host", "127.0.0.1", "--port", "18790", "--log-level", "warning"])
        .spawn();
}

pub fn run() {
    let state = Arc::new(Mutex::new(AppState::default()));

    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            // Focus existing window if app is already running
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.show();
                let _ = window.set_focus();
            }
        }))
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_http::init())
        .plugin(tauri_plugin_notification::init())
        .setup(|app| {
            let app_handle = app.handle().clone();

            // Start backends on launch
            start_backends(&app_handle);

            // System tray
            let quit = MenuItem::with_id(app, "quit", "Quit AI Employee", true, None::<&str>)?;
            let show = MenuItem::with_id(app, "show", "Show Dashboard", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&show, &quit])?;

            TrayIconBuilder::new()
                .menu(&menu)
                .on_menu_event(move |app, event| {
                    match event.id.as_ref() {
                        "quit" => app.exit(0),
                        "show" => {
                            if let Some(w) = app.get_webview_window("main") {
                                let _ = w.show();
                                let _ = w.set_focus();
                            }
                        }
                        _ => {}
                    }
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click { button: MouseButton::Left, button_state: MouseButtonState::Up, .. } = event {
                        let app = tray.app_handle();
                        if let Some(window) = app.get_webview_window("main") {
                            let _ = window.show();
                            let _ = window.set_focus();
                        }
                    }
                })
                .build(app)?;

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            get_backend_status,
            check_first_run,
            complete_onboarding,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
