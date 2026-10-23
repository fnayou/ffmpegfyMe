import subprocess, json, sys, time, re, ipaddress, os
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


def run_ffmpeg(
    command: List[str],
    on_output: Optional[Callable[[str], None]] = None,
) -> int:
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        while process.poll() is None:
            line = process.stdout.readline()
            if line and ("frame=" in line or "size=" in line or "time=" in line):
                safe_line = _redact_line(command, line)
                if on_output is not None:
                    on_output(safe_line)
                print(f"\r{safe_line.strip()}", end='')
        print()

        return process.returncode

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
) -> bool:
    parsed_url = urllib.parse.urlparse(url)
    if not all([parsed_url.scheme, parsed_url.netloc]):
        print("❌ Invalid URL format.")
        return False

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        print(f"⏳ Starting download to {output_path.name}...")

        cmd: List[str] = [
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
            '-bsf:a', 'aac_adtstoasc',
            '-stats',
            '-loglevel', 'warning',
            str(output_path)
        ]

        def report_progress(line: str) -> None:
            safe_line = _redact_line(cmd, line)
            print(f"\r{safe_line.strip()}", end='')

        exit_code = (runner or run_ffmpeg)(cmd, on_output=report_progress)
        return exit_code == 0

    except subprocess.SubprocessError as e:
        print(f"❌ FFmpeg error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False


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


def download_with_retry(item: Dict[str, str], output_path: Path, max_retries: int = 2, runner: Optional[Callable] = None) -> bool:
    try:
        headers, cookies = resolve_request_auth(item)
    except ValueError:
        print("❌ Authentication configuration error. Download skipped.")
        return False

    for attempt in range(max_retries + 1):
        if attempt > 0:
            print(f"⚠️ Retry attempt {attempt}/{max_retries}...")
            time.sleep(2)

        if download_stream(item['url'], output_path, runner=runner, headers=headers, cookies=cookies):
            return True

    return False


def main(runner: Optional[Callable] = None) -> None:
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

    if state_file.exists():
        print(f"\n📄 Found saved progress for this batch: {state_file}")
        reset = input("🔁 Do you want to reset progress and start from the beginning? (y/N): ").strip().lower()
        if reset == 'y':
            save_state(state_file, 0)
            print("✅ Progress reset to the beginning.")

    print(f"\n📝 Progress file: {state_file}")
    print(f"💾 Output directory: {output_dir}\n")

    start_index = load_state(state_file)
    if start_index >= len(downloads):
        print("✅ All downloads already completed!")
        sys.exit(0)

    use_saved = input(f"▶️  Continue from last saved index {start_index}? (Y/n): ").strip().lower() or 'y'
    if use_saved != 'y':
        start_index = interactive_menu(downloads)

    display_download_summary(downloads, start_index)

    print("⚙️  Choose download mode:")
    print("   [1] Manual (ask for each link)")
    print("   [2] Automatic (download all remaining files)")

    while True:
        mode = input("Enter your choice [1/2]: ").strip()
        if mode in ['1', '2']:
            break
        print("❗ Invalid choice. Please enter 1 or 2.")

    for i in range(start_index, len(downloads)):
        item = downloads[i]
        safe_filename = validate_output_filename(item['output'])
        output_path = output_dir / safe_filename

        if output_path.exists():
            print(f"⏩ Skipped (already exists): {output_path.name}")
            save_state(state_file, i + 1)
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

        success = download_with_retry(item, output_path, runner=runner)

        if success:
            print(f"✅ Successfully downloaded: {safe_filename}")
            save_state(state_file, i + 1)
        else:
            print(f"❌ Failed to download: {safe_filename} after retries")
            if mode == '1':
                retry = input("Continue with next download? (Y/n): ").strip().lower() or 'y'
                if retry != 'y':
                    print("👋 Exiting.")
                    break
            else:
                print("⏭️  Skipping and continuing in auto mode.")
                save_state(state_file, i + 1)

    print("\n✅ All done with ffmpegfyMe!")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️ Download interrupted by user")
        print("👋 Exiting ffmpegfyMe - progress has been saved")
        sys.exit(0)
