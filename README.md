# TMDLang

**T**imebase **M**ark **D**own **L**anguage — a markup language for sequential, time-based events such as **band-style music scores**, **audio remixes**, and **video editing scripts**.

## Overview

TMDLang uses a Markdown-like syntax to describe events on a shared timeline.
Three file types are supported:

| Header | Purpose | Output |
|--------|---------|--------|
| `::SCORE::` | Band-style numbered music score | PDF / SVG |
| `::REMIX::` | Audio remixing / beat-synced arrangement | `.wav` / `.mp3` |
| `::VIDEO::` | Video editing / short-video assembly | `.mp4` |

## Quick Start

```bash
# Score (print parsed structure)
python src/tmd.py example/三天三夜.tmd

# Audio remix (dry run — prints timeline without rendering)
python src/tmd.py remix_demo.tmd --dry-run

# Audio remix (render)
python src/tmd.py remix_demo.tmd -o my_remix.wav

# Video edit (render)
python src/tmd.py video_edit_demo.tmd -o promo.mp4 -r 1920x1080 --fps 30
```

### Prerequisites

- **Python 3.8+**
- **Score rendering:** `cairocffi` (install via `pip install cairocffi`)
- **REMIX / VIDEO:** `ffmpeg` and `ffprobe` must be installed and on `$PATH`
- **Fonts (macOS):** Install [FreeSerif](http://ftp.gnu.org/gnu/freefont/freefont-ttf-20120503.zip) and [Hanazono](http://fonts.jp/hanazono/) to display musical symbols (🎝, 𝆒, 𝄋, 𝄌, etc.)

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

## File Structure

All three file types share the same basic structure:

```
::SCORE::                           ← file type header
** Song Title **                    ← title in double stars
! = 120                             ← BPM
? = C                               ← key (Moving Do system)
<4/4>                               ← time signature

section:instrument@|offset|{        ← part block
    <timebase*>                     ← time resolution
    content                         ← notes, chords, clips, etc.
}

-> intro -> verse -> chorus ->#     ← playback order
```

---

## Score Syntax (`::SCORE::`)

### Pitch — Moving Do System

Standard octave: `1 2 3 4 5 6 7`
Low octave: `1_ 2_ ... 7_`
High octave: `1^ 2^ ... 7^`
Sharps/flats: `1' 2' ...` (sharp), `1, 2, ...` (flat)
Rest: `0` or `-`

**Rule:** accidentals before octave marks — `1'^` (sharp high Do), never `1^'`.

### Rhythm

`<n*>` sets the base time unit where n notes fill one whole note:

```
<1*>   whole notes       <4*>  quarter notes
<2*>   half notes        <8*>  eighth notes
<16*>  sixteenth notes   <32*> thirty-second notes
```

Tuplets: `(125125)` places 6 notes in 2 beats' time.

### Chords

Chords in square brackets: `[1] [6m] [4] [5]`

### Groove / Percussion

Dynamics levels: `X x T t S s` (loud → soft)

```
<16*> XsTsx--XtXsX-x-ts
```

### Key/Tempo/Time Signature Changes

```
{?=E,}    absolute key change       {?+5}   relative (semitones)
{!=145}   absolute tempo change      {!+30}  relative
{<3/4>}   time signature change
```

Full syntax reference: [`doc/Band-Score.syntax.zh_TW.md`](doc/Band-Score.syntax.zh_TW.md)

---

## Remix Syntax (`::REMIX::`)

For audio remixing with BPM-synced arrangement.

```
::REMIX::
** Lo-Fi Beats **
! = 85
<4/4>

~samples: "./samples"               ← asset directory declaration
~audio: "./audio"

intro:drums@|0|{
    <4*>
    $samples/kick.wav - $samples/hat.wav -
}

intro:pad@|+2|{                     ← starts 2 bars in
    <4*>
    [fade_in:2s] [volume:0.5]
    $audio/pad.wav[0:00-0:04]       ← clip slice
}

-> intro -> verse ->#
```

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

---

## Video Syntax (`::VIDEO::`)

For video editing and short-video assembly.

```
::VIDEO::
** 产品介绍 **
! = 120
<4/4>

~footage: "./footage"
~audio: "./audio"

hook:画面@|0|{                      ← video track
    <T:1s*>                         ← absolute time base: 1 second per unit
    [fade_in:0.5s]
    $footage/hero.mp4[0:02-0:05]
    $footage/action.mp4[0:00-0:03]
}

hook:字幕@|0|{                      ← subtitle track
    <T:1.5s*>
    "你准备好了吗？" -- "开始吧！"
}

hook:BGM@|0|{                       ← background music track
    <T:6s*>
    [volume:0.5] [fade_in:1s]
    $audio/bgm.mp3[0:00-0:06]
}

-> hook ->#
```

### Absolute Time Bases

```
<T:0.5s*>         each unit = 0.5 seconds
<T:100ms*>        each unit = 100 milliseconds
<T:1frame@30fps*> each unit = 1 frame at 30fps
```

### Video Effects

| Effect | Syntax | Description |
|--------|--------|-------------|
| Cut | `[cut]` | Hard cut (default between clips) |
| Dissolve | `[dissolve:1s]` | Cross-dissolve transition |
| Crossfade | `[crossfade:0.5s]` | Audio+video crossfade |
| Zoom in | `[zoom_in:2s]` | Ken Burns zoom in |
| Zoom out | `[zoom_out:2s]` | Ken Burns zoom out |
| Pan | `[pan:left-to-right]` | Pan across frame |
| Wipe | `[wipe:1s]` | Wipe transition |
| Color grade | `[color_grade:warm]` | Color preset (warm/cool/bw) |
| Rotate | `[rotate:90]` | Rotate N degrees |
| Speed | `[speed:0.5x]` | Slow motion / fast motion |

### Subtitles

Quoted strings on a subtitle track auto-generate SRT and burn into the video:

```
section:字幕@|0|{
    <T:2s*>
    "第一行" "第二行" -- "第四个时间点"
}
```

---

## Media Clips

Reference external media files with `$path` syntax:

```
$audio/song.mp3                     full file
$audio/song.mp3[0:05-0:12]          slice: from 0:05 to 0:12
$footage/scene.mp4[0:00.5-0:03.2]   sub-second precision
```

Paths resolve against `~asset:` declarations or relative to the `.tmd` file.

---

## Timing Offsets

```
@|0|     start at bar 0 of this section
@|+4|    start 4 bars into this section
@|-1|    start 1 bar before this section (overlap with previous)
```

---

## Architecture

```
input.tmd
  │
  ├─ TMDScanner.py        Parse .tmd file (regex-based tokenizer)
  │   ├─ MarkTypeGetter()           → SCORE / REMIX / VIDEO
  │   ├─ AssetDeclGetter()          → {alias: path}
  │   ├─ MediaTrackContentGetter()  → parsed tracks with clips/effects/text
  │   └─ (existing SCORE getters)
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
  ├─ TMDDrawer.py         Score rendering (Cairo)
  │
  └─ tmd.py               CLI orchestrator
      ├─ main_score()               → score pipeline
      ├─ main_remix()               → audio remix pipeline
      └─ main_video()               → video edit pipeline
```

## Examples

See the [`example/`](example/) directory:
- `三天三夜.tmd` — Full band score with 7 instrument parts
- `remix_demo.tmd` — Audio remix demo
- `video_edit_demo.tmd` — Video editing demo
- `short_video_music.tmd` — Short-video with music

## License

See repository for license information.

## 概述（中文）

以類似 Markdown Language 的標記語法建立依時序進行的事件流程表格，支援三種模式：

- **樂隊形式級數樂譜** (`::SCORE::`) — 生成 PDF/SVG 簡譜
- **音訊混音** (`::REMIX::`) — 以 BPM 同步的音訊剪輯與混音
- **影片剪輯** (`::VIDEO::`) — 短視頻/影片組裝與字幕疊加

詳細語法請參閱 [`doc/Band-Score.syntax.zh_TW.md`](doc/Band-Score.syntax.zh_TW.md)（樂譜）及 [`doc/Media-Syntax.md`](doc/Media-Syntax.md)（音訊/影片）。
