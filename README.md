# MP3 Speed Changer

A command-line tool that speeds up entire folders of MP3 files while **preserving natural pitch**. It is built for long recordings (lectures, audiobooks, podcasts) and is **resumable**: if the process is interrupted, just run it again and it continues where it stopped.

Powered by [FFmpeg](https://ffmpeg.org/)'s `atempo` filter. No third-party Python packages are required.

---

## Features

- **Pitch-preserving speed-up** – voices stay natural, no "chipmunk" effect.
- **Batch processing** – converts every `.mp3` file in a folder in one run.
- **Chunked & parallel** – each file is split into 5-minute chunks processed in parallel across all CPU cores.
- **Resumable** – interrupted runs (app closed, phone restarted, power loss) pick up from the last finished chunk; already-completed files are skipped.
- **Flexible speeds** – presets (1.1x, 1.2x, 1.3x, 1.5x, 1.75x, 2.0x) or any custom value, including speeds above 2.0x via automatic filter chaining.
- **Interactive menu** – choose a folder and speed step by step, with a live progress bar.
- **Detailed final report** – files processed / skipped / failed, total size before and after, and total time taken.
- **Arabic / RTL filename support** – correct display in terminals that lack bidi support (optional `python-bidi`).
- **Termux friendly** – designed to run well on Android.

---

## Requirements

| Requirement | Notes |
|---|---|
| Python | 3.7 or newer |
| FFmpeg | Must be available in your `PATH` |
| python-bidi *(optional)* | Only for correct display of Arabic filenames |

### Install FFmpeg

**Termux (Android)**
```bash
pkg update
pkg install python ffmpeg
```

**Ubuntu / Debian**
```bash
sudo apt install ffmpeg
```

**macOS (Homebrew)**
```bash
brew install ffmpeg
```

**Windows**
Download FFmpeg from [ffmpeg.org](https://ffmpeg.org/download.html) and add its `bin` folder to your `PATH`.

### Optional: Arabic filename support
```bash
pip install python-bidi
```

---

## Installation

```bash
git clone https://github.com/<your-username>/<your-repo>.git
cd <your-repo>
```

Or simply download `speed_up_audio.py` and run it directly.

---

## Usage

### Interactive mode
```bash
python3 speed_up_audio.py
```

### With a folder path
```bash
python3 speed_up_audio.py /path/to/your/mp3/folder
```

On Termux, the shared storage folder is usually under `~/storage/shared/` (run `termux-setup-storage` once to enable access):
```bash
python3 speed_up_audio.py ~/storage/shared/Download/lectures
```

### Walkthrough

1. Start the tool and choose **1. Start**.
2. Enter the folder path (skipped if you passed it as an argument).
3. The tool lists all MP3 files it found, with their sizes.
4. Pick a speed:

   | Option | Speed |
   |---|---|
   | 1 | 1.1x |
   | 2 | 1.2x |
   | 3 | 1.3x |
   | 4 | 1.5x |
   | 5 | 1.75x |
   | 6 | 2.0x |
   | 7 | Custom (e.g. `1.35`) |

5. Wait for processing to finish and review the final report.

---

## Output

Results are saved in a new sub-folder next to your originals. **Your original files are never modified.**

```
my_folder/
├── lecture1.mp3
├── lecture2.mp3
└── sped_up_1.5x/
    ├── lecture1_1.5x.mp3
    ├── lecture2_1.5x.mp3
    └── .completed.txt      # progress log used for resuming
```

Output files are encoded at **96 kbps**, which usually makes them smaller than high-bitrate originals.

---

## How It Works

For each MP3 file, the tool runs four steps:

1. **Copy** the file to a local working directory (`~/.speed_up_audio_work`), which is more reliable than working on shared storage.
2. **Split** it into 5-minute chunks (without re-encoding).
3. **Speed up** the chunks in parallel using FFmpeg's `atempo` filter.
4. **Join** the processed chunks into one MP3 and save it to the output folder.

Temporary files are removed once a file finishes. If the tool is interrupted, the working directory keeps the finished chunks, so the next run continues from there.

FFmpeg's `atempo` filter only supports speeds between 0.5x and 2.0x, so for values outside that range the tool automatically chains several filters together (e.g. 3.0x → `atempo=2.0,atempo=1.5`).

---

## Configuration

You can adjust these constants at the top of `speed_up_audio.py`:

| Constant | Default | Description |
|---|---|---|
| `CHUNK_SECONDS` | `300` | Length of each chunk in seconds |
| `MAX_WORKERS` | CPU core count | Number of chunks processed in parallel |
| `SPEED_OPTIONS` | `1.1 … 2.0, Custom` | Speed presets shown in the menu |

If your device gets hot or runs out of memory, lower `MAX_WORKERS` (for example to `2`).

---

## Troubleshooting

**`ERROR: ffmpeg is not installed or not found in PATH`**
Install FFmpeg (see [Requirements](#requirements)) and make sure `ffmpeg -version` works in your terminal.

**Arabic filenames look reversed or broken**
Run `pip install python-bidi` and start the tool again.

**The folder is not found on Termux**
Run `termux-setup-storage`, allow storage permission, then use a path under `~/storage/shared/`.

**A file failed to process**
Re-run the tool. Finished files and chunks are skipped automatically, and only the failed part is retried.

**I want to re-process a file with the same speed**
Delete its output file and remove its name from `.completed.txt` inside the output folder.

---

## Limitations

- Only `.mp3` files are supported.
- Only the selected folder is scanned (sub-folders are not searched).
- Output is always re-encoded at 96 kbps.

---

## Contributing

Issues and pull requests are welcome. If you find a bug or have an idea for an improvement, please open an issue.

## License

Add a license of your choice (for example [MIT](https://choosealicense.com/licenses/mit/)) by creating a `LICENSE` file in the repository.
