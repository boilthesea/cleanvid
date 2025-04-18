#!/usr/bin/env python3

import argparse
import base64
import chardet
import codecs
import errno
import json
import os
import shutil
import tempfile
import sys
import subprocess
import re
import pysrt
import delegator
from datetime import datetime
from subliminal import *
from babelfish import Language
from collections import OrderedDict

try:
    from cleanvid.caselessdictionary import CaselessDictionary
except ImportError:
    from caselessdictionary import CaselessDictionary
from itertools import tee

__script_location__ = os.path.dirname(os.path.realpath(__file__))

VIDEO_DEFAULT_PARAMS = '-c:v libx264 -preset slow -crf 22'
AUDIO_DEFAULT_PARAMS = '-c:a aac -ab 224k -ar 44100'
# for downmixing, https://superuser.com/questions/852400 was helpful
AUDIO_DOWNMIX_FILTER = 'pan=stereo|FL=0.8*FC + 0.6*FL + 0.6*BL + 0.5*LFE|FR=0.8*FC + 0.6*FR + 0.6*BR + 0.5*LFE'
SUBTITLE_DEFAULT_LANG = 'eng'
PLEX_AUTO_SKIP_DEFAULT_CONFIG = '{"markers":{},"offsets":{},"tags":{},"allowed":{"users":[],"clients":[],"keys":[]},"blocked":{"users":[],"clients":[],"keys":[]},"clients":{},"mode":{}}'


# thanks https://docs.python.org/3/library/itertools.html#recipes
def pairwise(iterable):
    a, b = tee(iterable)
    next(b, None)
    return zip(a, b)


######## GetFormatAndStreamInfo ###############################################
def GetFormatAndStreamInfo(vidFileSpec):
    result = None
    if os.path.isfile(vidFileSpec):
        ffprobeCmd = "ffprobe -loglevel quiet -print_format json -show_format -show_streams \"" + vidFileSpec + "\""
        ffprobeResult = delegator.run(ffprobeCmd, block=True)
        if ffprobeResult.return_code == 0:
            result = json.loads(ffprobeResult.out)
    return result


######## GetAudioStreamsInfo ###############################################
def GetAudioStreamsInfo(vidFileSpec):
    result = None
    if os.path.isfile(vidFileSpec):
        ffprobeCmd = (
            "ffprobe -loglevel quiet -select_streams a -show_entries stream=index,codec_name,sample_rate,channel_layout:stream_tags=language -of json \""
            + vidFileSpec
            + "\""
        )
        ffprobeResult = delegator.run(ffprobeCmd, block=True)
        if ffprobeResult.return_code == 0:
            result = json.loads(ffprobeResult.out)
    return result


######## GetStreamSubtitleMap ###############################################
def GetStreamSubtitleMap(vidFileSpec):
    result = None
    if os.path.isfile(vidFileSpec):
        ffprobeCmd = (
            "ffprobe -loglevel quiet -select_streams s -show_entries stream=index:stream_tags=language -of csv=p=0 \""
            + vidFileSpec
            + "\""
        )
        ffprobeResult = delegator.run(ffprobeCmd, block=True)
        if ffprobeResult.return_code == 0:
            # e.g. for ara and chi, "-map 0:5 -map 0:7" or "-map 0:s:3 -map 0:s:5"
            # 2,eng
            # 3,eng
            # 4,eng
            # 5,ara
            # 6,bul
            # 7,chi
            # 8,cze
            # 9,dan
            result = OrderedDict()
            for l in [x.split(',') for x in ffprobeResult.out.split()]:
                result[int(l[0])] = l[1]
    return result


######## HasAudioMoreThanStereo ###############################################
def HasAudioMoreThanStereo(vidFileSpec):
    result = False
    if os.path.isfile(vidFileSpec):
        ffprobeCmd = (
            "ffprobe -loglevel quiet -select_streams a -show_entries stream=channels -of csv=p=0 \""
            + vidFileSpec
            + "\""
        )
        ffprobeResult = delegator.run(ffprobeCmd, block=True)
        if ffprobeResult.return_code == 0:
            result = any(
                [
                    x
                    for x in [int(''.join([z for z in y if z.isdigit()])) for y in list(set(ffprobeResult.out.split()))]
                    if x > 2
                ]
            )
    return result


######## SplitLanguageIfForced #####################################################
def SplitLanguageIfForced(lang):
    srtLanguageSplit = lang.split(':')
    srtLanguage = srtLanguageSplit[0]
    srtForceIndex = int(srtLanguageSplit[1]) if len(srtLanguageSplit) > 1 else None
    return srtLanguage, srtForceIndex


######## ExtractSubtitles #####################################################
def ExtractSubtitles(vidFileSpec, srtLanguage):
    subFileSpec = ""
    srtLanguage, srtForceIndex = SplitLanguageIfForced(srtLanguage)
    if (streamInfo := GetStreamSubtitleMap(vidFileSpec)) and (
        stream := (
            next(iter([k for k, v in streamInfo.items() if (v == srtLanguage)]), None)
            if not srtForceIndex
            else srtForceIndex
        )
    ):
        subFileParts = os.path.splitext(vidFileSpec)
        subFileSpec = subFileParts[0] + "." + srtLanguage + ".srt"
        ffmpegCmd = (
            "ffmpeg -hide_banner -nostats -loglevel error -y -i \""
            + vidFileSpec
            + f"\" -map 0:{stream} \""
            + subFileSpec
            + "\""
        )
        ffmpegResult = delegator.run(ffmpegCmd, block=True)
        if (ffmpegResult.return_code != 0) or (not os.path.isfile(subFileSpec)):
            subFileSpec = ""
    return subFileSpec


######## GetSubtitles #########################################################
def GetSubtitles(vidFileSpec, srtLanguage, offline=False):
    subFileSpec = ExtractSubtitles(vidFileSpec, srtLanguage)
    if not os.path.isfile(subFileSpec):
        if offline:
            subFileSpec = ""
        else:
            if os.path.isfile(vidFileSpec):
                subFileParts = os.path.splitext(vidFileSpec)
                srtLanguage, srtForceIndex = SplitLanguageIfForced(srtLanguage)
                subFileSpec = subFileParts[0] + "." + str(Language(srtLanguage)) + ".srt"
                if not os.path.isfile(subFileSpec):
                    video = Video.fromname(vidFileSpec)
                    bestSubtitles = download_best_subtitles([video], {Language(srtLanguage)})
                    savedSub = save_subtitles(video, [bestSubtitles[video][0]])

            if subFileSpec and (not os.path.isfile(subFileSpec)):
                subFileSpec = ""

    return subFileSpec


######## UTF8Convert #########################################################
# attempt to convert any text file to UTF-* without BOM and normalize line endings
def UTF8Convert(fileSpec, universalEndline=True):
    # Read from file
    with open(fileSpec, 'rb') as f:
        raw = f.read()

    # Decode
    raw = raw.decode(chardet.detect(raw)['encoding'])

    # Remove windows line endings
    if universalEndline:
        raw = raw.replace('\r\n', '\n')

    # Encode to UTF-8
    raw = raw.encode('utf8')

    # Remove BOM
    if raw.startswith(codecs.BOM_UTF8):
        raw = raw.replace(codecs.BOM_UTF8, '', 1)

    # Write to file
    with open(fileSpec, 'wb') as f:
        f.write(raw)


#################################################################################
class VidCleaner(object):
    inputVidFileSpec = ""
    inputSubsFileSpec = ""
    cleanSubsFileSpec = ""
    edlFileSpec = ""
    jsonFileSpec = ""
    tmpSubsFileSpec = ""
    assSubsFileSpec = ""
    outputVidFileSpec = ""
    swearsFileSpec = ""
    swearsPadMillisec = 0
    embedSubs = False
    fullSubs = False
    subsOnly = False
    edl = False
    hardCode = False
    reEncodeVideo = False
    reEncodeAudio = False
    unalteredVideo = False
    subsLang = SUBTITLE_DEFAULT_LANG
    vParams = VIDEO_DEFAULT_PARAMS
    audioStreamIdx = None
    aParams = AUDIO_DEFAULT_PARAMS
    aDownmix = False
    threadsInput = None
    threadsEncoding = None
    plexAutoSkipJson = ""
    plexAutoSkipId = ""
    swearsMap = CaselessDictionary({})
    muteTimeList = []
    jsonDumpList = None

    ######## init #################################################################

    def __init__(
        self,
        iVidFileSpec,
        iSubsFileSpec,
        oVidFileSpec,
        oSubsFileSpec,
        iSwearsFileSpec,
        swearsPadSec=0.0,
        embedSubs=False,
        fullSubs=False,
        subsOnly=False,
        edl=False,
        jsonDump=False,
        subsLang=SUBTITLE_DEFAULT_LANG,
        reEncodeVideo=False,
        reEncodeAudio=False,
        hardCode=False,
        vParams=VIDEO_DEFAULT_PARAMS,
        audioStreamIdx=None,
        aParams=AUDIO_DEFAULT_PARAMS,
        aDownmix=False,
        threadsInput=None,
        threadsEncoding=None,
        plexAutoSkipJson="",
        plexAutoSkipId="",
    ):
        if (iVidFileSpec is not None) and os.path.isfile(iVidFileSpec):
            self.inputVidFileSpec = iVidFileSpec
        else:
            raise IOError(errno.ENOENT, os.strerror(errno.ENOENT), iVidFileSpec)

        if (iSubsFileSpec is not None) and os.path.isfile(iSubsFileSpec):
            self.inputSubsFileSpec = iSubsFileSpec

        if (iSwearsFileSpec is not None) and os.path.isfile(iSwearsFileSpec):
            self.swearsFileSpec = iSwearsFileSpec
        else:
            raise IOError(errno.ENOENT, os.strerror(errno.ENOENT), iSwearsFileSpec)

        if (oVidFileSpec is not None) and (len(oVidFileSpec) > 0):
            self.outputVidFileSpec = oVidFileSpec
            if os.path.isfile(self.outputVidFileSpec):
                os.remove(self.outputVidFileSpec)

        if (oSubsFileSpec is not None) and (len(oSubsFileSpec) > 0):
            self.cleanSubsFileSpec = oSubsFileSpec
            if os.path.isfile(self.cleanSubsFileSpec):
                os.remove(self.cleanSubsFileSpec)

        self.swearsPadMillisec = round(swearsPadSec * 1000.0)
        self.embedSubs = embedSubs
        self.fullSubs = fullSubs
        self.subsOnly = subsOnly or edl or (plexAutoSkipJson and plexAutoSkipId)
        self.edl = edl
        self.jsonDumpList = [] if jsonDump else None
        self.plexAutoSkipJson = plexAutoSkipJson
        self.plexAutoSkipId = plexAutoSkipId
        self.reEncodeVideo = reEncodeVideo
        self.reEncodeAudio = reEncodeAudio
        self.hardCode = hardCode
        self.subsLang = subsLang
        self.vParams = vParams
        self.audioStreamIdx = audioStreamIdx
        self.aParams = aParams
        self.aDownmix = aDownmix
        self.threadsInput = threadsInput
        self.threadsEncoding = threadsEncoding
        if self.vParams.startswith('base64:'):
            self.vParams = base64.b64decode(self.vParams[7:]).decode('utf-8')
        if self.aParams.startswith('base64:'):
            self.aParams = base64.b64decode(self.aParams[7:]).decode('utf-8')

    ######## del ##################################################################
    def __del__(self):
        if (not os.path.isfile(self.outputVidFileSpec)) and (not self.unalteredVideo):
            if os.path.isfile(self.cleanSubsFileSpec):
                os.remove(self.cleanSubsFileSpec)
            if os.path.isfile(self.edlFileSpec):
                os.remove(self.edlFileSpec)
            if os.path.isfile(self.jsonFileSpec):
                os.remove(self.jsonFileSpec)
        if os.path.isfile(self.tmpSubsFileSpec):
            os.remove(self.tmpSubsFileSpec)
        if os.path.isfile(self.assSubsFileSpec):
            os.remove(self.assSubsFileSpec)

    ######## CreateCleanSubAndMuteList #################################################
    def CreateCleanSubAndMuteList(self):
        if (self.inputSubsFileSpec is None) or (not os.path.isfile(self.inputSubsFileSpec)):
            raise IOError(
                errno.ENOENT,
                f"Input subtitle file unspecified or not found ({os.strerror(errno.ENOENT)})",
                self.inputSubsFileSpec,
            )

        subFileParts = os.path.splitext(self.inputSubsFileSpec)

        self.tmpSubsFileSpec = subFileParts[0] + "_utf8" + subFileParts[1]
        shutil.copy2(self.inputSubsFileSpec, self.tmpSubsFileSpec)
        UTF8Convert(self.tmpSubsFileSpec)

        if not self.cleanSubsFileSpec:
            self.cleanSubsFileSpec = subFileParts[0] + "_clean" + subFileParts[1]

        if not self.edlFileSpec:
            cleanSubFileParts = os.path.splitext(self.cleanSubsFileSpec)
            self.edlFileSpec = cleanSubFileParts[0] + '.edl'

        if (self.jsonDumpList is not None) and (not self.jsonFileSpec):
            cleanSubFileParts = os.path.splitext(self.cleanSubsFileSpec)
            self.jsonFileSpec = cleanSubFileParts[0] + '.json'

        lines = []

        with open(self.swearsFileSpec) as f:
            lines = [line.rstrip('\n') for line in f]

        for line in lines:
            lineMap = line.split("|")
            if len(lineMap) > 1:
                self.swearsMap[lineMap[0]] = lineMap[1]
            else:
                self.swearsMap[lineMap[0]] = "*****"

        replacer = re.compile(r'\b(' + '|'.join(self.swearsMap.keys()) + r')\b', re.IGNORECASE)

        subs = pysrt.open(self.tmpSubsFileSpec)
        newSubs = pysrt.SubRipFile()
        newTimestampPairs = []

        # append a dummy sub at the very end so that pairwise can peek and see nothing
        subs.append(
            pysrt.SubRipItem(
                index=len(subs) + 1,
                start=(subs[-1].end.seconds if subs else 0) + 1,
                end=(subs[-1].end.seconds if subs else 0) + 2,
                text='Fin',
            )
        )

        # for each subtitle in the set
        # if text contains profanity...
        # OR if the next text contains profanity and lies within the pad ...
        # OR if the previous text contained profanity and lies within the pad ...
        # then include the subtitle in the new set
        prevNaughtySub = None
        for sub, subPeek in pairwise(subs):
            newText = replacer.sub(lambda x: self.swearsMap[x.group()], sub.text)
            newTextPeek = (
                replacer.sub(lambda x: self.swearsMap[x.group()], subPeek.text) if (subPeek is not None) else None
            )
            # this sub contains profanity, or
            if (
                (newText != sub.text)
                or
                # we have defined a pad, and
                (
                    (self.swearsPadMillisec > 0)
                    and (newTextPeek is not None)
                    and
                    # the next sub contains profanity and is within pad seconds of this one, or
                    (
                        (
                            (newTextPeek != subPeek.text)
                            and ((subPeek.start.ordinal - sub.end.ordinal) <= self.swearsPadMillisec)
                        )
                        or
                        # the previous sub contained profanity and is within pad seconds of this one
                        (
                            (prevNaughtySub is not None)
                            and ((sub.start.ordinal - prevNaughtySub.end.ordinal) <= self.swearsPadMillisec)
                        )
                    )
                )
            ):
                subScrubbed = newText != sub.text
                if subScrubbed and (self.jsonDumpList is not None):
                    self.jsonDumpList.append(
                        {
                            'old': sub.text,
                            'new': newText,
                            'start': str(sub.start),
                            'end': str(sub.end),
                        }
                    )
                newSub = sub
                newSub.text = newText
                newSubs.append(newSub)
                if subScrubbed:
                    prevNaughtySub = sub
                    newTimes = [
                        pysrt.SubRipTime.from_ordinal(sub.start.ordinal - self.swearsPadMillisec).to_time(),
                        pysrt.SubRipTime.from_ordinal(sub.end.ordinal + self.swearsPadMillisec).to_time(),
                    ]
                else:
                    prevNaughtySub = None
                    newTimes = [sub.start.to_time(), sub.end.to_time()]
                newTimestampPairs.append(newTimes)
            else:
                if self.fullSubs:
                    newSubs.append(sub)
                prevNaughtySub = None

        newSubs.save(self.cleanSubsFileSpec)
        if self.jsonDumpList is not None:
            with open(self.jsonFileSpec, "w") as f:
                f.write(
                    json.dumps(
                        {
                            "now": datetime.now().isoformat(),
                            "edits": self.jsonDumpList,
                            "media": {
                                "input": self.inputVidFileSpec,
                                "output": self.outputVidFileSpec,
                                "ffprobe": GetFormatAndStreamInfo(self.inputVidFileSpec),
                            },
                            "subtitles": {
                                "input": self.inputSubsFileSpec,
                                "output": self.cleanSubsFileSpec,
                            },
                        },
                        indent=4,
                    )
                )

        self.muteTimeList = []
        edlLines = []
        plexDict = json.loads(PLEX_AUTO_SKIP_DEFAULT_CONFIG) if self.plexAutoSkipId and self.plexAutoSkipJson else None

        if plexDict:
            plexDict["markers"][self.plexAutoSkipId] = []
            plexDict["mode"][self.plexAutoSkipId] = "volume"

        # Append one at the very end of the file to work with pairwise
        newTimes = [pysrt.SubRipTime.from_ordinal(subs[-1].end.ordinal).to_time(), None]
        newTimestampPairs.append(newTimes)

        for timePair, timePairPeek in pairwise(newTimestampPairs):
            lineStart = (
                (timePair[0].hour * 60.0 * 60.0)
                + (timePair[0].minute * 60.0)
                + timePair[0].second
                + (timePair[0].microsecond / 1000000.0)
            )
            lineEnd = (
                (timePair[1].hour * 60.0 * 60.0)
                + (timePair[1].minute * 60.0)
                + timePair[1].second
                + (timePair[1].microsecond / 1000000.0)
            )
            lineStartPeek = (
                (timePairPeek[0].hour * 60.0 * 60.0)
                + (timePairPeek[0].minute * 60.0)
                + timePairPeek[0].second
                + (timePairPeek[0].microsecond / 1000000.0)
            )
            self.muteTimeList.append(
                "afade=enable='between(t,"
                + format(lineStart, '.3f')
                + ","
                + format(lineEnd, '.3f')
                + ")':t=out:st="
                + format(lineStart, '.3f')
                + ":d=10ms"
            )
            self.muteTimeList.append(
                "afade=enable='between(t,"
                + format(lineEnd, '.3f')
                + ","
                + format(lineStartPeek, '.3f')
                + ")':t=in:st="
                + format(lineEnd, '.3f')
                + ":d=10ms"
            )
            if self.edl:
                edlLines.append(f"{format(lineStart, '.1f')}\t{format(lineEnd, '.3f')}\t1")
            if plexDict:
                plexDict["markers"][self.plexAutoSkipId].append(
                    {"start": round(lineStart * 1000.0), "end": round(lineEnd * 1000.0), "mode": "volume"}
                )
        if self.edl and (len(edlLines) > 0):
            with open(self.edlFileSpec, 'w') as edlFile:
                for item in edlLines:
                    edlFile.write(f"{item}\n")
        if plexDict and (len(plexDict["markers"][self.plexAutoSkipId]) > 0):
            json.dump(
                plexDict,
                open(self.plexAutoSkipJson, 'w'),
                indent=4,
            )

    ######## MultiplexCleanVideo ###################################################
    def MultiplexCleanVideo(self):
        # if we're don't *have* to generate a new video file, don't
        # we need to generate a video file if any of the following are true:
        # - we were explicitly asked to re-encode
        # - we are hard-coding (burning) subs
        # - we are embedding a subtitle stream
        # - we are not doing "subs only" or EDL mode and there more than zero mute sections
        if (
            self.reEncodeVideo
            or self.reEncodeAudio
            or self.hardCode
            or self.embedSubs
            or ((not self.subsOnly) and (len(self.muteTimeList) > 0))
        ):
            if self.reEncodeVideo or self.hardCode:
                if self.hardCode and os.path.isfile(self.cleanSubsFileSpec):
                    self.assSubsFileSpec = self.cleanSubsFileSpec + '.ass'
                    subConvCmd = f"ffmpeg -hide_banner -nostats -loglevel error -y -i {self.cleanSubsFileSpec} {self.assSubsFileSpec}"
                    subConvResult = delegator.run(subConvCmd, block=True)
                    if (subConvResult.return_code == 0) and os.path.isfile(self.assSubsFileSpec):
                        videoArgs = f"{self.vParams} -vf \"ass={self.assSubsFileSpec}\""
                    else:
                        print(subConvCmd)
                        print(subConvResult.err)
                        raise ValueError(f'Could not process {self.cleanSubsFileSpec}')
                else:
                    videoArgs = self.vParams
            else:
                videoArgs = "-c:v copy"

            audioStreamOnlyIndex = 0
            if audioStreams := GetAudioStreamsInfo(self.inputVidFileSpec).get('streams', []):
                if len(audioStreams) > 0:
                    if self.audioStreamIdx is None:
                        if len(audioStreams) == 1:
                            if 'index' in audioStreams[0]:
                                self.audioStreamIdx = audioStreams[0]['index']
                            else:
                                raise ValueError(f'Could not determine audio stream index for {self.inputVidFileSpec}')
                        else:
                            raise ValueError(
                                f'Multiple audio streams, specify audio stream index with --audio-stream-index'
                            )
                    elif any(stream.get('index', -1) == self.audioStreamIdx for stream in audioStreams):
                        audioStreamOnlyIndex = next(
                            (
                                i
                                for i, stream in enumerate(audioStreams)
                                if stream.get('index', -1) == self.audioStreamIdx
                            ),
                            0,
                        )
                    else:
                        raise ValueError(
                            f'Audio stream index {self.audioStreamIdx} is invalid for {self.inputVidFileSpec}'
                        )
                else:
                    raise ValueError(f'No audio streams found in {self.inputVidFileSpec}')
            else:
                raise ValueError(f'Could not determine audio streams in {self.inputVidFileSpec}')
            self.aParams = re.sub(r"-c:a(\s+)", rf"-c:a:{str(audioStreamOnlyIndex)}\1", self.aParams)
            audioUnchangedMapList = ' '.join(
                f'-map 0:a:{i}' if i != audioStreamOnlyIndex else '' for i in range(len(audioStreams))
            )

            if self.aDownmix and HasAudioMoreThanStereo(self.inputVidFileSpec):
                self.muteTimeList.insert(0, AUDIO_DOWNMIX_FILTER)
            if (not self.subsOnly) and (len(self.muteTimeList) > 0):
                audioFilter = f' -filter_complex "[0:a:{audioStreamOnlyIndex}]{",".join(self.muteTimeList)}[a{audioStreamOnlyIndex}]"'
            else:
                audioFilter = " "
            if self.embedSubs and os.path.isfile(self.cleanSubsFileSpec):
                outFileParts = os.path.splitext(self.outputVidFileSpec)
                subsArgsInput = f" -i \"{self.cleanSubsFileSpec}\" "
                subsArgsEmbed = f" -map 1:s -c:s {'mov_text' if outFileParts[1] == '.mp4' else 'srt'} -disposition:s:0 default -metadata:s:s:0 language={self.subsLang} "
            else:
                subsArgsInput = ""
                subsArgsEmbed = " -sn "

            ffmpegCmd = (
                f"ffmpeg -hide_banner -nostats -loglevel error -y {'' if self.threadsInput is None else ('-threads '+ str(int(self.threadsInput)))} -i \""
                + self.inputVidFileSpec
                + "\""
                + subsArgsInput
                + audioFilter
                + f' -map 0:v -map "[a{audioStreamOnlyIndex}]" {audioUnchangedMapList} '
                + subsArgsEmbed
                + videoArgs
                + f" {self.aParams} {'' if self.threadsEncoding is None else ('-threads '+ str(int(self.threadsEncoding)))} \""
                + self.outputVidFileSpec
                + "\""
            )
            ffmpegResult = delegator.run(ffmpegCmd, block=True)
            if (ffmpegResult.return_code != 0) or (not os.path.isfile(self.outputVidFileSpec)):
                print(ffmpegCmd)
                print(ffmpegResult.err)
                raise ValueError(f'Could not process {self.inputVidFileSpec}')
        else:
            self.unalteredVideo = True


#################################################################################
def RunCleanvid():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-s',
        '--subs',
        help='.srt subtitle file (will attempt auto-download if unspecified and not --offline)',
        metavar='<srt>',
    )
    parser.add_argument('-i', '--input', required=True, help='input video file', metavar='<input video>')
    parser.add_argument('-o', '--output', help='output video file', metavar='<output video>')
    parser.add_argument(
        '--plex-auto-skip-json',
        help='custom JSON file for PlexAutoSkip (also implies --subs-only)',
        metavar='<output JSON>',
        dest="plexAutoSkipJson",
    )
    parser.add_argument(
        '--plex-auto-skip-id',
        help='content identifier for PlexAutoSkip (also implies --subs-only)',
        metavar='<content identifier>',
        dest="plexAutoSkipId",
    )
    parser.add_argument('--subs-output', help='output subtitle file', metavar='<output srt>', dest="subsOut")
    parser.add_argument(
        '-w',
        '--swears',
        help='text file containing profanity (with optional mapping)',
        default=os.path.join(__script_location__, 'swears.txt'),
        metavar='<profanity file>',
    )
    parser.add_argument(
        '-l',
        '--lang',
        help=f'language for extracting srt from video file or srt download (default is "{SUBTITLE_DEFAULT_LANG}")',
        default=SUBTITLE_DEFAULT_LANG,
        metavar='<language>',
    )
    parser.add_argument(
        '-p', '--pad', help='pad (seconds) around profanity', metavar='<int>', dest="pad", type=float, default=0.0
    )
    parser.add_argument(
        '-e',
        '--embed-subs',
        help='embed subtitles in resulting video file',
        dest='embedSubs',
        action='store_true',
    )
    parser.add_argument(
        '-f',
        '--full-subs',
        help='include all subtitles in output subtitle file (not just scrubbed)',
        dest='fullSubs',
        action='store_true',
    )
    parser.add_argument(
        '--subs-only',
        help='only operate on subtitles (do not alter audio)',
        dest='subsOnly',
        action='store_true',
    )
    parser.add_argument(
        '--offline',
        help="don't attempt to download subtitles",
        dest='offline',
        action='store_true',
    )
    parser.add_argument(
        '--edl',
        help='generate MPlayer EDL file with mute actions (also implies --subs-only)',
        dest='edl',
        action='store_true',
    )
    parser.add_argument(
        '--json',
        help='generate JSON file with muted subtitles and their contents',
        dest='json',
        action='store_true',
    )
    parser.add_argument('--re-encode-video', help='Re-encode video', dest='reEncodeVideo', action='store_true')
    parser.add_argument('--re-encode-audio', help='Re-encode audio', dest='reEncodeAudio', action='store_true')
    parser.add_argument(
        '-b', '--burn', help='Hard-coded subtitles (implies re-encode)', dest='hardCode', action='store_true'
    )
    parser.add_argument(
        '-v',
        '--video-params',
        help='Video parameters for ffmpeg (only if re-encoding)',
        dest='vParams',
        default=VIDEO_DEFAULT_PARAMS,
    )
    parser.add_argument(
        '-a', '--audio-params', help='Audio parameters for ffmpeg', dest='aParams', default=AUDIO_DEFAULT_PARAMS
    )
    parser.add_argument(
        '-d', '--downmix', help='Downmix to stereo (if not already stereo)', dest='aDownmix', action='store_true'
    )
    parser.add_argument(
        '--audio-stream-index',
        help='Index of audio stream to process',
        metavar='<int>',
        dest="audioStreamIdx",
        type=int,
        default=None,
    )
    parser.add_argument(
        '--audio-stream-list',
        help='Show list of audio streams (to get index for --audio-stream-index)',
        action='store_true',
        dest="audioStreamIdxList",
    )
    parser.add_argument(
        '--threads-input',
        help='ffmpeg global options -threads value',
        metavar='<int>',
        dest="threadsInput",
        type=int,
        default=None,
    )
    parser.add_argument(
        '--threads-encoding',
        help='ffmpeg encoding options -threads value',
        metavar='<int>',
        dest="threadsEncoding",
        type=int,
        default=None,
    )
    parser.add_argument(
        '--threads',
        help='ffmpeg -threads value (for both global options and encoding)',
        metavar='<int>',
        dest="threads",
        type=int,
        default=None,
    )
    parser.add_argument(
        '--alass',
        help='Attempt to synchronize subtitles with video using alass before cleaning (requires alass in PATH)',
        action='store_true',
        dest="use_alass"
    )
    # --- Add --win flag ---
    parser.add_argument(
        '--win',
        help='Use Windows-compatible multi-step processing (avoids command length errors)',
        action='store_true',
        dest="use_win_method" # Use a distinct destination variable
    )
    parser.set_defaults(
        audioStreamIdxList=False,
        edl=False,
        embedSubs=False,
        fullSubs=False,
        hardCode=False,
        offline=False,
        reEncodeAudio=False,
        reEncodeVideo=False,
        subsOnly=False,
        use_alass=False, # Default alass to False
        use_win_method=False, # Default to False
    )
    args = parser.parse_args()

    # --- Check for --win flag ---
    if args.use_win_method:
        # --- Execute cleanvidwin.py ---
        print("Windows compatibility mode requested (--win). Delegating to cleanvidwin.py...")

        # Construct path to cleanvidwin.py (assuming it's in the same directory)
        script_dir = os.path.dirname(__file__)
        cleanvidwin_path = os.path.join(script_dir, 'cleanvidwin.py')

        if not os.path.exists(cleanvidwin_path):
             print(f"Error: cleanvidwin.py not found at {cleanvidwin_path}", file=sys.stderr)
             sys.exit(1)

        # Prepare arguments for cleanvidwin.py (pass all except the --win flag itself)
        win_args = [arg for arg in sys.argv[1:] if arg != '--win']
        print(f"Executing: {sys.executable} {cleanvidwin_path} {' '.join(win_args)}")

        # Execute cleanvidwin.py using the same Python interpreter
        try:
            process_result = subprocess.run(
                [sys.executable, cleanvidwin_path] + win_args,
                check=True, # Raise exception on non-zero exit code
                capture_output=False, # Let output go directly to console
                text=True,
                # Ensure environment variables like PATH are passed through if needed by ffmpeg
                env=os.environ
            )
            print("cleanvidwin.py completed successfully.")
            sys.exit(0) # Exit successfully after delegation
        except subprocess.CalledProcessError as e:
            print(f"Error executing cleanvidwin.py: {e}", file=sys.stderr)
            # Optionally print stdout/stderr from the failed process if captured
            # print(f"Stdout:\n{e.stdout}", file=sys.stderr)
            # print(f"Stderr:\n{e.stderr}", file=sys.stderr)
            sys.exit(e.returncode) # Exit with the same error code
        except Exception as e:
             print(f"An unexpected error occurred while trying to run cleanvidwin.py: {e}", file=sys.stderr)
             sys.exit(1)

    # --- Original Logic (if --win is not used) ---
    else:
        print("Using standard processing method. Use --win for Windows compatibility mode.")
        if args.audioStreamIdxList:
            audioStreamsInfo = GetAudioStreamsInfo(args.input)
            # e.g.:
            #   1: aac, 44100 Hz, stereo, eng
            #   3: opus, 48000 Hz, stereo, jpn
            print(
                '\n'.join(
                    [
                        f"{x['index']}: {x.get('codec_name', 'unknown codec')}, {x.get('sample_rate', 'unknown')} Hz, {x.get('channel_layout', 'unknown channel layout')}, {x.get('tags', {}).get('language', 'unknown language')}"
                        for x in audioStreamsInfo.get("streams", [])
                    ]
                )
            )
            sys.exit(0) # Exit after listing streams

        # Proceed with normal processing setup
        inFile = args.input
        outFile = args.output
        subsFile = args.subs
        lang = args.lang
        plexFile = args.plexAutoSkipJson
        if inFile:
            inFileParts = os.path.splitext(inFile)
            if not outFile:
                outFile = inFileParts[0] + "_clean" + inFileParts[1]
            if not subsFile:
                subsFile = GetSubtitles(inFile, lang, args.offline)
            if args.plexAutoSkipId and not plexFile:
                plexFile = inFileParts[0] + "_PlexAutoSkip_clean.json"

        # --- Optional Alass Synchronization ---
        alass_temp_srt_file = None # To track temp file for cleanup
        if args.use_alass:
            if subsFile and os.path.isfile(subsFile):
                print(f"Attempting subtitle synchronization with alass for: {subsFile}")
                try:
                    # Create a temporary file for alass output
                    # Use NamedTemporaryFile correctly - create it, get name, close handle
                    temp_f = tempfile.NamedTemporaryFile(suffix=".srt", delete=False, mode='w', encoding='utf-8')
                    alass_temp_srt_file = temp_f.name
                    temp_f.close() # Close the handle so alass can write to it (on Windows)
                    print(f"  Using temporary file for alass output: {alass_temp_srt_file}")

                    alass_cmd = f'alass "{inFile}" "{subsFile}" "{alass_temp_srt_file}"'
                    print(f"  Executing: {alass_cmd}")
                    alass_result = delegator.run(alass_cmd, block=True)

                    if alass_result.return_code == 0 and os.path.isfile(alass_temp_srt_file) and os.path.getsize(alass_temp_srt_file) > 0:
                        print(f"  Alass synchronization successful. Using synced subtitles: {alass_temp_srt_file}")
                        subsFile = alass_temp_srt_file # Update subsFile to point to the synced version
                    else:
                        print(f"  Warning: Alass synchronization failed (return code: {alass_result.return_code}). Proceeding with original subtitles.", file=sys.stderr)
                        print(f"  Alass stderr: {alass_result.err}", file=sys.stderr)
                        # Clean up the potentially empty/failed temp file immediately
                        if os.path.exists(alass_temp_srt_file):
                            os.remove(alass_temp_srt_file)
                        alass_temp_srt_file = None # Reset tracker
                except Exception as e:
                    print(f"  Warning: An error occurred during alass execution: {e}. Proceeding with original subtitles.", file=sys.stderr)
                    if alass_temp_srt_file and os.path.exists(alass_temp_srt_file): os.remove(alass_temp_srt_file) # Cleanup on exception
                    alass_temp_srt_file = None # Reset tracker
            else:
                print("  Warning: --alass flag specified, but no valid subtitle file found to synchronize.", file=sys.stderr)

        if plexFile and not args.plexAutoSkipId:
            raise ValueError(
                f'Content ID must be specified if creating a PlexAutoSkip JSON file (https://github.com/mdhiggins/PlexAutoSkip/wiki/Identifiers)'
            )

        # Instantiate the cleaner and run processing within try/finally for cleanup
        try:
            cleaner = VidCleaner(
                 inFile,
                 subsFile, # This will be the original or the alass temp file
                 outFile,
                 args.subsOut,
                 args.swears,
                 args.pad,
                 args.embedSubs,
                 args.fullSubs,
                 args.subsOnly,
                 args.edl,
                 args.json,
                 lang,
                 args.reEncodeVideo,
                 args.reEncodeAudio,
                 args.hardCode,
                 args.vParams,
                 args.audioStreamIdx,
                 args.aParams,
                 args.aDownmix,
                 args.threadsInput if args.threadsInput is not None else args.threads,
                 args.threadsEncoding if args.threadsEncoding is not None else args.threads,
                 plexFile,
                 args.plexAutoSkipId,
            )
            cleaner.CreateCleanSubAndMuteList()
            # --- Wrap the potentially failing call ---
            cleaner.MultiplexCleanVideo()
            print("Processing completed successfully using standard method.")

        except ValueError as e:
            print(f"\n--- Processing Error ---", file=sys.stderr)
            print(f"Error details: {e}", file=sys.stderr)
            # Check if it's likely the command length error (heuristic)
            is_windows = sys.platform.startswith('win')
            # Suggest --win only on Windows and if the error isn't about missing files/streams
            # (More specific error checking could be added here if needed)
            if is_windows:
                 print("\nSuggestion: Processing failed.", file=sys.stderr)
                 print("If you are on Windows and suspect a command-line length error,", file=sys.stderr)
                 print("try running the command again with the --win flag added.", file=sys.stderr)
            sys.exit(1) # Exit with error code after printing suggestion
        except Exception as e:
             # Catch other potential errors during original processing
             print(f"\n--- Unexpected Error ---", file=sys.stderr)
             print(f"Error details: {e}", file=sys.stderr)
             # Consider printing traceback for unexpected errors
             # import traceback
             # traceback.print_exc(file=sys.stderr)
             sys.exit(1)
        finally:
            # --- Cleanup Alass Temp File ---
            if alass_temp_srt_file and os.path.exists(alass_temp_srt_file):
                print(f"Cleaning up temporary alass file: {alass_temp_srt_file}")
                os.remove(alass_temp_srt_file)


#################################################################################
if __name__ == '__main__':
    RunCleanvid()

#################################################################################
