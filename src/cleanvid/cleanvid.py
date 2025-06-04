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

# Helper function to run ffmpeg and check results
def run_ffmpeg_command(command, error_message_prefix="ffmpeg command failed"):
    print(f"Running ffmpeg command:\n{command}") # Log the command
    result = delegator.run(command, block=True)
    if result.return_code != 0:
        print(f"ffmpeg stderr:\n{result.err}")
        raise ValueError(f"{error_message_prefix}: {result.err}")
    print("ffmpeg command completed successfully.")
    return result

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
    use_win_method = False # Added for Windows compatibility

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
        use_win_method=False, # Added for Windows compatibility
        chapter_markers=False,
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
        self.use_win_method = use_win_method # Added for Windows compatibility
        self.chapter_markers = chapter_markers
        self.chapter_file_path = None

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
        # Keep ASS if hardcoding succeeded (logic from cleanvidwin.py)
        if os.path.isfile(self.assSubsFileSpec) and not self.hardCode:
            try:
                os.remove(self.assSubsFileSpec)
            except OSError:
                pass # Ignore error if file is gone
        if self.chapter_file_path and os.path.isfile(self.chapter_file_path):
            try:
                os.remove(self.chapter_file_path)
                print(f"Cleaned up chapter file: {self.chapter_file_path}")
            except OSError as e:
                print(f"Warning: Could not delete chapter file {self.chapter_file_path}: {e}")


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

        if self.chapter_markers:
            self.chapter_list = []
            # Iterate through newTimestampPairs (excluding the dummy one at the end)
            for timePair in newTimestampPairs[:-1]: # Exclude the dummy pair
                start_time = timePair[0] # datetime.time object
                # Calculate chapter start time in milliseconds
                chapter_start_ms = (start_time.hour * 3600 +
                                    start_time.minute * 60 +
                                    start_time.second) * 1000 + \
                                   start_time.microsecond // 1000
                self.chapter_list.append({
                    'start': chapter_start_ms,
                    'title': f"Muted Segment {len(self.chapter_list) + 1}"
                })

    ######## MultiplexCleanVideo ###################################################
    def MultiplexCleanVideo(self):
        if self.chapter_markers and hasattr(self, 'chapter_list') and self.chapter_list:
            try:
                # Create a temporary file for chapters
                with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt', encoding='utf-8') as f:
                    self.chapter_file_path = f.name
                    f.write(";FFMETADATA1\n")
                    f.write("TIMEBASE=1/1000\n") # Times are in milliseconds
                    for c in self.chapter_list:
                        f.write("[CHAPTER]\n")
                        f.write(f"START={c['start']}\n")
                        f.write(f"END={c['start']}\n") # Point chapters
                        f.write(f"title={c['title']}\n")
                print(f"Chapter file created: {self.chapter_file_path}")
            except Exception as e:
                print(f"Error creating chapter file: {e}")
                self.chapter_file_path = None # Ensure it's None if creation failed

        if not self.use_win_method:
            # Original single-step ffmpeg logic
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
                        # Use run_ffmpeg_command helper
                        subConvCmd = f"ffmpeg -hide_banner -nostats -loglevel error -y -i \"{self.cleanSubsFileSpec}\" \"{self.assSubsFileSpec}\""
                        run_ffmpeg_command(subConvCmd, f'Could not process {self.cleanSubsFileSpec} to ASS')
                        if os.path.isfile(self.assSubsFileSpec):
                            videoArgs = f"{self.vParams} -vf \"ass={self.assSubsFileSpec.replace(':', r'\\\\:')}\"" # Escaping for Windows paths
                        else:
                            raise ValueError(f'ASS file not created: {self.assSubsFileSpec}')
                    else:
                        videoArgs = self.vParams
                else:
                    videoArgs = "-c:v copy"

                audioStreamOnlyIndex = 0
                # Ensure self.actual_audio_streams is populated for consistency, though not directly used in this path's audioUnchangedMapList
                audioStreamsInfo = GetAudioStreamsInfo(self.inputVidFileSpec)
                if audioStreamsInfo and 'streams' in audioStreamsInfo and audioStreamsInfo['streams']:
                    self.actual_audio_streams = audioStreamsInfo['streams']
                else:
                    self.actual_audio_streams = [] # Ensure it's an empty list if no streams

                if len(self.actual_audio_streams) > 0:
                    if self.audioStreamIdx is None:
                        if len(self.actual_audio_streams) == 1:
                            if 'index' in self.actual_audio_streams[0]:
                                self.audioStreamIdx = self.actual_audio_streams[0]['index']
                                audioStreamOnlyIndex = 0 # Since it's the first and only stream in the list
                            else:
                                raise ValueError(f'Could not determine audio stream index for {self.inputVidFileSpec}')
                        else:
                            raise ValueError(
                                f'Multiple audio streams, specify audio stream index with --audio-stream-index'
                            )
                    elif any(stream.get('index', -1) == self.audioStreamIdx for stream in self.actual_audio_streams):
                        audioStreamOnlyIndex = next(
                            (
                                i
                                for i, stream in enumerate(self.actual_audio_streams)
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

                # Original aParams modification - ensure it targets the correct 0-based index from the enumerated list
                self.aParams = re.sub(r"-c:a(?::\d+)?(\s+)", rf"-c:a:{str(audioStreamOnlyIndex)}\1", self.aParams, 1)
                if not re.search(r"-c:a:" + str(audioStreamOnlyIndex), self.aParams): # if no stream specifier was there
                     self.aParams = re.sub(r"-c:a(\s+)", rf"-c:a:{str(audioStreamOnlyIndex)}\1", self.aParams, 1)


                audioUnchangedMapList = ' '.join(
                    # Use the 0-based index from enumeration for mapping
                    f'-map 0:a:{i}' if stream.get('index') != self.audioStreamIdx else ''
                    for i, stream in enumerate(self.actual_audio_streams)
                ).strip()


                if self.aDownmix and HasAudioMoreThanStereo(self.inputVidFileSpec):
                    self.muteTimeList.insert(0, AUDIO_DOWNMIX_FILTER)
                if (not self.subsOnly) and (len(self.muteTimeList) > 0):
                    # Use the 0-based index for filter_complex
                    audioFilter = f' -filter_complex "[0:a:{audioStreamOnlyIndex}]{",".join(self.muteTimeList)}[a{audioStreamOnlyIndex}]"'
                    mapAudioOutput = f'[a{audioStreamOnlyIndex}]'
                else:
                    audioFilter = " "
                    # Map the selected audio stream directly if no filter
                    mapAudioOutput = f'0:a:{audioStreamOnlyIndex}'

                # Build input list and map arguments
                inputs = [f'-i "{self.inputVidFileSpec}"']
                maps = [f'-map 0:v', f'-map "{mapAudioOutput}"']
                if audioUnchangedMapList:
                    maps.append(audioUnchangedMapList)

                input_idx_counter = 1 # Video is 0
                metadata_map_idx = None
                subs_map_idx = None

                if self.chapter_file_path:
                    inputs.append(f'-i "{self.chapter_file_path}"')
                    metadata_map_idx = input_idx_counter
                    input_idx_counter += 1

                if self.embedSubs and os.path.isfile(self.cleanSubsFileSpec):
                    inputs.append(f'-i "{self.cleanSubsFileSpec}"')
                    subs_map_idx = input_idx_counter
                    # input_idx_counter += 1 # Not strictly necessary if it's the last input

                ffmpeg_inputs_str = " ".join(inputs)
                ffmpeg_maps_str = " ".join(maps)

                ffmpeg_metadata_map_str = ""
                if metadata_map_idx is not None:
                    ffmpeg_metadata_map_str = f" -map_metadata {metadata_map_idx}"

                ffmpeg_subs_embed_str = " -sn " # Default to no subtitles
                if subs_map_idx is not None:
                    outFileParts = os.path.splitext(self.outputVidFileSpec)
                    subs_codec = 'mov_text' if outFileParts[1] == '.mp4' else 'srt'
                    ffmpeg_subs_embed_str = f" -map {subs_map_idx}:s -c:s {subs_codec} -disposition:s:0 default -metadata:s:s:0 language={self.subsLang} "

                ffmpegCmd = (
                    f"ffmpeg -hide_banner -nostats -loglevel error -y {'' if self.threadsInput is None else ('-threads '+ str(int(self.threadsInput)))} "
                    f"{ffmpeg_inputs_str} "
                    f"{audioFilter} " # audioFilter already contains necessary spaces
                    f"{ffmpeg_maps_str} "
                    f"{ffmpeg_subs_embed_str} "
                    f"{videoArgs} " # videoArgs might include hardcoded subs, which is fine
                    f"{self.aParams} "
                    f"{ffmpeg_metadata_map_str} " # map_metadata should come before output file
                    f"{'' if self.threadsEncoding is None else ('-threads '+ str(int(self.threadsEncoding)))} "
                    f"\"{self.outputVidFileSpec}\""
                )
                # Use run_ffmpeg_command helper
                run_ffmpeg_command(ffmpegCmd.strip(), f'Could not process {self.inputVidFileSpec}')
                if not os.path.isfile(self.outputVidFileSpec):
                     raise ValueError(f'Output file {self.outputVidFileSpec} was not created by ffmpeg (standard path).')
            else:
                self.unalteredVideo = True
        else:
            # Multi-step ffmpeg logic from cleanvidwin.py
            temp_files_to_clean = []
            temp_filter_filepath = None
            # audioStreams = None # Not needed as self.actual_audio_streams is used

            try:
                needs_processing = (
                    self.reEncodeVideo
                    or self.reEncodeAudio
                    or self.hardCode
                    or self.embedSubs
                    or ((not self.subsOnly) and (len(self.muteTimeList) > 0))
                )

                if not needs_processing:
                    self.unalteredVideo = True
                    print("No video/audio processing required based on options (Windows path).")
                    return

                audioStreamOnlyIndex = 0
                audioStreamsInfo = GetAudioStreamsInfo(self.inputVidFileSpec) # Call GetAudioStreamsInfo
                if not audioStreamsInfo or 'streams' not in audioStreamsInfo or not audioStreamsInfo['streams']:
                    raise ValueError(f'Could not determine audio streams in {self.inputVidFileSpec} (Windows path)')
                
                self.actual_audio_streams = audioStreamsInfo['streams'] # Set self.actual_audio_streams

                if self.audioStreamIdx is None:
                    if len(self.actual_audio_streams) == 1:
                        if 'index' in self.actual_audio_streams[0]:
                            self.audioStreamIdx = self.actual_audio_streams[0]['index']
                            audioStreamOnlyIndex = 0 # 0-based index in the list
                        else:
                            raise ValueError(f'Could not determine audio stream index for {self.inputVidFileSpec} (Windows path)')
                    else:
                        raise ValueError(
                            f'Multiple audio streams ({len(self.actual_audio_streams)} found), specify audio stream index with --audio-stream-index (Windows path)'
                        )
                elif any(stream.get('index', -1) == self.audioStreamIdx for stream in self.actual_audio_streams):
                    audioStreamOnlyIndex = next((i for i, s in enumerate(self.actual_audio_streams) if s.get('index') == self.audioStreamIdx), 0)
                else:
                    raise ValueError(
                        f'Audio stream index {self.audioStreamIdx} is invalid for {self.inputVidFileSpec} (Windows path)'
                    )
                
                print(f"Selected audio stream (Windows path): Input Index={self.audioStreamIdx}, FFmpeg Map Index=0:a:{audioStreamOnlyIndex}")

                if self.aDownmix and HasAudioMoreThanStereo(self.inputVidFileSpec):
                    if AUDIO_DOWNMIX_FILTER not in self.muteTimeList:
                        self.muteTimeList.insert(0, AUDIO_DOWNMIX_FILTER)

                audio_filtering_active = (not self.subsOnly) and (len(self.muteTimeList) > 0)

                if audio_filtering_active:
                    print("Audio filtering is active. Using multi-step ffmpeg process (Windows path).")

                    temp_raw_audio_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
                    temp_raw_audio_filepath = temp_raw_audio_file.name
                    temp_raw_audio_file.close()
                    temp_files_to_clean.append(temp_raw_audio_filepath)
                    print(f"  Temp raw audio file: {temp_raw_audio_filepath}")

                    ffmpeg_split_audio_cmd = (
                        f"ffmpeg -hide_banner -nostats -loglevel error -y "
                        f"{'' if self.threadsInput is None else ('-threads '+ str(int(self.threadsInput)))} "
                        f"-i \"{self.inputVidFileSpec}\" "
                        f"-map 0:a:{audioStreamOnlyIndex} -c:a pcm_s16le "
                        f"\"{temp_raw_audio_filepath}\""
                    )
                    run_ffmpeg_command(ffmpeg_split_audio_cmd, "Failed to split and decode audio stream (Windows path)")

                    filter_graph_content = ",".join(self.muteTimeList)
                    temp_filter_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt', encoding='utf-8')
                    temp_filter_filepath = temp_filter_file.name
                    temp_filter_file.write(filter_graph_content)
                    temp_filter_file.close()
                    temp_files_to_clean.append(temp_filter_filepath)
                    print(f"  Temp filter script: {temp_filter_filepath}")

                    current_aParams_win = self.aParams
                    default_codec_match_win = re.search(r'-c:a\s+(\S+)', AUDIO_DEFAULT_PARAMS)
                    default_codec_win = default_codec_match_win.group(1) if default_codec_match_win else 'aac'
                    output_audio_codec_win = default_codec_win
                    
                    current_aParams_win = re.sub(r'-c:a:\d+\s+', '-c:a ', current_aParams_win)
                    current_aParams_win = re.sub(r'-codec:a:\d+\s+', '-codec:a ', current_aParams_win)
                    codec_match_win = re.search(r'-(?:c|codec):a\s+(\S+)', current_aParams_win)
                    if codec_match_win:
                        specified_codec_win = codec_match_win.group(1)
                        if specified_codec_win.lower() != 'copy':
                            output_audio_codec_win = specified_codec_win
                            current_aParams_win = re.sub(r'\s*-(?:c|codec):a\s+\S+', '', current_aParams_win).strip()
                        else:
                            current_aParams_win = re.sub(r'\s*-(?:c|codec):a\s+copy', '', current_aParams_win).strip()
                    else:
                        output_audio_codec_win = default_codec_win
                        current_aParams_win = ""

                    filtered_audio_suffix_win = f".{output_audio_codec_win}"
                    if output_audio_codec_win == 'aac': filtered_audio_suffix_win = '.m4a'
                    elif output_audio_codec_win == 'ac3': filtered_audio_suffix_win = '.ac3'
                    elif output_audio_codec_win == 'opus': filtered_audio_suffix_win = '.opus'

                    temp_filtered_audio_file = tempfile.NamedTemporaryFile(suffix=filtered_audio_suffix_win, delete=False)
                    temp_filtered_audio_filepath = temp_filtered_audio_file.name
                    temp_filtered_audio_file.close()
                    temp_files_to_clean.append(temp_filtered_audio_filepath)
                    print(f"  Temp filtered audio file: {temp_filtered_audio_filepath}")
                    print(f"  Using audio codec (Windows path): {output_audio_codec_win}, params: '{current_aParams_win}'")

                    ffmpeg_filter_audio_cmd = (
                        f"ffmpeg -hide_banner -nostats -loglevel error -y "
                        f"-i \"{temp_raw_audio_filepath}\" "
                        f"-filter_script \"{temp_filter_filepath}\" "
                        f"-c:a {output_audio_codec_win} {current_aParams_win} "
                        f"{'' if self.threadsEncoding is None else ('-threads '+ str(int(self.threadsEncoding)))} "
                        f"\"{temp_filtered_audio_filepath}\""
                    )
                    run_ffmpeg_command(ffmpeg_filter_audio_cmd, "Failed to filter audio stream (Windows path)")

                    mux_inputs_list = [f"-i \"{self.inputVidFileSpec}\"", f"-i \"{temp_filtered_audio_filepath}\""]
                    mux_input_idx_counter_win = 2 # Video is 0, Filtered Audio is 1

                    chapter_metadata_map_idx_win = None
                    if self.chapter_file_path:
                        mux_inputs_list.append(f'-i "{self.chapter_file_path}"')
                        chapter_metadata_map_idx_win = mux_input_idx_counter_win
                        mux_input_idx_counter_win +=1

                    subs_input_index_win = mux_input_idx_counter_win # Next available index for subs

                    mux_inputs = " ".join(mux_inputs_list)
                    mux_maps = f"-map 0:v -map 1:a" # Video from input 0, Processed audio from input 1

                    if chapter_metadata_map_idx_win is not None:
                        mux_maps += f" -map_metadata {chapter_metadata_map_idx_win}"

                    audioUnchangedMapList_win = ' '.join(
                        f'-map 0:a:{i}'
                        for i, stream in enumerate(self.actual_audio_streams)
                        if stream.get('index') != self.audioStreamIdx
                    ).strip()
                    if audioUnchangedMapList_win:
                        mux_maps += f" {audioUnchangedMapList_win}"
                    mux_maps += " -map 0:d? -map 0:t?" # Map data and attachment streams from original video
                    mux_codecs = "-c:v copy -c:a copy -c:d copy -c:t copy" # Default codecs

                    if self.embedSubs and os.path.isfile(self.cleanSubsFileSpec):
                        # Subtitles are added as a new input, so their input index needs to be dynamic
                        mux_inputs += f" -i \"{self.cleanSubsFileSpec}\"" # Append to existing mux_inputs string
                        mux_maps += f" -map {subs_input_index_win}:s" # Map the subtitle stream using its dynamic index
                        outFileParts_win = os.path.splitext(self.outputVidFileSpec)
                        subs_codec_win = 'mov_text' if outFileParts_win[1] == '.mp4' else 'srt'
                        mux_codecs += f" -c:s {subs_codec_win} -disposition:s:0 default -metadata:s:s:0 language={self.subsLang}"
                    else:
                        mux_codecs += " -sn" # No subtitles
                    
                    if self.hardCode:
                        if not os.path.isfile(self.cleanSubsFileSpec):
                            print("Warning: Hardcode requested but clean subtitle file not found (Windows path).")
                            if self.reEncodeVideo:
                                mux_codecs = re.sub(r'-c:v\s+copy', self.vParams, mux_codecs)
                        else:
                            if not hasattr(self, 'assSubsFileSpec') or not self.assSubsFileSpec: # Check if already defined
                                self.assSubsFileSpec = os.path.splitext(self.cleanSubsFileSpec)[0] + '.ass'
                            if not os.path.isfile(self.assSubsFileSpec) or os.path.getmtime(self.assSubsFileSpec) < os.path.getmtime(self.cleanSubsFileSpec):
                                print("Converting SRT to ASS for hardcoding (Windows path)...")
                                subConvCmd_win = f"ffmpeg -hide_banner -nostats -loglevel error -y -i \"{self.cleanSubsFileSpec}\" \"{self.assSubsFileSpec}\""
                                run_ffmpeg_command(subConvCmd_win, "Failed to convert subtitles to ASS format (Windows path)")
                            else:
                                print("Using existing ASS file for hardcoding (Windows path).")
                            
                            if os.path.isfile(self.assSubsFileSpec):
                                print("Applying hardcoded subtitles (Windows path)...")
                                video_encode_params_win = self.vParams
                                escaped_ass_path_win = self.assSubsFileSpec.replace('\\', '/').replace(':', '\\\\:') # Ensure proper escaping
                                if "-c:v copy" in mux_codecs:
                                     mux_codecs = mux_codecs.replace('-c:v copy', f"{video_encode_params_win} -vf \"ass='{escaped_ass_path_win}'\"")
                                else:
                                     mux_codecs += f" -vf \"ass='{escaped_ass_path_win}'\"" # Should append if -c:v copy was already replaced
                            else:
                                print("Warning: Failed to find or create ASS file for hardcoding (Windows path).")
                                if self.reEncodeVideo:
                                    mux_codecs = re.sub(r'-c:v\s+copy', self.vParams, mux_codecs)
                    elif self.reEncodeVideo:
                        mux_codecs = re.sub(r'-c:v\s+copy', self.vParams, mux_codecs)

                    ffmpeg_mux_cmd = (
                        f"ffmpeg -hide_banner -nostats -loglevel error -y "
                        f"{mux_inputs} "
                        f"{mux_maps} {mux_codecs} "
                        f"{'' if self.threadsEncoding is None else ('-threads '+ str(int(self.threadsEncoding)))} "
                        f"\"{self.outputVidFileSpec}\""
                    )
                    run_ffmpeg_command(ffmpeg_mux_cmd, "Failed to mux final video (Windows path)")

                else: # No audio filtering, but still using multi-step logic for other reasons (e.g. reEncodeVideo with --win)
                    print("Audio filtering not active, but using multi-step structure for other processing (Windows path).")
                    # This branch will be similar to the original single-step, but within the try/finally for consistency
                    # if only video re-encode or subtitle embedding is needed without audio filtering.

                    videoArgs_win = "-c:v copy"
                    if self.reEncodeVideo or self.hardCode:
                        if self.hardCode:
                            if not os.path.isfile(self.cleanSubsFileSpec):
                                print("Warning: Hardcode requested but clean subtitle file not found (Windows path, no audio filter).")
                                videoArgs_win = self.vParams
                            else:
                                if not hasattr(self, 'assSubsFileSpec') or not self.assSubsFileSpec:
                                    self.assSubsFileSpec = os.path.splitext(self.cleanSubsFileSpec)[0] + '.ass'
                                if not os.path.isfile(self.assSubsFileSpec) or os.path.getmtime(self.assSubsFileSpec) < os.path.getmtime(self.cleanSubsFileSpec):
                                    subConvCmd_win_nf = f"ffmpeg -hide_banner -nostats -loglevel error -y -i \"{self.cleanSubsFileSpec}\" \"{self.assSubsFileSpec}\""
                                    run_ffmpeg_command(subConvCmd_win_nf, "Failed to convert subtitles to ASS (Windows path, no audio filter)")
                                if os.path.isfile(self.assSubsFileSpec):
                                     escaped_ass_path_win_nf = self.assSubsFileSpec.replace('\\', '/').replace(':', '\\\\:')
                                     videoArgs_win = f"{self.vParams} -vf \"ass='{escaped_ass_path_win_nf}'\""
                                else:
                                     print("Warning: ASS file not created for hardcoding (Windows path, no audio filter).")
                                     videoArgs_win = self.vParams # Fallback to re-encode
                        else: # Just reEncodeVideo
                            videoArgs_win = self.vParams
                    
                    # Audio arguments: target the selected stream.
                    # In this "no audio filtering" Windows path, we are still re-encoding audio if self.reEncodeAudio is true,
                    # or copying if not. The self.aParams should be respected.
                    # Ensure aParams correctly targets the 0-based index of the chosen audio stream.
                    audioArgs_win = re.sub(r"-c:a(?::\d+)?(\s+)", rf"-c:a:{str(audioStreamOnlyIndex)}\1", self.aParams, 1)
                    if not re.search(r"-c:a:" + str(audioStreamOnlyIndex), audioArgs_win):
                         audioArgs_win = re.sub(r"-c:a(\s+)", rf"-c:a:{str(audioStreamOnlyIndex)}\1", audioArgs_win, 1)

                    subsArgsInput_win = ""
                    subsArgsEmbed_win = "-sn"
                    mapArgs_win = f"-map 0:v -map 0:a:{audioStreamOnlyIndex}" # Map selected audio stream

                    # Map other audio streams to be copied
                    audioUnchangedMapList_win_nf = ' '.join(
                        f'-map 0:a:{i}'
                        for i, stream in enumerate(self.actual_audio_streams)
                        if stream.get('index') != self.audioStreamIdx # Exclude the main audio stream, it's already mapped
                    ).strip()
                    if audioUnchangedMapList_win_nf:
                        mapArgs_win += f" {audioUnchangedMapList_win_nf}"


                    if self.embedSubs and os.path.isfile(self.cleanSubsFileSpec):
                        subsArgsInput_win = f" -i \"{self.cleanSubsFileSpec}\""
                        mapArgs_win += " -map 1:s" 
                        outFileParts_win_nf = os.path.splitext(self.outputVidFileSpec)
                        subs_codec_win_nf = 'mov_text' if outFileParts_win_nf[1] == '.mp4' else 'srt'
                        subsArgsEmbed_win = f"-c:s {subs_codec_win_nf} -disposition:s:0 default -metadata:s:s:0 language={self.subsLang}"

                    ffmpeg_cmd_single_win = (
                        f"ffmpeg -hide_banner -nostats -loglevel error -y "
                        f"{'' if self.threadsInput is None else ('-threads '+ str(int(self.threadsInput)))} "
                        f"-i \"{self.inputVidFileSpec}\" {subsArgsInput_win} "
                        f"{mapArgs_win} "
                        f"{videoArgs_win} {audioArgs_win} {subsArgsEmbed_win} "
                        f"{'' if self.threadsEncoding is None else ('-threads '+ str(int(self.threadsEncoding)))} "
                        f"\"{self.outputVidFileSpec}\""
                    )
                    run_ffmpeg_command(ffmpeg_cmd_single_win, "Failed to process video (Windows path, no audio filter)")

                if not os.path.isfile(self.outputVidFileSpec):
                    raise ValueError(f'Output file {self.outputVidFileSpec} was not created successfully (Windows path).')
                else:
                    print(f"Successfully created output file: {self.outputVidFileSpec} (Windows path)")

            finally:
                if temp_filter_filepath and os.path.exists(temp_filter_filepath):
                    try:
                        os.remove(temp_filter_filepath)
                        print(f"Cleaned up temporary filter script: {temp_filter_filepath} (Windows path)")
                    except OSError as e:
                        print(f"Warning: Could not delete temporary filter file {temp_filter_filepath}: {e} (Windows path)")
                
                print(f"Cleaning up {len(temp_files_to_clean)} temporary file(s) (Windows path)...")
                for temp_file in temp_files_to_clean:
                    if temp_file and os.path.exists(temp_file):
                        try:
                            os.remove(temp_file)
                            print(f"  Cleaned up: {temp_file} (Windows path)")
                        except OSError as e:
                            print(f"  Warning: Could not delete temporary file {temp_file}: {e} (Windows path)")


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
        dest='subsLang', # Changed dest to subsLang
        help=f'subtitle language (default: {SUBTITLE_DEFAULT_LANG}) (append :<index> to force specific stream index, e.g. eng:2)', # Updated help
        default=SUBTITLE_DEFAULT_LANG,
        metavar='<language>',
    )
    parser.add_argument(
        '-p', '--pad',
        dest='swearsPadSec', # Changed dest to swearsPadSec
        help='pad (seconds) around profanity (default: 0.0)', # Updated help
        metavar='<seconds>', # Changed metavar
        type=float,
        default=0.0
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
        help='generate JSON file detailing edits (default: false)', # Updated help
        dest='jsonDump', # Changed dest to jsonDump
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
        dest='vParams',
        help=f'Video parameters for ffmpeg (only if re-encoding, default: {VIDEO_DEFAULT_PARAMS}) (prefix with base64: if needed)', # Updated help
        default=VIDEO_DEFAULT_PARAMS,
        metavar='<ffmpeg video args>', # Added metavar
    )
    parser.add_argument(
        '-a', '--audio-params',
        dest='aParams',
        help=f'Audio parameters for ffmpeg (default: {AUDIO_DEFAULT_PARAMS}) (prefix with base64: if needed)', # Updated help
        default=AUDIO_DEFAULT_PARAMS,
        metavar='<ffmpeg audio args>', # Added metavar
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
    parser.add_argument(
        '--chapter',
        help='Create chapter markers for muted segments',
        action='store_true',
        default=False,
        dest="chapter_markers"
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
        chapter_markers=False, # Default chapter_markers to False
    )
    args = parser.parse_args()

    # --- Logic now unified, VidCleaner handles use_win_method ---
    # The subprocess call to cleanvidwin.py has been removed.
    # VidCleaner class itself will use self.use_win_method to determine the ffmpeg processing path.

    if args.use_win_method:
        print("Windows compatibility mode requested (--win). Internal multi-step logic will be used.")
    else:
        print("Using standard processing method. Use --win for Windows compatibility mode if issues arise on Windows.")

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
    # lang variable now directly uses args.subsLang due to dest change
    plexFile = args.plexAutoSkipJson
    if inFile:
        inFileParts = os.path.splitext(inFile)
        if not outFile:
            outFile = inFileParts[0] + "_clean" + inFileParts[1]
        if not subsFile:
            subsFile = GetSubtitles(inFile, args.subsLang, args.offline) # Use args.subsLang
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
             args.swearsPadSec, # Changed from args.pad
             args.embedSubs,
             args.fullSubs,
             args.subsOnly,
             args.edl,
             args.jsonDump, # Changed from args.json
             args.subsLang, # Changed from lang
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
             args.use_win_method, # Pass the flag
             args.chapter_markers, # Pass chapter_markers
        )
        cleaner.CreateCleanSubAndMuteList()
        # --- Wrap the potentially failing call ---
        cleaner.MultiplexCleanVideo()
        print("Processing completed successfully.") # Generic success message

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
