#!/usr/bin/env python3

import argparse
import base64
import chardet
import codecs
import errno
import json
import os
import shutil
import sys
import re
import pysrt
import delegator
import tempfile # Added for temporary files
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
        if os.path.isfile(self.assSubsFileSpec) and not self.hardCode: # Keep ASS if hardcoding succeeded
             try:
                 os.remove(self.assSubsFileSpec)
             except OSError:
                 pass # Ignore error if file is gone

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
            # Build filter graph components for audio filtering
            # Using afade for smoother transitions (original logic)
            self.muteTimeList.append(
                "afade=enable='between(t,"
                + format(lineStart, '.3f')
                + ","
                + format(lineEnd, '.3f')
                + ")':t=out:st="
                + format(lineStart, '.3f')
                + ":d=10ms" # Mute section (fade out)
            )
            self.muteTimeList.append(
                "afade=enable='between(t,"
                + format(lineEnd, '.3f')
                + ","
                + format(lineStartPeek, '.3f') # Use peek for fade-in start
                + ")':t=in:st="
                + format(lineEnd, '.3f')
                + ":d=10ms" # Unmute section (fade in)
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
        temp_files_to_clean = [] # List to hold paths of temp files for cleanup
        temp_filter_filepath = None # Keep this separate as it's handled slightly differently
        audioStreams = None # Define audioStreams in the broader scope

        try:
            # Determine if video processing is needed (existing logic)
            needs_processing = (
                self.reEncodeVideo
                or self.reEncodeAudio
                or self.hardCode
                or self.embedSubs
                or ((not self.subsOnly) and (len(self.muteTimeList) > 0)) # Check original muteTimeList length
            )

            if not needs_processing:
                self.unalteredVideo = True
                print("No video/audio processing required based on options.")
                return # Exit early if no processing needed

            # --- Determine audio stream index ---
            audioStreamOnlyIndex = 0 # Default to first stream if index not specified/found
            audioStreams = GetAudioStreamsInfo(self.inputVidFileSpec)
            if not audioStreams or 'streams' not in audioStreams or not audioStreams['streams']:
                 raise ValueError(f'Could not determine audio streams in {self.inputVidFileSpec}')

            actual_streams = audioStreams['streams']
            if self.audioStreamIdx is None:
                if len(actual_streams) == 1:
                    if 'index' in actual_streams[0]:
                        self.audioStreamIdx = actual_streams[0]['index']
                        # Find the 0-based index for mapping
                        audioStreamOnlyIndex = next((i for i, s in enumerate(actual_streams) if s.get('index') == self.audioStreamIdx), 0)
                    else:
                        raise ValueError(f'Could not determine audio stream index for {self.inputVidFileSpec}')
                else:
                    raise ValueError(
                        f'Multiple audio streams ({len(actual_streams)} found), specify audio stream index with --audio-stream-index'
                    )
            elif any(stream.get('index', -1) == self.audioStreamIdx for stream in actual_streams):
                 # Find the 0-based index for mapping
                 audioStreamOnlyIndex = next((i for i, s in enumerate(actual_streams) if s.get('index') == self.audioStreamIdx), 0)
            else:
                raise ValueError(
                    f'Audio stream index {self.audioStreamIdx} is invalid for {self.inputVidFileSpec}'
                )

            # Apply stream index to aParams if needed (original logic modified) - This is handled later in muxing if needed
            print(f"Selected audio stream: Input Index={self.audioStreamIdx}, FFmpeg Map Index=0:a:{audioStreamOnlyIndex}")
            # Store the list of actual audio streams for later use in mapping
            self.actual_audio_streams = actual_streams


            # --- Determine if audio filtering is needed ---
            # Note: muteTimeList is populated in CreateCleanSubAndMuteList
            if self.aDownmix and HasAudioMoreThanStereo(self.inputVidFileSpec):
                # Prepend downmix filter if needed *before* checking length
                if AUDIO_DOWNMIX_FILTER not in self.muteTimeList: # Avoid duplicates
                    self.muteTimeList.insert(0, AUDIO_DOWNMIX_FILTER)

            audio_filtering_active = (not self.subsOnly) and (len(self.muteTimeList) > 0)

            # --- Main Processing Logic ---
            if audio_filtering_active:
                print("Audio filtering is active. Using multi-step ffmpeg process.")

                # == Step 1: Extract Target Audio ==
                print("Step 1: Extracting target audio stream...")

                # Create temporary file for raw audio
                temp_raw_audio_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
                temp_raw_audio_filepath = temp_raw_audio_file.name
                temp_raw_audio_file.close()
                temp_files_to_clean.append(temp_raw_audio_filepath) # Only add audio file now
                print(f"  Temp raw audio file: {temp_raw_audio_filepath}")

                # Extract and decode audio to WAV
                ffmpeg_split_audio_cmd = (
                    f"ffmpeg -hide_banner -nostats -loglevel error -y "
                    f"{'' if self.threadsInput is None else ('-threads '+ str(int(self.threadsInput)))} "
                    f"-i \"{self.inputVidFileSpec}\" "
                    f"-map 0:a:{audioStreamOnlyIndex} -c:a pcm_s16le " # Decode to WAV
                    f"\"{temp_raw_audio_filepath}\""
                )
                run_ffmpeg_command(ffmpeg_split_audio_cmd, "Failed to split and decode audio stream")

                # == Step 2: Filter Audio ==
                print("Step 2: Filtering audio stream...")

                # Create filter script file
                filter_graph_content = ",".join(self.muteTimeList)
                temp_filter_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt', encoding='utf-8')
                temp_filter_filepath = temp_filter_file.name # Store path for cleanup
                # Filtergraph for single WAV input doesn't need stream specifiers like [0:a:0]
                # It implicitly operates on the input stream.
                temp_filter_file.write(f"{filter_graph_content}")
                temp_filter_file.close()
                temp_files_to_clean.append(temp_filter_filepath) # Add filter script for cleanup
                print(f"  Temp filter script: {temp_filter_filepath}")


                # Determine output audio parameters (remove stream specifiers if present)
                # Use default codec if 'copy' is specified, otherwise use provided params
                current_aParams = self.aParams
                default_codec_match = re.search(r'-c:a\s+(\S+)', AUDIO_DEFAULT_PARAMS)
                default_codec = default_codec_match.group(1) if default_codec_match else 'aac'
                output_audio_codec = default_codec # Default to AAC

                # Try to extract codec and other params from self.aParams
                # Remove any stream specifiers first
                current_aParams = re.sub(r'-c:a:\d+\s+', '-c:a ', current_aParams)
                current_aParams = re.sub(r'-codec:a:\d+\s+', '-codec:a ', current_aParams)

                codec_match = re.search(r'-(?:c|codec):a\s+(\S+)', current_aParams)
                if codec_match:
                    specified_codec = codec_match.group(1)
                    if specified_codec.lower() != 'copy':
                        output_audio_codec = specified_codec
                        # Remove the codec part to keep other params like bitrate, etc.
                        current_aParams = re.sub(r'\s*-(?:c|codec):a\s+\S+', '', current_aParams).strip()
                    else:
                        # If 'copy' was specified, just use default codec and ignore other params in self.aParams for this step
                         current_aParams = re.sub(r'\s*-(?:c|codec):a\s+copy', '', current_aParams).strip()
                else:
                    # No codec specified in aParams, use default
                    output_audio_codec = default_codec
                    current_aParams = "" # Clear params if only default codec is used

                # Determine filtered audio file extension based on codec
                filtered_audio_suffix = f".{output_audio_codec}"
                if output_audio_codec == 'aac': filtered_audio_suffix = '.m4a'
                elif output_audio_codec == 'ac3': filtered_audio_suffix = '.ac3'
                elif output_audio_codec == 'opus': filtered_audio_suffix = '.opus'
                # Add more mappings if needed

                temp_filtered_audio_file = tempfile.NamedTemporaryFile(suffix=filtered_audio_suffix, delete=False)
                temp_filtered_audio_filepath = temp_filtered_audio_file.name
                temp_filtered_audio_file.close()
                temp_files_to_clean.append(temp_filtered_audio_filepath)
                print(f"  Temp filtered audio file: {temp_filtered_audio_filepath}")
                print(f"  Using audio codec: {output_audio_codec}, params: '{current_aParams}'")


                # Construct filter command
                ffmpeg_filter_audio_cmd = (
                    f"ffmpeg -hide_banner -nostats -loglevel error -y "
                    f"-i \"{temp_raw_audio_filepath}\" "
                    f"-filter_script \"{temp_filter_filepath}\" "
                    f"-c:a {output_audio_codec} {current_aParams} " # Apply codec and remaining params
                    f"{'' if self.threadsEncoding is None else ('-threads '+ str(int(self.threadsEncoding)))} "
                    f"\"{temp_filtered_audio_filepath}\""
                )
                run_ffmpeg_command(ffmpeg_filter_audio_cmd, "Failed to filter audio stream")

                # == Step 3: Mux Streams ==
                print("Step 3: Muxing final video...")

                # --- Construct Mux Command ---
                # Inputs: Original Video (0), Filtered Audio (1), Optional Clean Subs (2)
                mux_inputs = f"-i \"{self.inputVidFileSpec}\" -i \"{temp_filtered_audio_filepath}\""
                subs_input_index = 2 # Starts at 2 if subs are added

                # Mapping: Video, Filtered Audio, Other Audio, Optional Subs/Data
                mux_maps = "-map 0:v -map 1:a" # Map all video from input 0, filtered audio from input 1
                # Map other audio streams from input 0 (original video)
                audioUnchangedMapList = ' '.join(
                    f'-map 0:a:{i}'
                    for i, stream in enumerate(self.actual_audio_streams) # Use stored stream list
                    if stream.get('index') != self.audioStreamIdx # Exclude the stream we filtered
                )
                if audioUnchangedMapList:
                    mux_maps += f" {audioUnchangedMapList}"
                # Optionally map data and attachments from original input
                mux_maps += " -map 0:d? -map 0:t?"

                # Codecs: Copy video, copy filtered audio, copy other audio, handle subs
                mux_codecs = "-c:v copy -c:a copy -c:d copy -c:t copy" # Start with copy for all mapped streams

                # Handle subtitle embedding/copying/excluding
                if self.embedSubs and os.path.isfile(self.cleanSubsFileSpec):
                    mux_inputs += f" -i \"{self.cleanSubsFileSpec}\""
                    mux_maps += f" -map {subs_input_index}:s" # Map subtitles from the new input
                    outFileParts = os.path.splitext(self.outputVidFileSpec)
                    subs_codec = 'mov_text' if outFileParts[1] == '.mp4' else 'srt'
                    # Add subtitle codec, disposition, metadata.
                    mux_codecs += f" -c:s {subs_codec} -disposition:s:0 default -metadata:s:s:0 language={self.subsLang}"
                else:
                    # If not embedding external subs, exclude all subs from original input
                    mux_codecs += " -sn" # Explicitly remove subs

                # Handle hardcoding (overrides video copy)
                if self.hardCode:
                    if not os.path.isfile(self.cleanSubsFileSpec):
                        print("Warning: Hardcode requested but clean subtitle file not found.")
                        # If hardcoding fails, we still need to re-encode if reEncodeVideo was true
                        if self.reEncodeVideo:
                             mux_codecs = re.sub(r'-c:v\s+copy', self.vParams, mux_codecs)
                    else:
                        # Convert SRT to ASS if needed
                        if not hasattr(self, 'assSubsFileSpec') or not self.assSubsFileSpec:
                            self.assSubsFileSpec = os.path.splitext(self.cleanSubsFileSpec)[0] + '.ass'
                        if not os.path.isfile(self.assSubsFileSpec) or os.path.getmtime(self.assSubsFileSpec) < os.path.getmtime(self.cleanSubsFileSpec):
                            print("Converting SRT to ASS for hardcoding...")
                            subConvCmd = f"ffmpeg -hide_banner -nostats -loglevel error -y -i \"{self.cleanSubsFileSpec}\" \"{self.assSubsFileSpec}\""
                            run_ffmpeg_command(subConvCmd, "Failed to convert subtitles to ASS format")
                        else:
                            print("Using existing ASS file for hardcoding.")

                        if os.path.isfile(self.assSubsFileSpec):
                            print("Applying hardcoded subtitles...")
                            # Replace video codec copy with re-encode + filter
                            video_encode_params = self.vParams # Use user/default encode params
                            escaped_ass_path = self.assSubsFileSpec.replace('\\', '/').replace(':', '\\\\:')
                            # Ensure we replace -c:v copy, even if other codecs were added
                            if "-c:v copy" in mux_codecs:
                                mux_codecs = mux_codecs.replace('-c:v copy', f"{video_encode_params} -vf \"ass='{escaped_ass_path}'\"")
                            else: # If -c:v copy was already replaced (e.g., by reEncodeVideo), add the filter
                                mux_codecs += f" -vf \"ass='{escaped_ass_path}'\""
                        else:
                            print("Warning: Failed to find or create ASS file for hardcoding.")
                            # Fallback to re-encoding if requested, even without subs
                            if self.reEncodeVideo:
                                 mux_codecs = re.sub(r'-c:v\s+copy', self.vParams, mux_codecs)
                elif self.reEncodeVideo: # Handle reEncodeVideo flag even if not hardcoding
                     mux_codecs = re.sub(r'-c:v\s+copy', self.vParams, mux_codecs)


                # Construct the final mux command
                ffmpeg_mux_cmd = (
                    f"ffmpeg -hide_banner -nostats -loglevel error -y "
                    f"{mux_inputs} "
                    f"{mux_maps} {mux_codecs} "
                    f"{'' if self.threadsEncoding is None else ('-threads '+ str(int(self.threadsEncoding)))} "
                    f"\"{self.outputVidFileSpec}\""
                )
                run_ffmpeg_command(ffmpeg_mux_cmd, "Failed to mux final video")

            else:
                # --- Original Logic (Simplified for no filtering) ---
                print("Audio filtering not active. Using single-step ffmpeg process.")

                # Determine video args (copy or re-encode/hardcode)
                videoArgs = "-c:v copy" # Default
                if self.reEncodeVideo or self.hardCode:
                    if self.hardCode:
                        if not os.path.isfile(self.cleanSubsFileSpec):
                             print("Warning: Hardcode requested but clean subtitle file not found.")
                             videoArgs = self.vParams # Fallback to re-encode without subs
                        else:
                             # Convert SRT to ASS if needed
                             if not hasattr(self, 'assSubsFileSpec') or not self.assSubsFileSpec:
                                 self.assSubsFileSpec = os.path.splitext(self.cleanSubsFileSpec)[0] + '.ass'
                             if not os.path.isfile(self.assSubsFileSpec) or os.path.getmtime(self.assSubsFileSpec) < os.path.getmtime(self.cleanSubsFileSpec):
                                 print("Converting SRT to ASS for hardcoding...")
                                 subConvCmd = f"ffmpeg -hide_banner -nostats -loglevel error -y -i \"{self.cleanSubsFileSpec}\" \"{self.assSubsFileSpec}\""
                                 run_ffmpeg_command(subConvCmd, "Failed to convert subtitles to ASS format")
                             else:
                                 print("Using existing ASS file for hardcoding.")

                             if os.path.isfile(self.assSubsFileSpec):
                                 escaped_ass_path = self.assSubsFileSpec.replace('\\', '/').replace(':', '\\\\:')
                                 videoArgs = f"{self.vParams} -vf \"ass='{escaped_ass_path}'\""
                             else:
                                 print("Warning: Failed to find or create ASS file for hardcoding. Re-encoding video without subs.")
                                 videoArgs = self.vParams
                    else: # Just reEncodeVideo
                        videoArgs = self.vParams
                # else: videoArgs remains "-c:v copy"

                # Determine audio args (use self.aParams, ensure stream specifier for target stream)
                # Remove existing stream specifiers and add the correct one
                audioArgs = re.sub(r'-(?:c|codec):a:\d+\s+', f'-c:a:{audioStreamOnlyIndex} ', self.aParams)
                audioArgs = re.sub(r'-c:a\s+', f'-c:a:{audioStreamOnlyIndex} ', audioArgs) # Ensure specifier if only -c:a was present
                # If no -c:a was present at all, add it with the specifier
                if f'-c:a:{audioStreamOnlyIndex}' not in audioArgs and f'-codec:a:{audioStreamOnlyIndex}' not in audioArgs:
                     # Extract codec from default if possible, fallback to copy
                     default_codec_match = re.search(r'-c:a\s+(\S+)', AUDIO_DEFAULT_PARAMS)
                     codec_to_use = default_codec_match.group(1) if default_codec_match else 'copy'
                     audioArgs += f" -c:a:{audioStreamOnlyIndex} {codec_to_use}"


                # Handle subtitle embedding
                subsArgsInput = ""
                subsArgsEmbed = "-sn" # Default to no subs
                # Map target audio stream first
                mapArgs = f"-map 0:v -map 0:a:{audioStreamOnlyIndex}"
                # TODO: Add back mapping for other audio streams if needed (audioUnchangedMapList logic)

                if self.embedSubs and os.path.isfile(self.cleanSubsFileSpec):
                     subsArgsInput = f" -i \"{self.cleanSubsFileSpec}\""
                     mapArgs += " -map 1:s" # Map subs from input 1
                     outFileParts = os.path.splitext(self.outputVidFileSpec)
                     subs_codec = 'mov_text' if outFileParts[1] == '.mp4' else 'srt'
                     subsArgsEmbed = f"-c:s {subs_codec} -disposition:s:0 default -metadata:s:s:0 language={self.subsLang}"
                # else: subsArgsEmbed remains "-sn"


                # Construct the single ffmpeg command
                ffmpeg_cmd_single = (
                     f"ffmpeg -hide_banner -nostats -loglevel error -y "
                     f"{'' if self.threadsInput is None else ('-threads '+ str(int(self.threadsInput)))} "
                     f"-i \"{self.inputVidFileSpec}\" {subsArgsInput} "
                     f"{mapArgs} " # Map video, target audio, and potentially subs
                     f"{videoArgs} {audioArgs} {subsArgsEmbed} " # Video codec, audio codec, subs codec/params or -sn
                     f"{'' if self.threadsEncoding is None else ('-threads '+ str(int(self.threadsEncoding)))} "
                     f"\"{self.outputVidFileSpec}\""
                )
                run_ffmpeg_command(ffmpeg_cmd_single, "Failed to process video (single step)")


            # Final check if output file exists
            if not os.path.isfile(self.outputVidFileSpec):
                 raise ValueError(f'Output file {self.outputVidFileSpec} was not created successfully.')
            else:
                 print(f"Successfully created output file: {self.outputVidFileSpec}")

        finally:
            # Clean up the temporary filter script file
            if temp_filter_filepath and os.path.exists(temp_filter_filepath):
                try:
                    os.remove(temp_filter_filepath)
                    print(f"Cleaned up temporary filter script: {temp_filter_filepath}")
                except OSError as e:
                    print(f"Warning: Could not delete temporary filter file {temp_filter_filepath}: {e}")

            # Clean up other temporary files (now only includes audio and filter script)
            print(f"Cleaning up {len(temp_files_to_clean)} temporary file(s)...")
            for temp_file in temp_files_to_clean:
                if temp_file and os.path.exists(temp_file): # Add check if temp_file is not None
                    try:
                        os.remove(temp_file)
                        print(f"  Cleaned up: {temp_file}")
                    except OSError as e:
                        print(f"  Warning: Could not delete temporary file {temp_file}: {e}")

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
        '--swears',
        help='pipe-delimited swears file (default: included swears.txt)',
        default=os.path.join(__script_location__, 'swears.txt'),
        metavar='<swears file>',
    )
    parser.add_argument(
        '--swears-pad-sec',
        help='seconds to pad swears (default: 0.0)',
        type=float,
        default=0.0,
        metavar='<pad seconds>',
        dest="swearsPadSec",
    )
    parser.add_argument(
        '--embed-subs', help='embed cleaned subtitle stream (default: false)', action='store_true', dest="embedSubs"
    )
    parser.add_argument(
        '--full-subs',
        help='output full subtitle file with swears replaced (default: false, only outputs swear lines)',
        action='store_true',
        dest="fullSubs",
    )
    parser.add_argument(
        '--subs-only',
        help='only generate subtitle file, do not process video (default: false)',
        action='store_true',
        dest="subsOnly",
    )
    parser.add_argument(
        '--edl',
        help='generate EDL file for video editors (also implies --subs-only) (default: false)',
        action='store_true',
    )
    parser.add_argument(
        '--json',
        help='generate JSON file detailing edits (default: false)',
        action='store_true',
        dest="jsonDump",
    )
    parser.add_argument(
        '--subs-lang',
        help='subtitle language (default: eng) (append :<index> to force specific stream index, e.g. eng:2)',
        default=SUBTITLE_DEFAULT_LANG,
        metavar='<language>',
        dest="subsLang",
    )
    parser.add_argument(
        '--re-encode-video',
        help='force re-encode of video stream (default: false)',
        action='store_true',
        dest="reEncodeVideo",
    )
    parser.add_argument(
        '--re-encode-audio',
        help='force re-encode of audio stream (default: false)',
        action='store_true',
        dest="reEncodeAudio",
    )
    parser.add_argument(
        '--hard-code',
        help='hard-code (burn) cleaned subtitles into video stream (implies --re-encode-video) (default: false)',
        action='store_true',
        dest="hardCode",
    )
    parser.add_argument(
        '--vparams',
        help=f'video encoding parameters (default: {VIDEO_DEFAULT_PARAMS}) (prefix with base64: if needed)',
        default=VIDEO_DEFAULT_PARAMS,
        metavar='<ffmpeg video args>',
    )
    parser.add_argument(
        '--audio-stream-index',
        help='audio stream index to process (default: auto-detect if only one stream)',
        type=int,
        default=None,
        metavar='<index>',
        dest="audioStreamIdx",
    )
    parser.add_argument(
        '--aparams',
        help=f'audio encoding parameters (default: {AUDIO_DEFAULT_PARAMS}) (prefix with base64: if needed)',
        default=AUDIO_DEFAULT_PARAMS,
        metavar='<ffmpeg audio args>',
    )
    parser.add_argument(
        '--audio-downmix',
        help='downmix audio to stereo if input has more channels (default: false)',
        action='store_true',
        dest="aDownmix",
    )
    parser.add_argument(
        '--threads-input',
        help='set threads for ffmpeg input processing (default: auto)',
        type=int,
        default=None,
        metavar='<threads>',
        dest="threadsInput",
    )
    parser.add_argument(
        '--threads-encoding',
        help='set threads for ffmpeg output encoding (default: auto)',
        type=int,
        default=None,
        metavar='<threads>',
        dest="threadsEncoding",
    )
    parser.add_argument(
        '--offline', help='do not attempt to download subtitles (default: false)', action='store_true'
    )
    parser.add_argument(
        '--alass',
        help='Attempt to synchronize subtitles with video using alass before cleaning (requires alass in PATH)',
        action='store_true',
        dest="use_alass"
    )

    args = parser.parse_args()
    # Add default for alass if not already present (though argparse handles this)
    if not hasattr(args, 'use_alass'):
        args.use_alass = False

    if args.hardCode:
        args.reEncodeVideo = True

    if not args.output:
        inParts = os.path.splitext(args.input)
        args.output = inParts[0] + "_clean" + inParts[1]

    if not args.subs:
        args.subs = GetSubtitles(args.input, args.subsLang, args.offline)

    # --- Optional Alass Synchronization ---
    alass_temp_srt_file = None # To track temp file for cleanup
    if args.use_alass:
        # Use args.input and args.subs directly here
        if args.subs and os.path.isfile(args.subs):
            print(f"Attempting subtitle synchronization with alass for: {args.subs}")
            try:
                # Create a temporary file for alass output
                temp_f = tempfile.NamedTemporaryFile(suffix=".srt", delete=False, mode='w', encoding='utf-8')
                alass_temp_srt_file = temp_f.name
                temp_f.close() # Close handle for Windows compatibility
                print(f"  Using temporary file for alass output: {alass_temp_srt_file}")

                alass_cmd = f'alass "{args.input}" "{args.subs}" "{alass_temp_srt_file}"'
                print(f"  Executing: {alass_cmd}")
                # Use delegator.run consistent with the rest of the script
                alass_result = delegator.run(alass_cmd, block=True)

                if alass_result.return_code == 0 and os.path.isfile(alass_temp_srt_file) and os.path.getsize(alass_temp_srt_file) > 0:
                    print(f"  Alass synchronization successful. Using synced subtitles: {alass_temp_srt_file}")
                    args.subs = alass_temp_srt_file # Update args.subs to point to the synced version
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

    # Instantiate the cleaner and run processing within try/finally for cleanup
    try:
        cleaner = VidCleaner(
            args.input,
            args.subs, # This will be the original or the alass temp file
            args.output,
            args.subsOut,
            args.swears,
            args.swearsPadSec,
            args.embedSubs,
            args.fullSubs,
            args.subsOnly,
            args.edl,
            args.jsonDump,
            args.subsLang,
            args.reEncodeVideo,
            args.reEncodeAudio,
            args.hardCode,
            args.vparams,
            args.audioStreamIdx,
            args.aparams,
            args.aDownmix,
            args.threadsInput,
            args.threadsEncoding,
            args.plexAutoSkipJson,
            args.plexAutoSkipId,
        )
        cleaner.CreateCleanSubAndMuteList()
        cleaner.MultiplexCleanVideo()
        print("Processing completed successfully using Windows compatibility method.") # Added context
    except Exception as e:
         # Add more specific error handling if needed, or re-raise
         print(f"\n--- Processing Error (Windows Method) ---", file=sys.stderr)
         print(f"Error details: {e}", file=sys.stderr)
         # Consider printing traceback for unexpected errors
         # import traceback
         # traceback.print_exc(file=sys.stderr)
         sys.exit(1) # Exit with error code
    finally:
        # --- Cleanup Alass Temp File ---
        if alass_temp_srt_file and os.path.exists(alass_temp_srt_file):
            print(f"Cleaning up temporary alass file: {alass_temp_srt_file}")
            os.remove(alass_temp_srt_file)


if __name__ == "__main__":
    RunCleanvid()
