# TMDLang Media Syntax — Audio Remix & Video Editing

TMDLang now supports two additional file types beyond `::SCORE::`:

| Header | Purpose | Output |
|--------|---------|--------|
| `::REMIX::` | Audio remixing / beat-synced arrangement | `.wav` / `.mp3` |
| `::VIDEO::` | Video editing / short-video assembly | `.mp4` |

---

## Quick Start

```bash
# Audio remix (dry run — prints timeline without rendering)
python tmd.py remix_demo.tmd --dry-run

# Audio remix (render)
python tmd.py remix_demo.tmd -o my_remix.wav

# Video edit (dry run)
python tmd.py video_edit_demo.tmd --dry-run

# Video edit (render)
python tmd.py video_edit_demo.tmd -o promo.mp4 -r 1920x1080 --fps 30
```

**Prerequisite:** `ffmpeg` and `ffprobe` must be installed and on `$PATH`.

---

## File Structure

```
::REMIX::                           ← or ::VIDEO::
** Project Name **
! = 120                             ← BPM (still used as master clock)
? = C                               ← key (optional, for reference)
<4/4>                               ← time signature

~audio: "./audio"                   ← asset directory declarations
~footage: "./footage"

section:track@|timing|{             ← part block (same as SCORE)
    <timebase>                      ← time resolution
    content                         ← clips, effects, text, rests
}

-> section1 -> section2 ->#         ← playback order
```

---

## Time Base

### BPM-relative (inherited from SCORE)

```
<4*>     ← each unit = 1 quarter note  (at 120 BPM → 0.5s)
<16*>    ← each unit = 1 sixteenth note (at 120 BPM → 0.125s)
```

### Absolute time (new)

```
<T:0.5s*>         ← each unit = 0.5 seconds
<T:100ms*>        ← each unit = 100 milliseconds
<T:1frame@30fps*> ← each unit = 1 frame at 30fps
```

---

## Media Clips

Reference external media files with `$path` syntax:

```
$audio/song.mp3                     ← full file
$audio/song.mp3[0:05-0:12]          ← slice: from 0:05 to 0:12
$footage/scene.mp4[0:00.5-0:03.2]   ← sub-second precision
```

Paths are resolved against `~asset` declarations or relative to the `.tmd` file.

---

## Effects

Apply effects with `[effect_name:param]` syntax:

### Audio Effects

| Effect | Syntax | Description |
|--------|--------|-------------|
| Fade in | `[fade_in:2s]` | Fade in over 2 seconds |
| Fade out | `[fade_out:3s]` | Fade out over 3 seconds |
| Volume | `[volume:0.7]` | Scale volume (0.0–1.0+) |
| Speed | `[speed:1.5x]` | Playback speed (affects pitch) |
| Reverse | `[reverse]` | Play backwards |
| Pitch | `[pitch:3]` | Pitch shift in semitones |
| Echo | `[echo]` | Add echo/delay effect |

### Video Effects

| Effect | Syntax | Description |
|--------|--------|-------------|
| Cut | `[cut]` | Hard cut (default between clips) |
| Dissolve | `[dissolve:1s]` | Cross-dissolve transition |
| Crossfade | `[crossfade:0.5s]` | Audio+video crossfade |
| Zoom in | `[zoom_in:2s]` | Ken Burns zoom in |
| Zoom out | `[zoom_out:2s]` | Ken Burns zoom out |
| Color grade | `[color_grade:warm]` | Color preset (warm/cool/bw) |
| Rotate | `[rotate:90]` | Rotate N degrees |
| Speed | `[speed:0.5x]` | Slow motion / fast motion |

---

## Subtitles / Text

Use quoted strings for subtitle text. Each quoted string occupies one time unit:

```
section:字幕@|0|{
    <T:2s*>
    "第一行字幕" "第二行字幕" -- "第四个时间点"
}
```

`--` or `-` are rests (no subtitle shown during that unit).

The renderer automatically generates SRT subtitles and burns them into the video.

---

## Track Types

The track name (after `:`) determines the role:

```
section:画面@|0|{...}     ← video track
section:BGM@|0|{...}      ← background music
section:字幕@|0|{...}     ← subtitle track
section:音效@|+2|{...}    ← sound effects (starts 2 bars later)
section:vocals@|0|{...}   ← vocal track
```

Multiple tracks in the same section play simultaneously (multi-track mixing).

---

## Timing Offsets

Same as `::SCORE::`:

```
@|0|     ← start at bar 0 of this section
@|+4|    ← start 4 bars into this section
@|-1|    ← start 1 bar before this section (overlap with previous)
```

---

## Complete Remix Example

```
::REMIX::
** Lo-Fi Beats **
! = 85
<4/4>

~samples: "./samples"
~audio: "./audio"

intro:drums@|0|{
    <4*>
    $samples/kick.wav - $samples/hat.wav -
    $samples/kick.wav - $samples/hat.wav $samples/snare.wav
}

intro:pad@|+2|{
    <4*>
    [fade_in:2s] [volume:0.5]
    $audio/pad.wav[0:00-0:04]
}

verse:drums@|0|{
    <16*>
    $samples/kick.wav --- $samples/hat.wav ---
    $samples/snare.wav --- $samples/hat.wav ---
}

verse:melody@|0|{
    <4*>
    $audio/vocal_chop.wav[0:00-0:02]
    $audio/vocal_chop.wav[0:02-0:04]
}

-> intro -> verse -> verse ->#
```

---

## Complete Video Example

```
::VIDEO::
** 产品介绍 **
! = 120
<4/4>

~footage: "./footage"
~audio: "./audio"

hook:画面@|0|{
    <T:1s*>
    [fade_in:0.5s]
    $footage/hero.mp4[0:02-0:05]
    $footage/action.mp4[0:00-0:03]
}

hook:字幕@|0|{
    <T:1.5s*>
    "你准备好了吗？" -- "开始吧！" --
}

hook:BGM@|0|{
    <T:6s*>
    [volume:0.5] [fade_in:1s]
    $audio/bgm.mp3[0:00-0:06]
}

-> hook ->#
```

---

## CLI Usage

```
python tmd.py <input.tmd> [options]

Options:
  -o, --output FILE     Output file path
  -r, --resolution WxH  Video resolution (default: 1920x1080)
  --fps N               Video frame rate (default: 30)
  --dry-run             Print timeline without rendering
```

---

## Architecture

```
input.tmd
  │
  ├─ TMDScanner.py        Parse .tmd file (regex-based)
  │   ├─ MarkTypeGetter()           → SCORE / REMIX / VIDEO
  │   ├─ AssetDeclGetter()          → {alias: path}
  │   ├─ MediaTrackContentGetter()  → parsed tracks with clips/effects/text
  │   └─ (all existing getters still work)
  │
  ├─ TMDTimeline.py       Resolve to absolute time
  │   ├─ timebase_to_seconds()      → convert BPM or absolute to seconds
  │   ├─ resolve_track()            → list[TimelineEvent]
  │   └─ build_timeline()           → ordered event list + total duration
  │
  ├─ TMDMedia.py          Render via FFmpeg
  │   ├─ AudioRemixer.render()      → .wav output
  │   └─ VideoEditor.render()       → .mp4 output
  │
  └─ tmd.py               CLI orchestrator
      ├─ main_score()               → original PDF/SVG pipeline
      ├─ main_remix()               → audio remix pipeline
      └─ main_video()               → video edit pipeline
```
