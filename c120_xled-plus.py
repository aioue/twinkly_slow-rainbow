#!/usr/bin/env python3
"""C.120 through xled_plus: the slow_rainbow sample, set up for one string.

Same movie as c120.py (2160 frames at 18 fps, two rainbows, one revolution in
120 seconds, white channel 0, dimmer 80%), built and uploaded with the
xled_plus library instead of c120.py's own HTTP client. Based on
https://github.com/Anders-Holst/xled_plus/pull/33

Needs xled_plus (https://github.com/Anders-Holst/xled_plus). Until the PR is
merged, install it with the PR's sample if you want to compare:
    pip install xled git+https://github.com/Anders-Holst/xled_plus

    python3 c120_xled-plus.py HOST          # read the string, write nothing
    python3 c120_xled-plus.py HOST --yes    # upload and play (refuses if a movie is stored)
    python3 c120_xled-plus.py HOST --yes --overwrite   # delete stored movies, then upload
    python3 c120_xled-plus.py HOST --yes --append      # keep stored movies, add C.120 and play it

Differences from the upstream sample:
- By default it will not upload over a stored movie. HighControlInterface.show_movie
  deletes the stored movies when the new one does not fit. This script stops
  instead, as c120.py does, unless you pass --overwrite or --append.
- --overwrite deletes every stored movie first. --append keeps them and stops
  if C.120 does not fit in the free frames. Firmware before 2.5.6 and family D
  hold one movie, so --append is refused there.
- It writes only with --yes.
- It sets the 80% dimmer after the upload, and names the movie "C.120".
"""

from __future__ import annotations

import argparse
import sys
from colorsys import hsv_to_rgb

SECONDS = 120
FPS = 18
FRAMES = SECONDS * FPS
RAINBOWS = 2
BRIGHTNESS_PERCENT = 80
MOVIE_NAME = "C.120"
# Strings leaving the controller in opposite directions: one continuous rainbow.
CIRCULAR = False


def rainbow_color(index: int, led_count: int, frame: int) -> tuple[int, int, int]:
    """Full-saturation HSV, the same colours as c120.py."""
    hue = (RAINBOWS * index / led_count - frame / FRAMES) % 1.0
    red, green, blue = hsv_to_rgb(hue, 1.0, 1.0)
    return (int(red * 255 + 0.5), int(green * 255 + 0.5), int(blue * 255 + 0.5))


def make_movie(ctr):
    return ctr.make_func_movie(
        FRAMES,
        lambda t: ctr.make_func_pattern(
            lambda i: rainbow_color(i, ctr.num_leds, t),
            circular=CIRCULAR,
        ),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Upload C.120 to a Twinkly string with xled_plus.")
    parser.add_argument("host", help="the string's IP address")
    parser.add_argument("--yes", action="store_true", help="upload the movie and play it")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--overwrite", action="store_true", help="delete stored movies, then upload")
    group.add_argument("--append", action="store_true", help="keep stored movies and add C.120")
    args = parser.parse_args(argv)

    try:
        from xled_plus.highcontrol import HighControlInterface
    except ImportError:
        print("xled_plus is not installed. Run: pip install xled git+https://github.com/Anders-Holst/xled_plus",
              file=sys.stderr)
        return 1

    ctr = HighControlInterface(args.host)
    print(f"{ctr.num_leds} LEDs, {ctr.led_profile}, firmware {'.'.join(map(str, ctr.version))}")
    if ctr.led_profile != "RGBW":
        print(f"expected an RGBW string, got {ctr.led_profile}. Nothing was written.", file=sys.stderr)
        return 1
    multi = ctr.family != "D" and ctr.version >= (2, 5, 6)
    stored = ctr.get_movies()["movies"] if multi else []
    print(f"movies stored: {len(stored)}")
    if stored and not (args.overwrite or args.append):
        print("The string already stores a movie. Nothing was written. "
              "Pass --overwrite to delete it or --append to keep it.", file=sys.stderr)
        return 1
    if args.append and not multi:
        print("This firmware holds one movie, so --append is not possible. Use --overwrite.", file=sys.stderr)
        return 1
    if not args.yes:
        print(f"{MOVIE_NAME}: {FRAMES} frames at {FPS} fps. Nothing was written. Re-run with --yes to upload.")
        return 0

    movie = make_movie(ctr)
    if args.append:
        movie_id = ctr.upload_movie(movie, FPS, MOVIE_NAME)
        if movie_id is False:
            print("Not enough free frames for C.120. Nothing was written. Use --overwrite.", file=sys.stderr)
            return 1
        ctr.show_movie(movie_id)
    else:
        if args.overwrite:
            ctr.clear_movies()
        ctr.show_movie(movie, FPS, MOVIE_NAME)
    ctr.set_brightness(BRIGHTNESS_PERCENT)
    print(f"Uploaded {MOVIE_NAME} and set the dimmer to {BRIGHTNESS_PERCENT}%.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
