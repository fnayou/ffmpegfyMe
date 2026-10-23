import subprocess, json, sys, time, re
from pathlib import Path
from typing import Callable, List, Dict, Optional
import urllib.parse

# === ffmpegfyMe Configuration ===
PROJECT_NAME = "ffmpegfyMe"
IN_DIR = Path("in")
OUT_DIR = Path("out")
PROGRESS_DIR = Path("progress")
MAX_STABLE_ID_LENGTH = 128
ALLOWED_ITEM_FIELDS = {"url", "output", "id"}


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
    if any(ord(char) < 32 or ord(char) == 127 or char.isspace() for char in url):
        return False
    parsed = urllib.parse.urlparse(url)
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
    if any(ord(char) < 32 or ord(char) == 127 for char in filename):
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
    if any(ord(char) < 32 or ord(char) == 127 for char in item_id):
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

        if output in seen_outputs:
            print(f"❌ Duplicate output destination at entry index {index}.")
            sys.exit(1)
        seen_outputs.add(output)

        entry = {"url": url, "output": output}
        if stable_id is not None:
            entry["id"] = stable_id
        downloads.append(entry)

    return downloads


def validate_output_filename(filename: str) -> str:
    if not _is_valid_output_filename(filename):
        print("❌ Invalid output filename.")
        sys.exit(1)
    return filename


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
                if on_output is not None:
                    on_output(line)
                print(f"\r{line.strip()}", end='')
        print()

        return process.returncode

    except subprocess.SubprocessError as e:
        print(f"❌ FFmpeg error: {e}")
        return 1
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return 1


def download_stream(url: str, output_path: Path, runner: Optional[Callable] = None) -> bool:
    parsed_url = urllib.parse.urlparse(url)
    if not all([parsed_url.scheme, parsed_url.netloc]):
        print("❌ Invalid URL format.")
        return False

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        print(f"⏳ Starting download to {output_path.name}...")

        cmd = [
            'ffmpeg', '-y',
            '-i', url,
            '-c', 'copy',
            '-bsf:a', 'aac_adtstoasc',
            '-stats',
            '-loglevel', 'warning',
            str(output_path)
        ]

        def report_progress(line: str) -> None:
            print(f"\r{line.strip()}", end='')

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
        print(f"{idx}: {item['output']} — {item['url']}")
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
    for attempt in range(max_retries + 1):
        if attempt > 0:
            print(f"⚠️ Retry attempt {attempt}/{max_retries}...")
            time.sleep(2)

        if download_stream(item['url'], output_path, runner=runner):
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
        print(f"➡️  From: {item['url']}")
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
            print(f"❌ Failed to download: {item['url']} after retries")
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
