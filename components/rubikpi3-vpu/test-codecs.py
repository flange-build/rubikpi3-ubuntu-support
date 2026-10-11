#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Test VPU encode/decode with explicit hardware codecs and pixel comparison."""
import argparse
import json
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="directory for generated videos and logs")
    parser.add_argument("--size", choices=("1280x720", "1920x1080"), default="1280x720")
    parser.add_argument("--frames", type=int, default=90)
    args = parser.parse_args()
    if not 1 <= args.frames <= 900:
        parser.error("frames must be between 1 and 900")
    width, height = map(int, args.size.split("x"))
    out = args.directory.resolve()
    out.mkdir(parents=True, exist_ok=True)

    def run(name, command):
        log_path = out / (name + ".log")
        with log_path.open("w") as log:
            try:
                result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=90)
            except subprocess.TimeoutExpired:
                raise SystemExit(f"{name}: timed out; see {log_path}")
        if result.returncode:
            raise SystemExit(f"{name}: exit {result.returncode}; see {log_path}")

    def hashes(path):
        return [line.split(",")[-1].strip() for line in path.read_text().splitlines()
                if line and not line.startswith("#")]

    results = []
    for codec, encoder in (("h264", "v4l2h264enc"), ("hevc", "v4l2h265enc")):
        stream = out / ("encoded." + codec)
        # Venus defaults to level 1. Explicitly negotiate a level suitable for
        # 1080p30; the tested firmware faults on unconstrained 1080p encoding.
        controls = "controls,video_bitrate=6000000," + ("h264_level=12" if codec == "h264" else "hevc_level=6")
        caps = "video/x-h264,profile=high,level=(string)4.1" if codec == "h264" else "video/x-h265,profile=main,level=(string)4.1"
        # Codec elements choose their own encoder device. Node numbers can
        # reverse across boots; the GStreamer 'device' property is read-only.
        run(codec + "-encode", [
            "gst-launch-1.0", "-e", "videotestsrc", f"num-buffers={args.frames}", "!",
            f"video/x-raw,format=NV12,width={width},height={height},framerate=30/1", "!",
            encoder, f"extra-controls={controls}", "!", caps, "!", "filesink", f"location={stream}",
        ])
        run(codec + "-probe", [
            "ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
            "-show_entries", "stream=codec_name,width,height,nb_read_frames",
            "-of", "json", str(stream),
        ])
        info = json.loads((out / (codec + "-probe.log")).read_text())["streams"][0]
        if (info["codec_name"], info["width"], info["height"], int(info["nb_read_frames"])) != (
                codec, width, height, args.frames):
            raise SystemExit(f"Unexpected encoded stream: {info}")
        for mode, decoder in (("software", codec), ("hardware", codec + "_v4l2m2m")):
            run(codec + "-decode-" + mode, [
                "ffmpeg", "-hide_banner", "-nostdin", "-y", "-c:v", decoder,
                "-i", str(stream), "-vf", "format=yuv420p", "-fps_mode", "passthrough",
                "-f", "framemd5", str(out / (codec + "-" + mode + ".md5")),
            ])
        sw = hashes(out / (codec + "-software.md5"))
        hw = hashes(out / (codec + "-hardware.md5"))
        if len(sw) != args.frames or len(hw) != args.frames or hw != sw:
            raise SystemExit(f"{codec}: frame count or pixel comparison failed: SW={len(sw)}, HW={len(hw)}")
        results.append({"codec": codec, "width": width, "height": height,
                        "frames": len(hw), "hardware_encode": True,
                        "hardware_decode": True, "pixels_match_software": True})
        print(f"PASS: {codec} {width}x{height}, {len(hw)} hardware-encoded frames; hardware/software decoded pixels match", flush=True)
    (out / "results.json").write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
