// Little Prince Launcher - the window.
//
// Everything the launcher does (the game servers, the hosts redirect, downloads,
// the publisher's browser) is the Python package beside this exe; this program
// only:
//   1. asks Windows for administrator rights (the hosts redirect and port 80
//      need them) - declining is allowed, the launcher then runs without them;
//   2. starts the bundled Python (runtime\python\pythonw.exe, or one on PATH)
//      running launcher_web.py on a free local port;
//   3. shows that page in a window (WebView2), and
//   4. on close asks the Python side to stop cleanly (hosts reverted, relay
//      stopped) before it goes - a Windows job object makes sure it can never
//      outlive the window even if this process is killed.
//
// The screens themselves are launcher\ui\*.html, served by Python, so they can be
// edited without rebuilding this exe.
#![windows_subsystem = "windows"]

use std::ffi::OsStr;
use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::os::windows::ffi::OsStrExt;
use std::os::windows::io::AsRawHandle;
use std::os::windows::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::{Child, Command};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use tauri::{RunEvent, WebviewUrl, WebviewWindowBuilder};
use windows_sys::Win32::Graphics::Dwm::DwmSetWindowAttribute;
use windows_sys::Win32::Storage::FileSystem::QueryDosDeviceW;
use windows_sys::Win32::System::JobObjects::{
    AssignProcessToJobObject, CreateJobObjectW, JobObjectExtendedLimitInformation,
    SetInformationJobObject, JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
};
use windows_sys::Win32::UI::Shell::{IsUserAnAdmin, ShellExecuteW};
use windows_sys::Win32::UI::WindowsAndMessaging::{MessageBoxW, MB_ICONERROR, SW_SHOWNORMAL};

const CREATE_NO_WINDOW: u32 = 0x0800_0000;
const TITLE: &str = "Little Prince Launcher";

fn wide(s: &OsStr) -> Vec<u16> {
    s.encode_wide().chain(std::iter::once(0)).collect()
}

/// One line in %TEMP%\littleprince-launcher.log - the only trace a windowless
/// program leaves when it cannot start.
fn trace(msg: &str) {
    let path = std::env::temp_dir().join("littleprince-launcher.log");
    if let Ok(mut f) = std::fs::OpenOptions::new().create(true).append(true).open(path) {
        let _ = writeln!(f, "{}", msg);
    }
}

fn error_box(text: &str) {
    trace(text);
    let t = wide(OsStr::new(text));
    let c = wide(OsStr::new(TITLE));
    unsafe { MessageBoxW(std::ptr::null_mut(), t.as_ptr(), c.as_ptr(), MB_ICONERROR) };
}

/// `path` with a subst drive letter swapped for the folder it stands for.
/// The elevated copy runs in the administrator's logon session, which does not
/// have subst drives - relaunching from one opened nothing at all.
fn real_path(path: &Path) -> PathBuf {
    let s = path.to_string_lossy().to_string();
    let b = s.as_bytes();
    if b.len() < 3 || b[1] != b':' {
        return path.to_path_buf();
    }
    let drive = wide(OsStr::new(&s[..2]));
    let mut buf = vec![0u16; 1024];
    let n = unsafe { QueryDosDeviceW(drive.as_ptr(), buf.as_mut_ptr(), buf.len() as u32) };
    if n > 0 {
        let end = buf.iter().position(|&c| c == 0).unwrap_or(0);
        let target = String::from_utf16_lossy(&buf[..end]);
        if let Some(rest) = target.strip_prefix("\\??\\") {
            return PathBuf::from(format!("{}\\{}", rest.trim_end_matches('\\'), &s[3..]));
        }
    }
    path.to_path_buf()
}

/// Ask for administrator rights by starting an elevated copy; true when it started.
fn relaunch_elevated(args: &[String]) -> bool {
    let exe = match std::env::current_exe() {
        Ok(p) => real_path(&p),
        Err(_) => return false,
    };
    let dir = exe.parent().map(Path::to_path_buf).unwrap_or_default();
    let mut params: Vec<String> = args.iter().map(|a| format!("\"{}\"", a)).collect();
    params.push("--elevated".into());
    let verb = wide(OsStr::new("runas"));
    let file = wide(exe.as_os_str());
    let par = wide(OsStr::new(&params.join(" ")));
    let cwd = wide(dir.as_os_str());
    let rc = unsafe {
        ShellExecuteW(std::ptr::null_mut(), verb.as_ptr(), file.as_ptr(), par.as_ptr(),
                      cwd.as_ptr(), SW_SHOWNORMAL)
    };
    rc as isize > 32
}

/// Windows 11 paints the title bar in the launcher's sky blue with white text,
/// so the frame matches the window (older Windows keeps its own colours).
fn color_title_bar(hwnd: *mut std::ffi::c_void) {
    const BORDER: u32 = 34;
    const CAPTION: u32 = 35;
    const TEXT: u32 = 36;
    let sky: u32 = 0x00F0_B04F;   // #4fb0f0 as 0x00BBGGRR
    let white: u32 = 0x00FF_FFFF;
    for (attr, value) in [(CAPTION, sky), (BORDER, sky), (TEXT, white)] {
        unsafe {
            DwmSetWindowAttribute(hwnd, attr, &value as *const u32 as *const _, 4);
        }
    }
}

fn free_port() -> u16 {
    TcpListener::bind("127.0.0.1:0")
        .and_then(|l| l.local_addr())
        .map(|a| a.port())
        .unwrap_or(48765)
}

/// The launcher folder: where the exe is, as it was started.  Only the elevated
/// relaunch swaps a subst drive for its real path - this process can still see
/// the drive, and the real path may be one only it can reach.
fn home() -> PathBuf {
    std::env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(Path::to_path_buf))
        .unwrap_or_else(|| PathBuf::from("."))
}

fn python(home: &Path) -> PathBuf {
    let bundled = home.join("runtime").join("python").join("pythonw.exe");
    if bundled.is_file() {
        bundled
    } else {
        PathBuf::from("pythonw.exe") // one on PATH, for a source checkout
    }
}

/// A job that kills its processes when its last handle closes - this process.
fn kill_with_us(child: &Child) {
    unsafe {
        let job = CreateJobObjectW(std::ptr::null(), std::ptr::null());
        if job.is_null() {
            return;
        }
        let mut info: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = std::mem::zeroed();
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        SetInformationJobObject(job, JobObjectExtendedLimitInformation,
                                &info as *const _ as *const _,
                                std::mem::size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32);
        AssignProcessToJobObject(job, child.as_raw_handle() as _);
        // the handle is kept open on purpose: it closes when this process ends
    }
}

/// Ask the Python side to stop cleanly, then make sure it is gone.
fn shutdown(port: u16, child: &Arc<Mutex<Option<Child>>>) {
    if let Ok(mut s) = TcpStream::connect_timeout(&([127, 0, 0, 1], port).into(),
                                                  Duration::from_millis(800)) {
        let _ = s.set_read_timeout(Some(Duration::from_secs(5)));
        let _ = s.write_all(b"POST /api/quit HTTP/1.0\r\nHost: 127.0.0.1\r\nContent-Length: 0\r\n\r\n");
        let mut sink = Vec::new();
        let _ = s.read_to_end(&mut sink);
    }
    if let Some(mut c) = child.lock().unwrap().take() {
        let deadline = Instant::now() + Duration::from_secs(6);
        while Instant::now() < deadline {
            if let Ok(Some(_)) = c.try_wait() {
                return;
            }
            std::thread::sleep(Duration::from_millis(100));
        }
        let _ = c.kill();
    }
}

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    trace(&format!("--- start {:?} args {:?}", std::env::current_exe().ok(), args));
    let elevated = unsafe { IsUserAnAdmin() } != 0;
    if !elevated
        && !args.iter().any(|a| a == "--elevated" || a == "--no-elevate")
        && relaunch_elevated(&args)
    {
        return; // the elevated copy takes over
    }

    let home = home();
    let script = home.join("launcher_web.py");
    trace(&format!("home {} script exists {}", home.display(), script.is_file()));
    if !script.is_file() {
        error_box(&format!("launcher_web.py is missing from\n{}\n\nUnzip the whole \
                            launcher folder, not just this exe.", home.display()));
        return;
    }
    let port = free_port();
    let mut cmd = Command::new(python(&home));
    cmd.arg(&script).arg("--ui-port").arg(port.to_string())
        .args(args.iter().filter(|a| a.as_str() != "--elevated"))
        .current_dir(&home)
        .creation_flags(CREATE_NO_WINDOW);
    let child = match cmd.spawn() {
        Ok(c) => c,
        Err(e) => {
            error_box(&format!("Could not start the launcher's Python ({}).\n\n\
                                Expected runtime\\python\\pythonw.exe in\n{}", e, home.display()));
            return;
        }
    };
    trace(&format!("python started, pid {} port {}", child.id(), port));
    kill_with_us(&child);
    let child = Arc::new(Mutex::new(Some(child)));

    let app = tauri::Builder::default()
        .setup(move |app| {
            let window = WebviewWindowBuilder::new(app, "main", WebviewUrl::App("index.html".into()))
                .title(TITLE)
                // a fixed size: the banner box is laid out for exactly this
                .inner_size(1200.0, 700.0)
                .resizable(false)
                .maximizable(false)
                .center()
                .initialization_script(&format!("window.__LP_PORT = {};", port))
                .build()?;
            if let Ok(hwnd) = window.hwnd() {
                color_title_bar(hwnd.0 as _);
            }
            Ok(())
        })
        .build(tauri::generate_context!());
    let app = match app {
        Ok(a) => a,
        Err(e) => {
            error_box(&format!("Could not open the launcher window: {}", e));
            shutdown(port, &child);
            return;
        }
    };
    trace("window built");

    let for_exit = child.clone();
    app.run(move |_handle, event| {
        if let RunEvent::Exit = event {
            shutdown(port, &for_exit);
        }
    });
}
