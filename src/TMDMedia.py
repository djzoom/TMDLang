"""TMDMedia - Audio remix & video editing engine for TMDLang.

Translates a resolved timeline (from TMDTimeline) into FFmpeg commands
that produce the final audio or video output.

Two primary workflows:
  1. Audio Remix  (::REMIX::) — slice, concatenate, crossfade, pitch-shift,
     and mix multiple audio sources on a BPM-synchronised timeline.
  2. Video Edit   (::VIDEO::) — cut, arrange, overlay subtitles, apply
     transitions, and mix video clips on an absolute-time timeline.

Dependencies: ffmpeg / ffprobe must be on $PATH.
"""

import json
import os
import shlex
import subprocess
import tempfile

from TMDTimeline import TimelineEvent, events_by_track, parse_timestamp


# ---------------------------------------------------------------------------
# FFmpeg helpers
# ---------------------------------------------------------------------------

def _run(cmd, check=True):
    """Run a shell command, return CompletedProcess."""
    print(f"  [ffmpeg] {cmd}")
    return subprocess.run(cmd, shell=True, check=check,
                          capture_output=True, text=True)


def probe_duration(path):
    """Get duration in seconds of a media file via ffprobe."""
    cmd = (f'ffprobe -v error -show_entries format=duration '
           f'-of json {shlex.quote(path)}')
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode != 0:
        return None
    info = json.loads(r.stdout)
    return float(info['format']['duration'])


def _resolve_asset_path(clip_path, assets):
    """Resolve a clip path like 'audio/song.mp3' using asset declarations."""
    if os.path.exists(clip_path):
        return clip_path
    # Try prepending declared asset directories
    for alias, base in assets.items():
        if clip_path.startswith(alias + '/'):
            relative = clip_path[len(alias) + 1:]
            candidate = os.path.join(base, relative)
            if os.path.exists(candidate):
                return candidate
        # Also try raw join
        candidate = os.path.join(base, clip_path)
        if os.path.exists(candidate):
            return candidate
    return clip_path  # return as-is; ffmpeg will error if missing


# ---------------------------------------------------------------------------
# Audio remix
# ---------------------------------------------------------------------------

class AudioRemixer:
    """Renders a ::REMIX:: timeline into a single mixed-down audio file."""

    def __init__(self, events, assets=None, output='remix_output.wav'):
        self.events = events
        self.assets = assets or {}
        self.output = output
        self._tmpdir = tempfile.mkdtemp(prefix='tmd_remix_')
        self._tmp_counter = 0

    def _tmpfile(self, ext='wav'):
        self._tmp_counter += 1
        return os.path.join(self._tmpdir, f'tmp_{self._tmp_counter}.{ext}')

    # -- Step 1: extract individual clips -----------------------------------

    def _extract_clip(self, event):
        """Extract a single audio clip from source, return path to temp wav."""
        src = _resolve_asset_path(event.data['path'], self.assets)
        out = self._tmpfile()
        seek = ''
        duration = ''
        if event.data.get('in') is not None:
            seek = f'-ss {event.data["in"]}'
        if event.data.get('out') is not None and event.data.get('in') is not None:
            dur = event.data['out'] - event.data['in']
            duration = f'-t {dur}'
        elif event.duration:
            duration = f'-t {event.duration}'
        cmd = f'ffmpeg -y {seek} -i {shlex.quote(src)} {duration} -ar 44100 -ac 2 {shlex.quote(out)}'
        _run(cmd)
        return out

    # -- Step 2: apply per-clip effects -------------------------------------

    def _apply_effects(self, clip_path, effects):
        """Apply audio effects to a clip file. Returns new path."""
        if not effects:
            return clip_path
        filters = []
        for eff in effects:
            name = eff.data['name']
            param = eff.data.get('param', '')
            if name == 'fade_in':
                dur = float(param.rstrip('s')) if param else 1.0
                filters.append(f'afade=t=in:d={dur}')
            elif name == 'fade_out':
                dur = float(param.rstrip('s')) if param else 1.0
                filters.append(f'afade=t=out:d={dur}')
            elif name == 'volume':
                filters.append(f'volume={param}')
            elif name == 'speed':
                rate = float(param.rstrip('x')) if param else 1.0
                filters.append(f'atempo={rate}')
            elif name == 'reverse':
                filters.append('areverse')
            elif name == 'pitch':
                # Pitch shift in semitones using rubberband
                semitones = float(param) if param else 0
                freq_ratio = 2 ** (semitones / 12.0)
                filters.append(f'asetrate=44100*{freq_ratio},aresample=44100')
            elif name == 'echo':
                filters.append('aecho=0.8:0.88:60:0.4')
        if not filters:
            return clip_path
        out = self._tmpfile()
        af = ','.join(filters)
        cmd = f'ffmpeg -y -i {shlex.quote(clip_path)} -af {shlex.quote(af)} {shlex.quote(out)}'
        _run(cmd)
        return out

    # -- Step 3: mix all tracks down ----------------------------------------

    def render(self):
        """Render the full remix to self.output."""
        grouped = events_by_track(self.events)
        track_files = []

        for track_name, track_events in grouped.items():
            clips_on_track = [e for e in track_events if e.event_type == 'clip']
            effects_on_track = [e for e in track_events if e.event_type == 'effect']
            if not clips_on_track:
                continue

            # Build per-track audio by placing clips at their start times
            # Find track extent
            track_start = min(e.start for e in clips_on_track)
            track_end = max(e.end() for e in clips_on_track)
            track_dur = track_end - track_start

            # Create a silent base
            base = self._tmpfile()
            cmd = (f'ffmpeg -y -f lavfi -i anullsrc=r=44100:cl=stereo '
                   f'-t {track_dur} {shlex.quote(base)}')
            _run(cmd)

            # Overlay each clip at the correct time
            current = base
            for clip_evt in clips_on_track:
                extracted = self._extract_clip(clip_evt)
                # Apply per-clip effects (effects whose start falls within clip range)
                clip_effects = [e for e in effects_on_track
                                if clip_evt.start <= e.start < clip_evt.end()]
                extracted = self._apply_effects(extracted, clip_effects)

                delay_ms = int((clip_evt.start - track_start) * 1000)
                out = self._tmpfile()
                # amerge with delay
                cmd = (f'ffmpeg -y -i {shlex.quote(current)} -i {shlex.quote(extracted)} '
                       f'-filter_complex '
                       f'"[1]adelay={delay_ms}|{delay_ms}[delayed];'
                       f'[0][delayed]amix=inputs=2:duration=longest" '
                       f'{shlex.quote(out)}')
                _run(cmd)
                current = out

            # Apply track-level effects (effects not tied to a specific clip)
            track_level_effects = [e for e in effects_on_track
                                   if not any(c.start <= e.start < c.end()
                                              for c in clips_on_track)]
            current = self._apply_effects(current, track_level_effects)
            track_files.append((current, track_start))

        if not track_files:
            print("No audio clips to render.")
            return

        # Mix all tracks together
        if len(track_files) == 1:
            _run(f'cp {shlex.quote(track_files[0][0])} {shlex.quote(self.output)}')
        else:
            # Use amix with delays for multi-track mixdown
            inputs = ''
            filter_parts = []
            for idx, (path, start) in enumerate(track_files):
                inputs += f' -i {shlex.quote(path)}'
                delay_ms = int(start * 1000)
                filter_parts.append(f'[{idx}]adelay={delay_ms}|{delay_ms}[t{idx}]')
            mix_inputs = ''.join(f'[t{i}]' for i in range(len(track_files)))
            filter_parts.append(
                f'{mix_inputs}amix=inputs={len(track_files)}:duration=longest')
            fc = ';'.join(filter_parts)
            cmd = f'ffmpeg -y{inputs} -filter_complex "{fc}" {shlex.quote(self.output)}'
            _run(cmd)

        print(f"\n  Audio remix rendered -> {self.output}")
        return self.output


# ---------------------------------------------------------------------------
# Video editor
# ---------------------------------------------------------------------------

class VideoEditor:
    """Renders a ::VIDEO:: timeline into a single video file."""

    def __init__(self, events, assets=None, output='video_output.mp4',
                 resolution='1920x1080', fps=30):
        self.events = events
        self.assets = assets or {}
        self.output = output
        self.resolution = resolution
        self.fps = fps
        self._tmpdir = tempfile.mkdtemp(prefix='tmd_video_')
        self._tmp_counter = 0

    def _tmpfile(self, ext='mp4'):
        self._tmp_counter += 1
        return os.path.join(self._tmpdir, f'tmp_{self._tmp_counter}.{ext}')

    def _extract_video_clip(self, event):
        """Extract a video clip segment."""
        src = _resolve_asset_path(event.data['path'], self.assets)
        out = self._tmpfile()
        seek = ''
        duration = ''
        if event.data.get('in') is not None:
            seek = f'-ss {event.data["in"]}'
        if event.data.get('out') is not None and event.data.get('in') is not None:
            dur = event.data['out'] - event.data['in']
            duration = f'-t {dur}'
        elif event.duration:
            duration = f'-t {event.duration}'
        cmd = (f'ffmpeg -y {seek} -i {shlex.quote(src)} {duration} '
               f'-vf scale={self.resolution}:force_original_aspect_ratio=decrease,'
               f'pad={self.resolution}:(ow-iw)/2:(oh-ih)/2 '
               f'-r {self.fps} -c:v libx264 -preset fast -c:a aac '
               f'{shlex.quote(out)}')
        _run(cmd)
        return out

    def _apply_video_effect(self, clip_path, effect):
        """Apply a single video effect, return new clip path."""
        name = effect.data['name']
        param = effect.data.get('param', '')
        out = self._tmpfile()

        if name == 'fade_in':
            dur = float(param.rstrip('s')) if param else 1.0
            vf = f'fade=t=in:d={dur}'
            af = f'afade=t=in:d={dur}'
            cmd = (f'ffmpeg -y -i {shlex.quote(clip_path)} '
                   f'-vf {shlex.quote(vf)} -af {shlex.quote(af)} '
                   f'-c:v libx264 -preset fast {shlex.quote(out)}')
        elif name == 'fade_out':
            dur = float(param.rstrip('s')) if param else 1.0
            vf = f'fade=t=out:d={dur}'
            af = f'afade=t=out:d={dur}'
            cmd = (f'ffmpeg -y -i {shlex.quote(clip_path)} '
                   f'-vf {shlex.quote(vf)} -af {shlex.quote(af)} '
                   f'-c:v libx264 -preset fast {shlex.quote(out)}')
        elif name == 'speed':
            rate = float(param.rstrip('x')) if param else 1.0
            # Video PTS and audio tempo
            vf = f'setpts={1/rate}*PTS'
            af = f'atempo={rate}'
            cmd = (f'ffmpeg -y -i {shlex.quote(clip_path)} '
                   f'-vf {shlex.quote(vf)} -af {shlex.quote(af)} '
                   f'-c:v libx264 -preset fast {shlex.quote(out)}')
        elif name == 'reverse':
            cmd = (f'ffmpeg -y -i {shlex.quote(clip_path)} '
                   f'-vf reverse -af areverse '
                   f'-c:v libx264 -preset fast {shlex.quote(out)}')
        elif name == 'zoom_in':
            dur = float(param.rstrip('s')) if param else 2.0
            vf = (f"zoompan=z='min(zoom+0.001,1.5)':d={int(dur*self.fps)}"
                  f":s={self.resolution}")
            cmd = (f'ffmpeg -y -i {shlex.quote(clip_path)} '
                   f'-vf {shlex.quote(vf)} '
                   f'-c:v libx264 -preset fast {shlex.quote(out)}')
        elif name == 'zoom_out':
            dur = float(param.rstrip('s')) if param else 2.0
            vf = (f"zoompan=z='if(eq(on,1),1.5,max(zoom-0.001,1))':d={int(dur*self.fps)}"
                  f":s={self.resolution}")
            cmd = (f'ffmpeg -y -i {shlex.quote(clip_path)} '
                   f'-vf {shlex.quote(vf)} '
                   f'-c:v libx264 -preset fast {shlex.quote(out)}')
        elif name == 'color_grade':
            # Simple color grading presets
            if param == 'warm':
                vf = 'colorbalance=rs=0.1:gs=0:bs=-0.1'
            elif param == 'cool':
                vf = 'colorbalance=rs=-0.1:gs=0:bs=0.1'
            elif param == 'bw':
                vf = 'hue=s=0'
            else:
                vf = f'eq=brightness=0.06:contrast=1.1:saturation=1.2'
            cmd = (f'ffmpeg -y -i {shlex.quote(clip_path)} '
                   f'-vf {shlex.quote(vf)} '
                   f'-c:v libx264 -preset fast -c:a copy {shlex.quote(out)}')
        elif name == 'volume':
            vol = param if param else '1.0'
            cmd = (f'ffmpeg -y -i {shlex.quote(clip_path)} '
                   f'-af volume={vol} -c:v copy {shlex.quote(out)}')
        elif name == 'rotate':
            deg = param if param else '90'
            vf = f'rotate={deg}*PI/180'
            cmd = (f'ffmpeg -y -i {shlex.quote(clip_path)} '
                   f'-vf {shlex.quote(vf)} '
                   f'-c:v libx264 -preset fast -c:a copy {shlex.quote(out)}')
        else:
            return clip_path

        _run(cmd)
        return out

    def _generate_subtitle_srt(self, text_events):
        """Generate an SRT file from text events."""
        srt_path = self._tmpfile('srt')
        lines = []
        for idx, evt in enumerate(text_events, 1):
            start = evt.start
            end = evt.end()
            lines.append(str(idx))
            lines.append(f'{_fmt_srt_time(start)} --> {_fmt_srt_time(end)}')
            lines.append(evt.data.get('text', ''))
            lines.append('')
        with open(srt_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        return srt_path

    def render(self):
        """Render the full video to self.output."""
        grouped = events_by_track(self.events)

        # Separate video clips, audio tracks, text/subtitle tracks
        video_clips = []    # (path, start_time)
        audio_tracks = []
        subtitle_events = []

        for track_name, track_events in grouped.items():
            clips = [e for e in track_events if e.event_type == 'clip']
            effects = [e for e in track_events if e.event_type == 'effect']
            texts = [e for e in track_events if e.event_type == 'text']

            if texts:
                subtitle_events.extend(texts)

            for clip_evt in clips:
                path = clip_evt.data.get('path', '')
                # Determine if it's audio-only or video
                is_audio = path.lower().endswith(('.mp3', '.wav', '.flac',
                                                  '.aac', '.ogg', '.m4a'))
                if is_audio:
                    extracted = self._extract_audio_clip(clip_evt)
                    audio_tracks.append((extracted, clip_evt.start))
                else:
                    extracted = self._extract_video_clip(clip_evt)
                    # Apply effects
                    clip_effects = [e for e in effects
                                    if clip_evt.start <= e.start < clip_evt.end()]
                    for eff in clip_effects:
                        extracted = self._apply_video_effect(extracted, eff)
                    video_clips.append((extracted, clip_evt.start))

        if not video_clips:
            print("No video clips to render.")
            return

        # -- Concatenate video clips (sorted by start time) --
        video_clips.sort(key=lambda x: x[1])
        concat_list = self._tmpfile('txt')
        with open(concat_list, 'w') as f:
            for path, _ in video_clips:
                f.write(f"file {shlex.quote(path)}\n")

        concat_out = self._tmpfile()
        cmd = (f'ffmpeg -y -f concat -safe 0 -i {shlex.quote(concat_list)} '
               f'-c:v libx264 -preset fast -c:a aac {shlex.quote(concat_out)}')
        _run(cmd)

        final = concat_out

        # -- Overlay subtitles if any --
        if subtitle_events:
            subtitle_events.sort(key=lambda e: e.start)
            srt = self._generate_subtitle_srt(subtitle_events)
            sub_out = self._tmpfile()
            cmd = (f'ffmpeg -y -i {shlex.quote(final)} '
                   f'-vf subtitles={shlex.quote(srt)} '
                   f'-c:v libx264 -preset fast -c:a copy {shlex.quote(sub_out)}')
            _run(cmd)
            final = sub_out

        # -- Mix in audio tracks if any --
        if audio_tracks:
            for audio_path, audio_start in audio_tracks:
                mixed = self._tmpfile()
                delay_ms = int(audio_start * 1000)
                cmd = (f'ffmpeg -y -i {shlex.quote(final)} -i {shlex.quote(audio_path)} '
                       f'-filter_complex '
                       f'"[1]adelay={delay_ms}|{delay_ms}[aud];'
                       f'[0:a][aud]amix=inputs=2:duration=longest" '
                       f'-c:v copy {shlex.quote(mixed)}')
                _run(cmd)
                final = mixed

        # Copy to output
        _run(f'cp {shlex.quote(final)} {shlex.quote(self.output)}')
        print(f"\n  Video rendered -> {self.output}")
        return self.output

    def _extract_audio_clip(self, event):
        """Extract an audio clip from source."""
        src = _resolve_asset_path(event.data['path'], self.assets)
        out = self._tmpfile('wav')
        seek = ''
        duration = ''
        if event.data.get('in') is not None:
            seek = f'-ss {event.data["in"]}'
        if event.data.get('out') is not None and event.data.get('in') is not None:
            dur = event.data['out'] - event.data['in']
            duration = f'-t {dur}'
        elif event.duration:
            duration = f'-t {event.duration}'
        cmd = (f'ffmpeg -y {seek} -i {shlex.quote(src)} {duration} '
               f'-ar 44100 -ac 2 {shlex.quote(out)}')
        _run(cmd)
        return out


# ---------------------------------------------------------------------------
# SRT time formatting
# ---------------------------------------------------------------------------

def _fmt_srt_time(seconds):
    """Format seconds as HH:MM:SS,mmm for SRT."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f'{h:02d}:{m:02d}:{s:02d},{ms:03d}'


# ---------------------------------------------------------------------------
# Convenience: generate crossfade concat
# ---------------------------------------------------------------------------

def crossfade_concat(clip_paths, crossfade_dur=0.5, output='crossfaded.mp4'):
    """Concatenate video clips with crossfade transitions between each pair."""
    if len(clip_paths) < 2:
        if clip_paths:
            _run(f'cp {shlex.quote(clip_paths[0])} {shlex.quote(output)}')
        return output

    current = clip_paths[0]
    for i in range(1, len(clip_paths)):
        out = output if i == len(clip_paths) - 1 else tempfile.mktemp(suffix='.mp4')
        cmd = (f'ffmpeg -y -i {shlex.quote(current)} -i {shlex.quote(clip_paths[i])} '
               f'-filter_complex '
               f'"xfade=transition=fade:duration={crossfade_dur}:offset='
               f'$(ffprobe -v error -show_entries format=duration -of csv=p=0 '
               f'{shlex.quote(current)}|head -1|'
               f'awk \'{{printf "%.2f", $1-{crossfade_dur}}}\')" '
               f'-c:v libx264 -preset fast {shlex.quote(out)}')
        _run(cmd)
        current = out
    return output
