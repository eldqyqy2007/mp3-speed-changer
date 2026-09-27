&lt;p align="center"&gt;
  &lt;img src="./assets/banner.svg" alt="MP3 Speed Changer banner" width="100%"&gt;
&lt;/p&gt;

&lt;p align="center"&gt;
  &lt;a href="LICENSE"&gt;&lt;img src="https://img.shields.io/badge/license-MIT-blue?labelColor=555" alt="license: MIT"&gt;&lt;/a&gt;
  &lt;img src="https://img.shields.io/badge/python-3.7%2B-yellow?labelColor=555&amp;logo=python&amp;logoColor=white" alt="python: 3.7+"&gt;
  &lt;img src="https://img.shields.io/badge/ffmpeg-required-orange?labelColor=555" alt="ffmpeg: required"&gt;
  &lt;img src="https://img.shields.io/badge/termux-friendly-green?labelColor=555" alt="termux: friendly"&gt;
&lt;/p&gt;

# MP3 Speed Changer

A command-line tool that speeds up entire folders of MP3 files while **preserving natural pitch**. It is built for long recordings (lectures, audiobooks, podcasts) and is **resumable**: if the process is interrupted, just run it again and it continues where it stopped.

Powered by [FFmpeg](https://ffmpeg.org/)'s `atempo` filter. No third-party Python packages are required.

```
lecture.mp3  --  1.5x, pitch preserved  --&gt;  lecture_1.5x.mp3
```

---

## Table of contents

- [Why this tool](#why-this-tool)
- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
- [Output](#output)
- [How it works](#how-it-works)
- [Configuration](#configuration)
- [Honest limitations](#honest-limitations)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

---

## Why this tool

Standard speed controls in most media players either distort pitch (the "chipmunk" effect) or only apply to one file at a time. This tool is built for the specific case of **long spoken-word audio in bulk**: a full folder of lecture recordings or audiobook chapters that all need to play faster, at a natural voice pitch, without babysitting the process file by file.

It is also built to survive interruption. Long batches on a phone can get killed by the OS, lose power, or lose a connection mid-run; this tool resumes from the last completed chunk instead of starting over.

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
git clone https://github.com/eldqyqy2007/mp3-speed-changer.git
cd mp3-speed-changer
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

## How it works

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

## Honest limitations

- **Only `.mp3` files are supported.** Other audio formats are ignored.
- **Only the selected folder is scanned** — sub-folders are not searched.
- **Output is always re-encoded at 96 kbps**, regardless of the source bitrate. This keeps files small and consistent but is a lossy re-encode every time, including on files that were already lower quality.
- **No progress persistence across different speed values.** Resuming only works if you re-run with the *same* speed you started with; switching speeds on a resumed run starts that file over.
- **No automated test suite.** The tool has been used and manually verified, but there is no CI or unit test coverage yet.
- **Not benchmarked at scale.** There are no formal numbers for throughput or accuracy — this is a practical utility, not a research project.

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

## Contributing

Issues and pull requests are welcome. If you find a bug or have an idea for an improvement, please open an issue.

## License

This project is licensed under the [MIT License](LICENSE).
