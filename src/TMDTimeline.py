"""TMDTimeline - Resolves parsed TMD structures into absolute-time event lists.

Converts BPM-relative or absolute time bases into seconds, then flattens the
section order (-> A -> B ->#) into a single timeline of timed events that
TMDMedia can execute.
"""

import re
from fractions import Fraction as frac


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

def parse_timestamp(ts):
    """Parse a timestamp string like '00:05.0' or '1:23:45.5' into seconds."""
    if ts is None:
        return None
    parts = ts.replace(',', '.').split(':')
    parts = [float(p) for p in parts]
    if len(parts) == 1:
        return parts[0]
    elif len(parts) == 2:
        return parts[0] * 60 + parts[1]
    else:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]


def timebase_to_seconds(timebase, tempo=120.0):
    """Return the duration in seconds of one time-unit given a timebase dict.

    timebase dict formats:
      {'mode': 'bpm', 'note_div': 4}          → quarter note at *tempo* BPM
      {'mode': 'absolute', 'value': 0.5, 'unit': 's', ...}
      {'mode': 'absolute', 'value': 1, 'unit': 'frame', 'fps': 30}
    """
    if timebase is None:
        # Default to quarter notes
        whole_note_sec = 4 * 60.0 / tempo
        return whole_note_sec / 4

    if timebase['mode'] == 'bpm':
        whole_note_sec = 4 * 60.0 / tempo  # 4 beats at *tempo* BPM
        return whole_note_sec / timebase['note_div']

    # Absolute mode
    val = timebase['value']
    unit = timebase['unit']
    if unit == 's':
        return val
    elif unit == 'ms':
        return val / 1000.0
    elif unit == 'frame':
        fps = timebase.get('fps') or 30
        return val / fps
    return val


def timing_offset_to_bars(timing_str):
    """Parse a timing string like '|+4|' or '|-1|' into a bar offset integer."""
    if not timing_str:
        return 0
    m = re.search(r'\|([+-]?\d+)\|', timing_str)
    if m:
        return int(m.group(1))
    return 0


# ---------------------------------------------------------------------------
# Timeline event types
# ---------------------------------------------------------------------------

class TimelineEvent:
    """A single event on the absolute timeline."""

    __slots__ = ('start', 'duration', 'track', 'event_type', 'data')

    def __init__(self, start, duration, track, event_type, data=None):
        self.start = start          # seconds from timeline origin
        self.duration = duration    # seconds
        self.track = track          # track name (e.g. "BGM", "画面", "字幕")
        self.event_type = event_type  # 'clip', 'effect', 'text', 'rest', 'note'
        self.data = data or {}      # type-specific payload

    def end(self):
        return self.start + self.duration

    def __repr__(self):
        return (f"<Event {self.event_type} track={self.track} "
                f"@{self.start:.3f}s +{self.duration:.3f}s data={self.data}>")


# ---------------------------------------------------------------------------
# Resolve a single track (part block) into events
# ---------------------------------------------------------------------------

def resolve_track(track_dict, tempo, section_start_sec=0.0, signature=(4, 4)):
    """Convert one parsed media track dict into a list of TimelineEvents.

    *track_dict* is one element returned by TMDScanner.MediaTrackContentGetter.
    """
    events = []
    tb = track_dict.get('timebase')
    unit_sec = timebase_to_seconds(tb, tempo)

    track_name = track_dict['InstrumentName']
    bar_offset = timing_offset_to_bars(track_dict.get('Timing', ''))
    beats_per_bar = signature[0]
    beat_note_val = signature[1]
    # Bar duration in seconds
    bar_sec = (beats_per_bar / beat_note_val) * (4 * 60.0 / tempo)
    offset_sec = section_start_sec + bar_offset * bar_sec

    cursor = offset_sec  # current time position in seconds

    # --- Handle media clips ---
    clips = track_dict.get('clips', [])
    effects = track_dict.get('effects', [])
    texts = track_dict.get('texts', [])
    tokens = track_dict.get('tokens', [])

    clip_idx = 0
    effect_idx = 0
    text_idx = 0

    for token in tokens:
        # Check if this token is a media clip placeholder
        if token.startswith('$'):
            if clip_idx < len(clips):
                clip = clips[clip_idx]
                clip_in = parse_timestamp(clip.get('in'))
                clip_out = parse_timestamp(clip.get('out'))
                clip_dur = None
                if clip_in is not None and clip_out is not None:
                    clip_dur = clip_out - clip_in
                if clip_dur is None:
                    clip_dur = unit_sec  # default to one time unit
                events.append(TimelineEvent(
                    start=cursor, duration=clip_dur, track=track_name,
                    event_type='clip',
                    data={'path': clip['path'], 'in': clip_in, 'out': clip_out}
                ))
                cursor += clip_dur
                clip_idx += 1
            else:
                cursor += unit_sec

        elif token.startswith('[') and token.endswith(']'):
            # Effect or chord — check if it's a known effect
            inner = token[1:-1]
            if effect_idx < len(effects) and effects[effect_idx]['name'] in inner:
                eff = effects[effect_idx]
                events.append(TimelineEvent(
                    start=cursor, duration=0, track=track_name,
                    event_type='effect',
                    data={'name': eff['name'], 'param': eff['param']}
                ))
                effect_idx += 1
            # Effects don't consume time by default
            # (they modify neighbouring clips)

        elif token.startswith('"') and token.endswith('"'):
            txt = token.strip('"')
            if not txt and text_idx < len(texts):
                txt = texts[text_idx]
                text_idx += 1
            events.append(TimelineEvent(
                start=cursor, duration=unit_sec, track=track_name,
                event_type='text',
                data={'text': txt}
            ))
            cursor += unit_sec

        elif token == '-' or token == '--' or all(c == '-' for c in token):
            # Rest / sustain — advance cursor
            dash_count = len(token)
            cursor += unit_sec * dash_count

        else:
            # Generic token (note, visual tag, etc.)
            events.append(TimelineEvent(
                start=cursor, duration=unit_sec, track=track_name,
                event_type='note',
                data={'token': token}
            ))
            cursor += unit_sec

    # If there are clips that weren't matched to tokens, append them
    # sequentially (simple concatenation mode)
    if clip_idx == 0 and clips:
        for clip in clips:
            clip_in = parse_timestamp(clip.get('in'))
            clip_out = parse_timestamp(clip.get('out'))
            clip_dur = None
            if clip_in is not None and clip_out is not None:
                clip_dur = clip_out - clip_in
            if clip_dur is None:
                clip_dur = unit_sec
            events.append(TimelineEvent(
                start=cursor, duration=clip_dur, track=track_name,
                event_type='clip',
                data={'path': clip['path'], 'in': clip_in, 'out': clip_out}
            ))
            cursor += clip_dur

    # Apply section-level effects (not attached to specific tokens)
    for eff in effects[effect_idx:]:
        events.append(TimelineEvent(
            start=offset_sec, duration=cursor - offset_sec, track=track_name,
            event_type='effect',
            data={'name': eff['name'], 'param': eff['param']}
        ))

    return events, cursor  # events + end-of-track time


# ---------------------------------------------------------------------------
# Build full timeline from all sections and order
# ---------------------------------------------------------------------------

def build_timeline(media_tracks, order_list, tempo, signature=(4, 4)):
    """Build an absolute-time event list from parsed media tracks and order.

    Parameters
    ----------
    media_tracks : list[dict]
        Output of TMDScanner.MediaTrackContentGetter.
    order_list : list[str]
        Output of TMDScanner.PartSequenceGetter (e.g. ['intro','A','B']).
    tempo : float
        BPM.
    signature : tuple
        (beats_per_bar, beat_note_value).

    Returns
    -------
    list[TimelineEvent]
        Sorted by start time.
    float
        Total timeline duration in seconds.
    """
    # Group tracks by section name
    sections = {}
    for t in media_tracks:
        name = t['partname']
        sections.setdefault(name, []).append(t)

    all_events = []
    cursor = 0.0  # global timeline position

    for section_name in order_list:
        if not section_name:
            continue
        tracks = sections.get(section_name, [])
        section_end = cursor
        for track in tracks:
            evts, track_end = resolve_track(
                track, tempo, section_start_sec=cursor, signature=signature)
            all_events.extend(evts)
            section_end = max(section_end, track_end)
        cursor = section_end

    all_events.sort(key=lambda e: (e.start, e.track))
    return all_events, cursor


# ---------------------------------------------------------------------------
# Convenience: group events by track
# ---------------------------------------------------------------------------

def events_by_track(events):
    """Group a flat event list by track name."""
    groups = {}
    for e in events:
        groups.setdefault(e.track, []).append(e)
    return groups
