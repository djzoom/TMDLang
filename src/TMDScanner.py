import re
from sys import exit
from fractions import Fraction as frac

PartSequencePattern = re.compile(r"\-\>([^\#]+)->\#")
PartContentPattern = re.compile(
    r"(?P<partname>\S*)?:(?P<InstrumentName>\S*)@(?P<Timing>[^\{]*)\{(?P<PartContent>[^}]+)\}")
SongNamePattern = re.compile(r"\s*\*\*\s+?(?P<SongName>[^\*]+)\s+?\*\*\s*")
TempoPattern = re.compile(r"\s*?\!\s*?\=\s*?(\d\d\d?\.?\d?\d?)\s*?\n")
KeyPattern = re.compile(r"\s*?\?\s*\=\s*(?P<Key>[ABCDEFGabcdefg][',]?m?)\s*?\n")
PerChordPattern = re.compile(
    r"\[(?P<Root>[1-7])(?P<RootAccidental>['|,])?(?P<Tonic>maj|Maj|aug|dim|m|M)?(?P<Ext>(?:sus|alt))?(?P<TensionNote>[^\]\/]*)?[\/]?(?P<Bass>[1-7])?(?P<BassAccidental>['|,])?\]")

SignaturePattern = re.compile(
    r"\<(?P<BeatsPerBar>\d\d?)\/(?P<TickBase>\d\d?)\>\s*[\n\r]")

# --- Media patterns (::REMIX:: and ::VIDEO::) ---

MarkupTypePattern = re.compile(r"^\:\:(?P<MarkType>\S+)\:\:\s*?$", re.MULTILINE)

# Asset declarations:  ~assets: "./footage/"  or  ~audio: "./audio/"
AssetDeclPattern = re.compile(
    r"~(?P<AssetName>\w+)\s*:\s*\"(?P<AssetPath>[^\"]+)\"")

# Media clip reference:  $audio/song.mp3[00:05.0-00:12.0]  or  $video/clip.mp4
MediaClipPattern = re.compile(
    r"\$(?P<ClipPath>[^\[\s\]]+)"
    r"(?:\[(?P<ClipIn>[\d:.]+)?-(?P<ClipOut>[\d:.]+)?\])?"
)

# Absolute time base:  <T:0.5s*>  or  <T:frame@30fps*>
AbsTimeBasePattern = re.compile(
    r"<T:(?P<TimeVal>[\d.]+)(?P<TimeUnit>s|ms|frame)(?:@(?P<FPS>\d+)fps)?(?:\*?)>"
)

# BPM-based time base (existing):  <4*>  <16*>
BpmTimeBasePattern = re.compile(r"<(?P<NoteDiv>[1248]|16|32)\*>")

# Effect directive:  [fade_in:1s]  [crossfade:0.5s]  [volume:0.8]
EffectPattern = re.compile(
    r"\[(?P<EffectName>fade_in|fade_out|crossfade|volume|speed|reverse|pitch|echo|"
    r"cut|dissolve|wipe|zoom_in|zoom_out|pan|rotate|text|color_grade)"
    r"(?::(?P<EffectParam>[^\]]*))?\]"
)

# Quoted text (for subtitles/titles):  "some text"
QuotedTextPattern = re.compile(r'"(?P<Text>[^"]*)"')

# Triple-quoted block (for visual descriptions):  """ ... """
TripleQuotePattern = re.compile(r'"""(?P<Block>[^"]*(?:"(?!""")[^"]*)*?)"""', re.DOTALL)

# Visual instruction tag:  [特写]  [切]  [推镜]  etc. (inside triple-quote blocks)
VisualTagPattern = re.compile(r"\[(?P<Tag>[^\]\[]+)\]")


def MarkTypeGetter(inputFile):
    """Get the markup type from the file header (SCORE, REMIX, VIDEO)."""
    m = MarkupTypePattern.search(inputFile)
    if m:
        return m.group('MarkType')
    return None


def AssetDeclGetter(inputFile):
    """Extract all asset path declarations."""
    return {m.group('AssetName'): m.group('AssetPath')
            for m in AssetDeclPattern.finditer(inputFile)}


def MediaTrackContentGetter(inputFile):
    """Extract part blocks with media-aware content parsing.

    Returns a list of dicts, each containing:
      - partname, InstrumentName (track type), Timing
      - clips: list of media clip references
      - effects: list of effect directives
      - texts: list of quoted text (subtitles)
      - descriptions: list of triple-quoted visual descriptions
      - raw: the raw content string
    """
    parts = [m.groupdict() for m in re.finditer(PartContentPattern, inputFile)]
    result = []
    for p in parts:
        raw = p['PartContent']
        # Parse time base
        abs_tb = AbsTimeBasePattern.search(raw)
        bpm_tb = BpmTimeBasePattern.search(raw)
        timebase = None
        if abs_tb:
            d = abs_tb.groupdict()
            timebase = {'mode': 'absolute', 'value': float(d['TimeVal']),
                        'unit': d['TimeUnit'], 'fps': int(d['FPS']) if d['FPS'] else None}
        elif bpm_tb:
            timebase = {'mode': 'bpm', 'note_div': int(bpm_tb.group('NoteDiv'))}

        # Parse media clips
        clips = []
        for cm in MediaClipPattern.finditer(raw):
            clips.append({
                'path': cm.group('ClipPath'),
                'in': cm.group('ClipIn'),
                'out': cm.group('ClipOut'),
            })

        # Parse effects
        effects = []
        for em in EffectPattern.finditer(raw):
            effects.append({
                'name': em.group('EffectName'),
                'param': em.group('EffectParam'),
            })

        # Parse subtitle texts
        texts = [tm.group('Text') for tm in QuotedTextPattern.finditer(raw)]

        # Parse visual description blocks
        descriptions = [dm.group('Block').strip()
                        for dm in TripleQuotePattern.finditer(raw)]

        # Strip content for rest/dash counting (timing grid)
        stripped = raw
        # Remove time base tags
        stripped = AbsTimeBasePattern.sub('', stripped)
        stripped = BpmTimeBasePattern.sub('', stripped)
        # Remove triple-quoted blocks
        stripped = TripleQuotePattern.sub('', stripped)
        # Remove comments
        stripped = re.sub(r'/\*[^*]*\*/', '', stripped)
        # Tokenize: each non-whitespace token is one time unit
        tokens = stripped.split()

        result.append({
            'partname': p['partname'],
            'InstrumentName': p['InstrumentName'],
            'Timing': p['Timing'],
            'timebase': timebase,
            'clips': clips,
            'effects': effects,
            'texts': texts,
            'descriptions': descriptions,
            'tokens': tokens,
            'raw': raw,
        })
    return result


def TempoGetter(inputFile):
    if len(re.findall(TempoPattern, inputFile)) != 1:
        return 120
    else:
        return re.findall(TempoPattern, inputFile)[0]


def KeyGetter(inputFile):
    if len(re.findall(KeyPattern, inputFile)) != 1:
        return ''
    else:
        return re.findall(KeyPattern, inputFile)[0]


def SongNameGetter(inputFile):
    if len(re.findall(SongNamePattern, inputFile)) != 1:
        return ''
    else:
        return re.findall(SongNamePattern, inputFile)[0]


def PartContentGetter(inputFile):
    LL = [m.groupdict() for m in re.finditer(PartContentPattern, inputFile)]

    for i in LL:
        i['PartContent'] = re.sub(r"\/\*[^\*]+\*\/", '', i['PartContent'].replace(
            ' ', '').replace('\n', '').replace('|', '').replace('\t', '').replace('\r', ''))

    return LL


def PartsContainsChord(PRTCNT):
    L = []
    for p in PRTCNT:
        if p['InstrumentName'] == 'CHORD':
            if p['Timing'] != '' and p['Timing'] != '|0|':
                print('any CHORD part should started with |0| or none!')
                exit('syntax error')
            else:
                L.append(p)
    return L


def PartSetGetter(PartContentDict):
    SetOfPartname = set()
    for i in PartContentDict:
        SetOfPartname.add(i['partname'])
    return SetOfPartname


def InstrumentSetGetter(PartContentList):
    SetOfInstument = set()
    for i in PartContentList:
        SetOfInstument.add(i['InstrumentName'])
    return SetOfInstument


def PartSequenceGetter(inputFile):
    if len(re.findall(PartSequencePattern, inputFile)) == 1:
        TempList = re.findall(PartSequencePattern, inputFile)[0].split('->')
        return [re.sub(r"\/\*[^\*]+\*\/", '', item.replace(
            ' ', '').replace('\n', '').replace('|', '').replace('\t', '').replace('\r', '')) for item in TempList]
    else:
        return []


def SignatureGetter(inputFile):
    Sig = re.findall(SignaturePattern, inputFile)
    if len(Sig) == 0:
        return (4, 4)

    elif Sig[0][1] not in {'1', '2', '4', '8', '16', '32'}:
        print('signature should base on 1, 2, 4, 8, 16, 32.')
        exit('invalid signature')

    else:
        return (int(Sig[0][0]), int(Sig[0][1]))


def ChordListGetter(PartsContainsChord):
    XX = []
    re4Content = re.compile(
        r"(?P<TimeBase>\<[1|2|4|8|16|32]\*\>)(?P<ChordString>[^<$]+)")
    re4ChordLengh = re.compile(r"(?P<FullChord>\[[^\]]+\])(?P<dash>\-*)")
    for i in PartsContainsChord:
        TT = {i['partname']: []}
        for j in re4Content.findall(i['PartContent']):
            for k in re4ChordLengh.findall(j[1]):
                TT[i['partname']].append((k[0], j[0], len(k[1]) + 1))
        XX.append(TT)
    return XX


def PerChordSymbolAndPosition(PCTX, SIGTRE):
    Y = []
    for ChordsInEveryPart in ChordListGetter(PartsContainsChord(PCTX)):
        X = []
        for DictItemWhichKeyIsPartName in ChordsInEveryPart:
            ListOfChordWithEveryPartContent = []
            for i in ChordsInEveryPart[DictItemWhichKeyIsPartName]:
                ListOfChordWithEveryPartContent.append(
                    (i[0], 1 / int(i[1].rstrip('*>').lstrip('<')), i[2]))
            SpaceBeforeChord = 0
            WholePartLength = 0
            for i in range(len(ListOfChordWithEveryPartContent)):
                WholePartLength += ListOfChordWithEveryPartContent[i][1] * \
                    ListOfChordWithEveryPartContent[i][2] * \
                    frac(str(SIGTRE[1]) + '/' + str(SIGTRE[0]))
                if i == 0:
                    X.append((0.0, [m.groupdict() for m in re.finditer(
                        PerChordPattern, ListOfChordWithEveryPartContent[i][0])][0]))
                else:
                    SpaceBeforeChord += frac(ListOfChordWithEveryPartContent[i - 1][1]) * \
                        frac(ListOfChordWithEveryPartContent[i - 1][2]) * \
                        frac(str(SIGTRE[1]) + '/' + str(SIGTRE[0]))
                    X.append((SpaceBeforeChord, [m.groupdict() for m in re.finditer(
                        PerChordPattern, ListOfChordWithEveryPartContent[i][0])][0]))
            Y.append(({DictItemWhichKeyIsPartName: X}, WholePartLength))
    return Y
