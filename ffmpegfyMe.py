import subprocess, json, sys, time, re, ipaddress, os, hashlib, tempfile, random, selectors, math
from pathlib import Path
from typing import Any, Callable, List, Dict, Optional, Tuple
import urllib.parse

# === ffmpegfyMe Configuration ===
PROJECT_NAME = "ffmpegfyMe"
IN_DIR = Path("in")
OUT_DIR = Path("out")
PROGRESS_DIR = Path("progress")
MAX_STABLE_ID_LENGTH = 128
ALLOWED_ITEM_FIELDS = {"url", "output", "id", "headers", "cookies"}
ENV_REFERENCE_PATTERN = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")
HTTP_TOKEN_PATTERN = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")


def _is_valid_env_reference(value: Any) -> bool:
    return isinstance(value, str) and ENV_REFERENCE_PATTERN.fullmatch(value) is not None


def _is_valid_http_token_header_name(name: Any) -> bool:
    return isinstance(name, str) and HTTP_TOKEN_PATTERN.fullmatch(name) is not None


def list_json_files() -> List[Path]:
    return sorted([f for f in IN_DIR.glob("*.json")])


def choose_json_file() -> Path:
    files = list_json_files()
    if not files:
        print("❌ No JSON files found in /in/")
        sys.exit(1)

    print(f"\n📂 Available JSON files in {IN_DIR}/:")
    for idx, file in enumerate(files):
        print(f"{idx}: {file.name}")

    while True:
        choice = input("\nSelect the JSON file to use by index: ").strip()
        if choice.isdigit() and 0 <= int(choice) < len(files):
            return files[int(choice)]
        print("❗ Invalid input.")


def prompt_download_dir(default_path: Path) -> Path:
    response = input(f"\n📁 Download directory [default: {default_path}]: ").strip()
    return Path(response) if response else default_path


def load_state(state_file: Path) -> int:
    try:
        with open(state_file) as f:
            return json.load(f)['last_index']
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return 0


def save_state(state_file: Path, index: int) -> None:
    with open(state_file, 'w') as f:
        json.dump({"last_index": index}, f)


ITEM_STATE_VERSION = 1
ITEM_STATUSES = ("pending", "succeeded", "failed")


def item_state_key(item: Dict[str, Any]) -> str:
    """Resume key: stable id plus output when id supplied, else SHA-256 of full URL plus output."""
    stable_id = item.get("id")
    output = item.get("output") or ""
    if isinstance(stable_id, str) and stable_id:
        return f"stable:{stable_id}:{output}"
    url = item.get("url") or ""
    digest_source = json.dumps([url, output], separators=(",", ":"), sort_keys=True)
    digest = hashlib.sha256(digest_source.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def item_is_complete(item_state: Optional[Dict[str, Any]], output_path: Path) -> bool:
    """True only when item succeeded, output filename matches, and file exists."""
    return (
        isinstance(item_state, dict)
        and item_state.get("status") == "succeeded"
        and item_state.get("output") == output_path.name
        and output_path.is_file()
    )


def process_download_item(item: Dict[str, Any], output_path: Path, state_file: Path, item_states: Dict[str, Dict[str, Any]], runner: Optional[Callable] = None, allow_overwrite: bool = False, inactivity_timeout: Optional[float] = None) -> bool:
    key = item_state_key(item)

    if item_is_complete(item_states.get(key), output_path):
        return True

    if output_path.exists() and not allow_overwrite:
        item_states[key] = {"status": "failed", "output": output_path.name}
        save_item_state(state_file, item_states)
        print(f"❌ Conflict: output file already exists: {output_path.name}")
        return False

    item_states[key] = {"status": "pending", "output": output_path.name}
    save_item_state(state_file, item_states)

    success = download_with_retry(item, output_path, runner=runner, allow_overwrite=allow_overwrite, inactivity_timeout=inactivity_timeout)

    item_states[key] = {"status": "succeeded" if success else "failed", "output": output_path.name}
    save_item_state(state_file, item_states)

    return success


def load_item_state(state_file: Path) -> Dict[str, Dict[str, Any]]:
    """Load per-item state mapping; missing or corrupt state yields empty mapping."""
    try:
        with open(state_file) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    items = data.get("items")
    if not isinstance(items, dict):
        return {}
    return {str(key): entry for key, entry in items.items() if isinstance(entry, dict)}


def is_legacy_progress_state(state_file: Path) -> bool:
    """True when state contains a legacy index without per-item state."""
    try:
        with open(state_file) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return False
    return (
        isinstance(data, dict)
        and "last_index" in data
        and "items" not in data
        and isinstance(data["last_index"], int)
        and not isinstance(data["last_index"], bool)
    )


def save_item_state(state_file: Path, items: Dict[str, Dict[str, Any]]) -> None:
    """Atomically persist per-item state via sibling temp file and os.replace."""
    state_file.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(state_file.parent), prefix=f".{state_file.name}.", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump({"version": ITEM_STATE_VERSION, "items": items}, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, state_file)
    except BaseException:
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise


def _is_valid_http_url(url: str) -> bool:
    if not isinstance(url, str) or not url:
        return False
    if any(ord(char) < 32 or 0x7F <= ord(char) <= 0x9F or char.isspace() for char in url):
        return False
    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    if not parsed.netloc or parsed.username is not None or parsed.password is not None:
        return False
    try:
        port = parsed.port
    except ValueError:
        return False
    if port is not None and not 0 <= port <= 65535:
        return False
    host = parsed.hostname or ""
    if ":" in host:
        try:
            ipaddress.ip_address(host)
        except ValueError:
            return False
    else:
        host_pattern = r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)*"
        if not re.fullmatch(host_pattern, host):
            return False
    return True


def _is_valid_output_filename(filename: str) -> bool:
    if not isinstance(filename, str) or not filename:
        return False
    if filename in (".", ".."):
        return False
    if "/" in filename or "\\" in filename:
        return False
    if any(ord(char) < 32 or 0x7F <= ord(char) <= 0x9F for char in filename):
        return False
    if not filename.strip():
        return False
    if os.path.splitext(filename)[1].lower() not in (".mp4", ".mkv"):
        return False
    return True


def _is_valid_stable_id(item_id: str) -> bool:
    """Stable ids are public batch identifiers; must not contain secrets."""
    if not isinstance(item_id, str) or not item_id:
        return False
    if len(item_id) > MAX_STABLE_ID_LENGTH:
        return False
    if any(ord(char) < 32 or 0x7F <= ord(char) <= 0x9F for char in item_id):
        return False
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", item_id):
        return False
    if item_id in (".", ".."):
        return False
    return True


def load_downloads(json_file: Path) -> List[Dict[str, str]]:
    try:
        with open(json_file) as f:
            data = json.load(f)
    except json.JSONDecodeError:
        print("❌ Error: Invalid JSON format.")
        sys.exit(1)
    except FileNotFoundError:
        print(f"❌ File not found: {json_file}")
        sys.exit(1)

    if not isinstance(data, list):
        print("❌ Error: JSON must be a list of objects.")
        sys.exit(1)

    downloads: List[Dict[str, str]] = []
    seen_ids = set()
    seen_outputs = set()

    for index, item in enumerate(data):
        if not isinstance(item, dict):
            print(f"❌ Invalid entry at index {index}. Must be an object.")
            sys.exit(1)

        unknown_fields = sorted(set(item) - ALLOWED_ITEM_FIELDS)
        if unknown_fields:
            print(f"❌ Invalid entry at index {index}. Unknown fields: {', '.join(unknown_fields)}.")
            sys.exit(1)

        if "url" not in item or "output" not in item:
            print(f"❌ Invalid entry at index {index}. Must contain 'url' and 'output'.")
            sys.exit(1)

        url = item["url"]
        output = item["output"]
        if not _is_valid_http_url(url):
            print(f"❌ Invalid URL at entry index {index}. Must be a nonempty absolute HTTP/HTTPS URL.")
            sys.exit(1)

        if not _is_valid_output_filename(output):
            print(f"❌ Invalid output filename at entry index {index}.")
            sys.exit(1)

        stable_id = None
        if "id" in item:
            stable_id = item["id"]
            if not _is_valid_stable_id(stable_id):
                print(f"❌ Invalid stable id at entry index {index}. Must be a safe identifier.")
                sys.exit(1)
            if stable_id in seen_ids:
                print(f"❌ Duplicate stable id at entry index {index}.")
                sys.exit(1)
            seen_ids.add(stable_id)

        if output.casefold() in seen_outputs:
            print(f"❌ Duplicate output destination at entry index {index}.")
            sys.exit(1)
        seen_outputs.add(output.casefold())

        headers: Optional[Dict[str, str]] = None
        cookies: Optional[str] = None
        if "headers" in item:
            headers = item["headers"]
            if not isinstance(headers, dict):
                print(f"❌ Invalid headers at entry index {index}. Must be an object mapping header names to environment references.")
                sys.exit(1)
            seen_header_names = set()
            for header_name, header_value in headers.items():
                if not _is_valid_http_token_header_name(header_name):
                    print(f"❌ Invalid header name at entry index {index}. Must be a valid HTTP token header name.")
                    sys.exit(1)
                lowered_name = header_name.lower()
                if lowered_name in seen_header_names:
                    print(f"❌ Duplicate header name at entry index {index}. Header names must be unique.")
                    sys.exit(1)
                seen_header_names.add(lowered_name)
                if not _is_valid_env_reference(header_value):
                    print(f"❌ Invalid header value at entry index {index}. Must be an environment variable reference.")
                    sys.exit(1)
        if "cookies" in item:
            cookies = item["cookies"]
            if not _is_valid_env_reference(cookies):
                print(f"❌ Invalid cookies at entry index {index}. Must be a single environment variable reference.")
                sys.exit(1)

        entry = {"url": url, "output": output}
        if stable_id is not None:
            entry["id"] = stable_id
        if headers is not None:
            entry["headers"] = headers
        if cookies is not None:
            entry["cookies"] = cookies
        downloads.append(entry)

    return downloads


def resolve_request_auth(
    item: Dict[str, Any],
    environment: Optional[Dict[str, str]] = None,
) -> Tuple[Dict[str, str], Optional[str]]:
    env: Dict[str, str] = dict(environment) if environment is not None else dict(os.environ)

    resolved_headers: Dict[str, str] = {}
    headers = item.get("headers") or {}
    for header_name, header_value in headers.items():
        if not _is_valid_env_reference(header_value):
            raise ValueError("Authentication header value must be an environment variable reference.")
        env_name = ENV_REFERENCE_PATTERN.fullmatch(header_value).group(1)
        resolved_value = env.get(env_name)
        if not isinstance(resolved_value, str) or resolved_value == "":
            raise ValueError("Authentication environment value is missing or empty.")
        if any(ord(char) < 32 or 0x7F <= ord(char) <= 0x9F for char in resolved_value):
            raise ValueError("Authentication header value contains unsupported characters.")
        resolved_headers[header_name] = resolved_value

    resolved_cookies: Optional[str] = None
    cookies = item.get("cookies")
    if cookies is not None:
        if not _is_valid_env_reference(cookies):
            raise ValueError("Authentication cookies must be an environment variable reference.")
        env_name = ENV_REFERENCE_PATTERN.fullmatch(cookies).group(1)
        resolved_cookies = env.get(env_name)
        if not isinstance(resolved_cookies, str) or resolved_cookies == "":
            raise ValueError("Authentication environment value is missing or empty.")
        if any(
            char != "\n" and (ord(char) < 32 or 0x7F <= ord(char) <= 0x9F)
            for char in resolved_cookies
        ):
            raise ValueError("Authentication cookies value contains unsupported characters.")

    if not resolved_headers and resolved_cookies is None:
        return {}, None
    return resolved_headers, resolved_cookies


def validate_output_filename(filename: str) -> str:
    if not _is_valid_output_filename(filename):
        print("❌ Invalid output filename.")
        sys.exit(1)
    return filename


REDACTED_PLACEHOLDER = "[REDACTED]"
FFMPEG_REDACTED_URL_PATTERN = re.compile(r"https?://[^\s]*", re.IGNORECASE)


def _redact_line(command: List[str], line: str) -> str:
    safe_line = line
    secret_values: List[str] = []
    for flag in ("-i", "-headers", "-cookies"):
        try:
            index = command.index(flag)
        except ValueError:
            continue
        if index + 1 < len(command):
            secret_values.append(command[index + 1])
    for value in secret_values:
        if value:
            safe_line = safe_line.replace(value, REDACTED_PLACEHOLDER)
    return FFMPEG_REDACTED_URL_PATTERN.sub(REDACTED_PLACEHOLDER, safe_line)


class FFmpegInactivityTimeout(Exception):
    """Raised when the ffmpeg subprocess produces no output within inactivity_timeout."""


class FFmpegProcessStartError(Exception):
    """Raised when the ffmpeg subprocess fails to start."""


class FFmpegOutputPromotionError(Exception):
    """Raised when the final output file could not be promoted from the temp file."""


def _run_ffmpeg_with_selector(
    process: "subprocess.Popen",
    command: List[str],
    on_output: Optional[Callable[[str], None]],
    inactivity_timeout: float,
) -> int:
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    start = time.monotonic()
    buffer = b""
    timed_out = False
    try:
        while True:
            if process.poll() is not None and not selector.select(0):
                break
            remaining = inactivity_timeout - (time.monotonic() - start)
            if remaining <= 0:
                timed_out = True
                break
            if not selector.select(remaining):
                timed_out = True
                break
            chunk = os.read(process.stdout.fileno(), 65536)
            if not chunk:
                remaining = inactivity_timeout - (time.monotonic() - start)
                if remaining <= 0:
                    timed_out = True
                    break
                try:
                    process.wait(timeout=remaining)
                except subprocess.TimeoutExpired:
                    timed_out = True
                    break
                if not buffer:
                    break
                chunk = bytes([10])
            start = time.monotonic()
            buffer += chunk.replace(bytes([13]), bytes([10]))
            while b"\n" in buffer:
                raw_line, buffer = buffer.split(b"\n", 1)
                line = raw_line.decode("utf-8", errors="replace")
                if line and ("frame=" in line or "size=" in line or "time=" in line):
                    safe_line = _redact_line(command, line)
                    if on_output is not None:
                        on_output(safe_line)
                    print(f"\r{safe_line.strip()}", end='')
                elif line:
                    safe_line = _redact_line(command, line)
                    print(safe_line, end="")
        if timed_out:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            raise FFmpegInactivityTimeout("FFmpeg inactivity timeout exceeded.")
        return process.returncode
    finally:
        selector.close()
        process.stdout.close()


def _resolve_ffmpeg_inactivity_timeout(value: Optional[float]) -> float:
    if value is None:
        value = os.environ.get("FFMPEG_INACTIVITY_TIMEOUT", "60")
    try:
        timeout = float(value)
    except (TypeError, ValueError):
        raise ValueError("FFMPEG_INACTIVITY_TIMEOUT must be a positive number") from None
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("FFMPEG_INACTIVITY_TIMEOUT must be a positive number")
    return timeout


def run_ffmpeg(
    command: List[str],
    on_output: Optional[Callable[[str], None]] = None,
    inactivity_timeout: Optional[float] = None,
) -> int:
    inactivity_timeout = _resolve_ffmpeg_inactivity_timeout(inactivity_timeout)
    try:
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
        except OSError as e:
            raise FFmpegProcessStartError("FFmpeg process failed to start.") from e

        if isinstance(process.stdout.fileno(), int):
            return _run_ffmpeg_with_selector(process, command, on_output, inactivity_timeout)

        while process.poll() is None:
            line = process.stdout.readline()
            if line and ("frame=" in line or "size=" in line or "time=" in line):
                safe_line = _redact_line(command, line)
                if on_output is not None:
                    on_output(safe_line)
                print(f"\r{safe_line.strip()}", end='')
            elif line:
                safe_line = _redact_line(command, line)
                print(safe_line, end="")
        print()

        return process.returncode

    except FFmpegInactivityTimeout:
        raise
    except FFmpegProcessStartError:
        raise
    except subprocess.SubprocessError:
        print("❌ FFmpeg error occurred.")
        return 1
    except Exception:
        print("❌ Unexpected error occurred.")
        return 1


def download_stream(
    url: str,
    output_path: Path,
    runner: Optional[Callable] = None,
    headers: Optional[Dict[str, str]] = None,
    cookies: Optional[str] = None,
    allow_overwrite: bool = False,
    inactivity_timeout: Optional[float] = None,
) -> bool:
    parsed_url = urllib.parse.urlparse(url)
    if not all([parsed_url.scheme, parsed_url.netloc]):
        print("❌ Invalid URL format.")
        return False

    if not allow_overwrite and output_path.exists():
        print("❌ Output file already exists. Use allow_overwrite to replace it.")
        return False

    cmd: List[str] = []
    temp_path: Optional[Path] = None

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        print(f"⏳ Starting download to {output_path.name}...")

        fd, tmp_name = tempfile.mkstemp(
            dir=str(output_path.parent),
            prefix=f".{output_path.stem}.",
            suffix=output_path.suffix,
        )
        os.close(fd)
        temp_path = Path(tmp_name)

        cmd = [
            'ffmpeg', '-y',
            '-protocol_whitelist', 'http,https,tcp,tls,crypto',
        ]
        if headers:
            cmd += ['-headers', "\r\n".join(f"{name}: {value}" for name, value in headers.items())]
        if cookies:
            cmd += ['-cookies', cookies]
        cmd += [
            '-i', url,
            '-c', 'copy',
            '-sn',
            '-dn',
            '-stats',
            '-loglevel', 'warning',
            str(temp_path)
        ]

        def report_progress(line: str) -> None:
            safe_line = _redact_line(cmd, line)
            print(f"\r{safe_line.strip()}", end='')

        if runner is not None:
            exit_code = runner(cmd, on_output=report_progress)
        else:
            exit_code = run_ffmpeg(cmd, on_output=report_progress, inactivity_timeout=inactivity_timeout)

        if exit_code == 0:
            try:
                if allow_overwrite:
                    os.replace(temp_path, output_path)
                else:
                    os.link(temp_path, output_path)
            except FileExistsError:
                raise FFmpegOutputPromotionError(
                    f"Output file already exists: {output_path.name}. Use allow_overwrite to replace it."
                )
            except OSError as e:
                raise FFmpegOutputPromotionError(f"Output promotion failed for {output_path.name}: {e}") from e
            return True

        return False

    except FFmpegProcessStartError:
        raise
    except FFmpegOutputPromotionError:
        raise
    except subprocess.SubprocessError as e:
        print(f"❌ FFmpeg error: {_redact_line(cmd, str(e))}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {_redact_line(cmd, str(e))}")
        return False
    finally:
        if temp_path is not None and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def interactive_menu(links: List[Dict[str, str]]) -> int:
    print("\n🎬 Available videos to download:\n")
    for idx, item in enumerate(links):
        print(f"{idx}: {item['output']}")
    print()

    while True:
        choice = input("Enter index to start from (or 'q' to quit): ").strip()
        if choice.lower() == 'q':
            sys.exit(0)
        if choice.isdigit() and 0 <= int(choice) < len(links):
            return int(choice)
        print("❗ Invalid input.")


def check_ffmpeg() -> bool:
    try:
        result = subprocess.run(["ffmpeg", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return result.returncode == 0
    except FileNotFoundError:
        return False


def display_download_summary(downloads: List[Dict[str, str]], start_index: int) -> None:
    remaining = len(downloads) - start_index
    print(f"\n📊 Download Summary:")
    print(f"   - Total items: {len(downloads)}")
    print(f"   - Starting at index: {start_index}")
    print(f"   - Items to download: {remaining}")

    print("\n🔜 Next downloads:")
    for i in range(start_index, min(start_index + 3, len(downloads))):
        print(f"   - {downloads[i]['output']}")
    if remaining > 3:
        print(f"   - ... and {remaining - 3} more")
    print()


def download_with_retry(item: Dict[str, str], output_path: Path, max_retries: int = 2, runner: Optional[Callable] = None, allow_overwrite: bool = False, inactivity_timeout: Optional[float] = None) -> bool:
    try:
        headers, cookies = resolve_request_auth(item)
    except ValueError:
        print("❌ Authentication configuration error. Download skipped.")
        return False

    inactivity_timeout = _resolve_ffmpeg_inactivity_timeout(inactivity_timeout)

    retries = max(0, min(max_retries, 2))
    for attempt in range(retries + 1):
        if attempt > 0:
            print(f"⚠️ Retry attempt {attempt}/{retries}...")
            if attempt == 1:
                time.sleep(random.uniform(1.5, 2.5))
            elif attempt == 2:
                time.sleep(random.uniform(5.0, 7.0))

        try:
            success = download_stream(item['url'], output_path, runner=runner, headers=headers, cookies=cookies, allow_overwrite=allow_overwrite, inactivity_timeout=inactivity_timeout)
        except FFmpegProcessStartError:
            print("❌ FFmpeg could not start. Download skipped.")
            return False
        except FFmpegOutputPromotionError as e:
            print(f"❌ {e} FFmpeg will not be retried.")
            return False
        if success:
            return True

    return False


def main(runner: Optional[Callable] = None) -> None:
    try:
        inactivity_timeout = _resolve_ffmpeg_inactivity_timeout(None)
    except ValueError as e:
        print(f"❌ Invalid FFmpeg inactivity timeout: {e}")
        sys.exit(1)

    IN_DIR.mkdir(exist_ok=True)
    OUT_DIR.mkdir(exist_ok=True)
    PROGRESS_DIR.mkdir(exist_ok=True)

    print(f"🎨 Welcome to {PROJECT_NAME} — your stream-to-file toolkit")

    if not check_ffmpeg():
        print("❌ FFmpeg is not installed or not found in PATH")
        sys.exit(1)

    json_file = choose_json_file()
    batch_name = json_file.stem
    default_output_path = OUT_DIR / batch_name
    output_dir = prompt_download_dir(default_output_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    downloads = load_downloads(json_file)
    if not downloads:
        print("⚠️ No downloads found in the JSON file")
        sys.exit(0)

    state_file = PROGRESS_DIR / f"{batch_name}_state.json"
    item_states = load_item_state(state_file)

    legacy_state = state_file.exists() and is_legacy_progress_state(state_file)
    if legacy_state:
        print(f"\n⚠️ Legacy progress found: {state_file}")
        print("The last_index cannot prove which outputs completed and is not valid per-item state.")
        reset = input("Replace it with empty versioned per-item state and restart? (y/N): ").strip().lower()
        if reset != 'y':
            print("👋 Exiting without changing progress or outputs.")
            sys.exit(0)
        item_states = {}
        save_item_state(state_file, item_states)
        print("✅ Legacy progress replaced with empty per-item state.")
    elif state_file.exists():
        print(f"\n📄 Found saved progress for this batch: {state_file}")
        reset = input("🔁 Do you want to reset progress and start from the beginning? (y/N): ").strip().lower()
        if reset == 'y':
            item_states = {}
            save_item_state(state_file, item_states)
            print("✅ Progress reset to the beginning.")

    print(f"\n📝 Progress file: {state_file}")
    print(f"💾 Output directory: {output_dir}\n")

    use_saved = input("▶️  Continue from saved per-item progress? (Y/n): ").strip().lower() or 'y'
    if use_saved != 'y':
        start_index = interactive_menu(downloads)
    else:
        start_index = 0

    display_download_summary(downloads, start_index)

    print("⚙️  Choose download mode:")
    print("   [1] Manual (ask for each link)")
    print("   [2] Automatic (download all remaining files)")

    while True:
        mode = input("Enter your choice [1/2]: ").strip()
        if mode in ['1', '2']:
            break
        print("❗ Invalid choice. Please enter 1 or 2.")

    failed_downloads: List[str] = []

    for i in range(start_index, len(downloads)):
        item = downloads[i]
        safe_filename = validate_output_filename(item['output'])
        output_path = output_dir / safe_filename

        if item_is_complete(item_states.get(item_state_key(item)), output_path):
            print(f"⏩ Skipped (already completed): {output_path.name}")
            continue

        print(f"\n🎧 Downloading [{i+1}/{len(downloads)}]: {safe_filename}")
        print(f"📁 To:   {output_path}")

        if mode == '1':
            action = input("Press Enter to start, [s]kip, or [q]uit: ").strip().lower()
            if action == 'q':
                print("👋 Exiting.")
                break
            elif action == 's':
                print("⏭️  Skipped.")
                continue

        allow_overwrite = False
        if output_path.exists() and mode == '1':
            overwrite_answer = input("Overwrite existing output? (y/N): ").strip().lower()
            allow_overwrite = overwrite_answer == 'y'

        success = process_download_item(
            item,
            output_path,
            state_file,
            item_states,
            runner=runner,
            allow_overwrite=allow_overwrite,
            inactivity_timeout=inactivity_timeout,
        )

        if success:
            print(f"✅ Successfully downloaded: {safe_filename}")
        else:
            failed_downloads.append(safe_filename)
            print(f"❌ Failed to download: {safe_filename} after retries")
            if mode == '1':
                retry = input("Continue with next download? (Y/n): ").strip().lower() or 'y'
                if retry != 'y':
                    print("👋 Exiting.")
                    break
            else:
                print("⏭️  Skipping and continuing in auto mode.")

    if failed_downloads:
        print("\n❌ Failed downloads:")
        for filename in failed_downloads:
            print(f"   - {filename}")

    print("\n✅ All done with ffmpegfyMe!")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️ Download interrupted by user")
        print("👋 Exiting ffmpegfyMe - progress has been saved")
        sys.exit(0)
