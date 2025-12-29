# cleanvid

**cleanvid** is originally the work of [mmguero](https://github.com/mmguero). This fork has been modified to add a GUI, work better in windows, and to add other features. Install instructions are a work in progress and most of what's below tells you how to install mmguero's version, it will be updated in the future to install this version.

**cleanvid** is a little script to mute profanity in video files in a few simple steps:

1. The user provides as input a video file and matching `.srt` subtitle file. If subtitles are not provided explicitly, they will be extracted from the video file if possible; if not, [`subliminal`](https://github.com/Diaoul/subliminal) is used to attempt to download the best matching `.srt` file.
2. Optionally (using the `--alass` flag), [`alass`](https://github.com/kaegi/alass) (Automatic Language-Agnostic Subtitle Synchronization) can be used to synchronize the obtained subtitles with the video's audio track, correcting offsets and timing issues.
3. [`pysrt`](https://github.com/byroot/pysrt) is used to parse the (potentially synchronized) `.srt` file, and each entry is checked against a [list](./src/cleanvid/swears.txt) of profanity or other words or phrases you'd like muted. Mappings can be provided (eg., map "sh\*t" to "poop"), otherwise the word will be replaced with **\***.
4. A new "clean" `.srt` file is created. with _only_ those phrases containing the censored/replaced objectional language (unless `--full-subs` is used).
5. [`ffmpeg`](https://www.ffmpeg.org/) is used to create a cleaned video file. This file contains the original video stream, but the specified audio stream is muted during the segments containing objectional language. That audio stream is re-encoded and remultiplexed back together with the video. Optionally, the clean `.srt` file can be embedded in the cleaned video file as a subtitle track.

You can then use your favorite media player to play the cleaned video file together with the cleaned subtitles.

As an alternative to creating a new video file, cleanvid can create a simple EDL file (see the [mplayer](http://www.mplayerhq.hu/DOCS/HTML/en/edl.html) or KODI [documentation](https://kodi.wiki/view/Edit_decision_list)) or a custom JSON definition file for [PlexAutoSkip](https://github.com/mdhiggins/PlexAutoSkip).

**cleanvid** is part of a family of projects with similar goals:

- 📼 [cleanvid](https://github.com/mmguero/cleanvid) for video files (using [SRT-formatted](https://en.wikipedia.org/wiki/SubRip#Format) subtitles)
- 🎤 [monkeyplug](https://github.com/mmguero/monkeyplug) for audio and video files (using either [Whisper](https://openai.com/research/whisper) or the [Vosk](https://alphacephei.com/vosk/)-[API](https://github.com/alphacep/vosk-api) for speech recognition)
- 📕 [montag](https://github.com/mmguero/montag) for ebooks

## Installation

Using `pip`, to install the latest [release from PyPI](https://pypi.org/project/cleanvid/):

```
python3 -m pip install -U cleanvid
```

Or to install directly from GitHub:

```
python3 -m pip install -U 'git+https://github.com/mmguero/cleanvid'
```

## Prerequisites

[cleanvid](./src/cleanvid/cleanvid.py) requires:

- Python 3
- [FFmpeg](https://www.ffmpeg.org)
- [babelfish](https://github.com/Diaoul/babelfish)
- [delegator.py](https://github.com/kennethreitz/delegator.py)
- [pysrt](https://github.com/byroot/pysrt)
- [subliminal](https://github.com/Diaoul/subliminal)
- [alass](https://github.com/kaegi/alass)\* (Optional, needed for `--alass` synchronization)

To install FFmpeg, use your operating system's package manager or install binaries from [ffmpeg.org](https://www.ffmpeg.org/download.html). The Python dependencies will be installed automatically if you are using `pip` to install cleanvid. To use the optional subtitle synchronization feature, install [alass](https://github.com/kaegi/alass) from its repository and ensure the executable (e.g., `alass.bat` on Windows) is in your system's PATH.

## usage

```
usage: cleanvid [-h] [-s <srt>] -i <input video> [-o <output video>] [--plex-auto-skip-json <output JSON>] [--plex-auto-skip-id <content identifier>] [--subs-output <output srt>]
                [-w <profanity file>] [-l <language>] [-p <int>] [-e] [-f] [--subs-only] [--offline] [--edl] [--json] [--re-encode-video] [--re-encode-audio] [-b] [-v VPARAMS] [-a APARAMS]
                [-d] [--audio-stream-index <int>] [--audio-stream-list] [--threads-input <int>] [--threads-encoding <int>] [--threads <int>]

options:
  -h, --help            show this help message and exit
  -s <srt>, --subs <srt>
                        .srt subtitle file (will attempt auto-download if unspecified and not --offline)
  -i <input video>, --input <input video>
                        input video file
  -o <output video>, --output <output video>
                        output video file
  --plex-auto-skip-json <output JSON>
                        custom JSON file for PlexAutoSkip (also implies --subs-only)
  --plex-auto-skip-id <content identifier>
                        content identifier for PlexAutoSkip (also implies --subs-only)
  --subs-output <output srt>
                        output subtitle file
  -w <profanity file>, --swears <profanity file>
                        text file containing profanity (with optional mapping)
  -l <language>, --lang <language>
                        language for extracting srt from video file or srt download (default is "eng")
  -p <int>, --pad <int>
                        pad (seconds) around profanity
  -e, --embed-subs      embed subtitles in resulting video file
  -f, --full-subs       include all subtitles in output subtitle file (not just scrubbed)
  --fast-index          can improve navigation on some smart tvs by moving the fast seeking index to the start of an mp4
  --subs-only           only operate on subtitles (do not alter audio)
  --offline             don't attempt to download subtitles
  --edl                 generate MPlayer EDL file with mute actions (also implies --subs-only)
  --json                generate JSON file with muted subtitles and their contents
  --re-encode-video     Re-encode video
  --re-encode-audio     Re-encode audio
  -b, --burn            Hard-coded subtitles (implies re-encode)
  -v VPARAMS, --video-params VPARAMS
                        Video parameters for ffmpeg (only if re-encoding)
  -a APARAMS, --audio-params APARAMS
                        Audio parameters for ffmpeg
  -d, --downmix         Downmix to stereo (if not already stereo)
  --audio-stream-index <int>
                        Index of audio stream to process
  --audio-stream-list   Show list of audio streams (to get index for --audio-stream-index)
  --threads-input <int>
                        ffmpeg global options -threads value
  --threads-encoding <int>
                        ffmpeg encoding options -threads value
  --threads <int>       ffmpeg -threads value (for both global options and encoding)
  --chapter             When specified, ffmpeg will add chapter markers to the output video at the beginning of each segment that is muted. This can be useful for quickly navigating to and verifying the muted sections. This option is off by default. The CleanVid GUI also provides a checkbox to enable this feature.
  --alass               Attempt to synchronize subtitles with video using alass before cleaning (requires alass in PATH)
  --win                 Use Windows-compatible multi-step processing (try this if you encounter errors on Windows, especially command-line length errors)
```

Alternately, you can use the experimental cleanvidgui.py to pass all of the above options through checkboxes and fields. The gui relies on additional libraries customtkinter and tkinterdnd2.

### GUI Queue Feature

The Cleanvid GUI includes a powerful queue system to process multiple video files efficiently:

- **Queue Panel**: A dedicated panel on the right side of the GUI displays the video processing queue.
- **Adding Files**:
  - Click the `+` button at the top of the queue panel to open a file dialog and select one or more video files.
  - (Future: Drag-and-drop functionality may be supported).
- **Settings per Batch**: When you add a batch of files, the settings currently selected in the "Options" tabs (e.g., swears file, output formats, encoding parameters) are locked in specifically for those files. If you change the settings and then add another batch of files, the new settings will apply only to that new batch.
- **Managing the Queue**:
  - **Remove File**: Click the trash can icon (🗑️) next to any file in the queue to remove it.
  - **Clear Queue**: Click the `x` button at the top of the queue panel to remove all files from the queue.
  - **View Settings**: Hover your mouse over a file in the queue to see a tooltip displaying the specific settings that are locked in for that file.
- **Processing the Queue**:
  - Click the "Run Queue" button (this button may also say "Clean Video" if the queue is empty but a single job is defined by the main input fields) to start processing all files in the queue sequentially.
  - The GUI will process one file at a time, using its associated settings. Output and errors for each file will be displayed in the console area.
- **Pausing and Resuming**:
  - While the queue is processing, a "Pause" button will become available. Clicking it will pause the queue after the currently processing file is completed.
  - The button will then change to "Resume", allowing you to continue processing the queue from where it left off.
- **Queue Persistence**: If you close the Cleanvid GUI while there are files remaining in the queue (either waiting or if processing was paused), the queue will be automatically saved. When you next start the GUI, these pending items will be reloaded into the queue.
- **Help**: Click the `?` button at the top of the queue panel for a summary of these instructions within the application.

This queue system allows for flexible batch processing with different settings applied to different sets of videos.

### Docker

Alternately, a [Dockerfile](./docker/Dockerfile) is provided to allow you to run cleanvid in Docker. You can build the `oci.guero.org/cleanvid:latest` Docker image with [`build_docker.sh`](./docker/build_docker.sh), then run [`cleanvid-docker.sh`](./docker/cleanvid-docker.sh) inside the directory where your video/subtitle files are located.

## Contributing

If you'd like to help improve cleanvid, pull requests will be welcomed!

## Authors

- **Seth Grover** - _Initial work_ - [mmguero](https://github.com/mmguero)

## License

This project is licensed under the BSD 3-Clause License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

Thanks to:

- the developers of [FFmpeg](https://www.ffmpeg.org/about.html)
- [Mattias Wadman](https://github.com/wader) for his [ffmpeg](https://github.com/wader/static-ffmpeg) image
- [delegator.py](https://github.com/kennethreitz/delegator.py) developer Kenneth Reitz and contributors
- [pysrt](https://github.com/byroot/pysrt) developer Jean Boussier and contributors
- [subliminal](https://github.com/Diaoul/subliminal) developer Antoine Bertin and contributors
- [`alass`](https://github.com/kaegi/alass) developer Kaegi and contributors
