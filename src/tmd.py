#!/usr/local/bin/python3
from pathlib import Path
import TMDScanner as Scan
import re
import sys

''' necessary variables '''
ReservedInstrument = set({'CHORD', 'GROOVE'})
InstrumentSet = set()
PartSet = set()
Key = 'C'            # default key is C
Tempo = 120.0       # default tempo 120
SongName = ''       # defult no name
Signature = [4, 4]  # defult to 4/4
PartsContent = []
PartNameList = []
InputFile = ''

SUPPORTED_TYPES = {'SCORE', 'REMIX', 'VIDEO'}


def FileChecker(ARGV):
    MarkupTypePattern = r"^\:\:(?P<MarkType>\S+)\:\:\s*?$"
    if len(ARGV) < 2:
        print("usage:\n%s InputFile.tmd [-o output_file]\n" % ARGV[0])
        return False

    elif not Path(ARGV[1]).is_file():
        print("there is no file named %s!" % ARGV[1])
        return False

    elif re.search(MarkupTypePattern, open(ARGV[1], 'r').readline()) is None:
        print("unknown filetype")
        return False
    else:
        return True


def parse_args(argv):
    """Parse command-line arguments beyond the input file."""
    args = {'input': argv[1] if len(argv) > 1 else None}
    i = 2
    while i < len(argv):
        if argv[i] in ('-o', '--output') and i + 1 < len(argv):
            args['output'] = argv[i + 1]
            i += 2
        elif argv[i] in ('-r', '--resolution') and i + 1 < len(argv):
            args['resolution'] = argv[i + 1]
            i += 2
        elif argv[i] in ('--fps',) and i + 1 < len(argv):
            args['fps'] = int(argv[i + 1])
            i += 2
        elif argv[i] == '--dry-run':
            args['dry_run'] = True
            i += 1
        else:
            i += 1
    return args


def main_score(InputFile):
    """Original SCORE processing pipeline."""
    Key = Scan.KeyGetter(InputFile)
    Tempo = float(Scan.TempoGetter(InputFile))
    Signature = Scan.SignatureGetter(InputFile)
    SongName = Scan.SongNameGetter(InputFile)

    PartsContent = Scan.PartContentGetter(InputFile)
    PartNameList = Scan.PartSequenceGetter(InputFile)
    PartSet = Scan.PartSetGetter(PartsContent)
    InstrumentSet = Scan.InstrumentSetGetter(PartsContent)
    PreDrawChordMsg = Scan.PerChordSymbolAndPosition(PartsContent, Signature)
    for i in PreDrawChordMsg:
        print('This Part Length: ', i[1])
        for j in i[0]:
            print(j, ':')
            for k in i[0][j]:
                print(k[0], '\n', k[1],  'bar behind->', 'at bar ', str(int(k[0])),
                      '\trow:', int(k[0] // 6), '\tcol:', int(k[0]) % 6)
    print('\nthe sequence: ', PartNameList)


def main_remix(InputFile, args):
    """REMIX processing pipeline — audio remixing."""
    import TMDTimeline as TL
    import TMDMedia as TM

    Tempo = float(Scan.TempoGetter(InputFile))
    Signature = Scan.SignatureGetter(InputFile)
    SongName = Scan.SongNameGetter(InputFile)
    assets = Scan.AssetDeclGetter(InputFile)

    media_tracks = Scan.MediaTrackContentGetter(InputFile)
    order = Scan.PartSequenceGetter(InputFile)

    print(f"  Project: {SongName}")
    print(f"  Tempo:   {Tempo} BPM")
    print(f"  Order:   {' -> '.join(order)}")
    print(f"  Tracks:  {len(media_tracks)}")
    print(f"  Assets:  {assets}")
    print()

    events, total_dur = TL.build_timeline(media_tracks, order, Tempo, Signature)

    if args.get('dry_run'):
        print("=== Timeline (dry run) ===")
        for e in events:
            print(f"  {e}")
        print(f"\n  Total duration: {total_dur:.2f}s")
        return

    output = args.get('output', f'{SongName or "remix"}_output.wav')
    remixer = TM.AudioRemixer(events, assets=assets, output=output)
    remixer.render()


def main_video(InputFile, args):
    """VIDEO processing pipeline — video editing."""
    import TMDTimeline as TL
    import TMDMedia as TM

    Tempo = float(Scan.TempoGetter(InputFile))
    Signature = Scan.SignatureGetter(InputFile)
    SongName = Scan.SongNameGetter(InputFile)
    assets = Scan.AssetDeclGetter(InputFile)

    media_tracks = Scan.MediaTrackContentGetter(InputFile)
    order = Scan.PartSequenceGetter(InputFile)

    print(f"  Project: {SongName}")
    print(f"  Tempo:   {Tempo} BPM")
    print(f"  Order:   {' -> '.join(order)}")
    print(f"  Tracks:  {len(media_tracks)}")
    print(f"  Assets:  {assets}")
    print()

    events, total_dur = TL.build_timeline(media_tracks, order, Tempo, Signature)

    if args.get('dry_run'):
        print("=== Timeline (dry run) ===")
        for e in events:
            print(f"  {e}")
        print(f"\n  Total duration: {total_dur:.2f}s")
        return

    output = args.get('output', f'{SongName or "video"}_output.mp4')
    resolution = args.get('resolution', '1920x1080')
    fps = args.get('fps', 30)
    editor = TM.VideoEditor(events, assets=assets, output=output,
                            resolution=resolution, fps=fps)
    editor.render()


def main():
    ARGV = sys.argv

    if not FileChecker(ARGV):
        sys.exit('File Type Error')

    InputFile = open(ARGV[1], 'r').read()
    mark_type = Scan.MarkTypeGetter(InputFile)
    args = parse_args(ARGV)

    if mark_type not in SUPPORTED_TYPES:
        sys.exit(f'Unsupported file type: ::{mark_type}::  '
                 f'(supported: {", ".join(SUPPORTED_TYPES)})')

    if mark_type == 'SCORE':
        main_score(InputFile)
    elif mark_type == 'REMIX':
        main_remix(InputFile, args)
    elif mark_type == 'VIDEO':
        main_video(InputFile, args)


if __name__ == '__main__':
    main()
