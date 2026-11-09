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
    python3 c120_xled-plus.py HOST --yes --delete-existing-movies   # delete ALL stored movies, then upload
    python3 c120_xled-plus.py HOST --yes --append      # keep stored movies, add C.120 and play it

The movie's unique_id on the string is a UUID derived from a hash of its bytes
(plus fps and LED count). If a stored movie carries that id, the script does not
upload again: it only plays it (--delete-existing-movies uploads it again anyway). Change the colours, speed or LED count and the id
changes, so the next run uploads. The string offers no way to read a movie back,
so this trusts the id. The dimmer is left alone on a skip.

What the script does for each state of the string (add --yes to write):

    State                              Default           Options
    ---------------------------------  ----------------  ------------------------------------
    No movie stored                    upload and play   -
    Same C.120 already stored          play, no upload   --delete-existing-movies re-uploads it
    Changed C.120 or another movie     refuse            --append keeps it and adds C.120;
      stored                                             --delete-existing-movies removes ALL
                                                         stored movies first
    Not enough free frames             refuse --append   --delete-existing-movies
    Firmware before 2.5.6 / family D   upload, replacing --append is refused. There is no list
      (one movie slot, no list)        the one movie     to read, so the stored movie cannot
                                                         be seen or protected
    Not an RGBW string                 refuse            -

Differences from the upstream sample:
- By default it will not upload over a stored movie. HighControlInterface.show_movie
  deletes the stored movies when the new one does not fit. This script stops
  instead, as c120.py does, unless you pass --delete-existing-movies or --append.
- --delete-existing-movies deletes every stored movie first. --append keeps them and stops
  if C.120 does not fit in the free frames. Firmware before 2.5.6 and family D
  hold one movie, so --append is refused there.
- It writes only with --yes.
- It sets the 80% dimmer after the upload, and names the movie "C.120".
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import uuid
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


def movie_id_for(data: bytes, fps: int, leds: int) -> str:
    digest = hashlib.sha256(data).hexdigest()
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"c120-xled-plus:{digest}:{fps}:{leds}"))


def frame_summary(ctr, listing: dict) -> str:
    """'<used>/<total> frames used (<free> free)', or just the free count if the total is unknown."""
    free = listing.get("available_frames")
    total = ctr.get_device_info().get("movie_capacity")
    if free is None:
        return "free frames unknown"
    if total is None:
        return f"{free} free"
    return f"{total - free}/{total} frames used ({free} free)"


def describe_storage(ctr, listing: dict, uid: str) -> str:
    stored = listing["movies"]
    if not stored and "available_frames" not in listing:
        return "movies stored: 0 (this firmware has one movie slot and no list)"
    lines = [f"movies stored: {len(stored)}, {frame_summary(ctr, listing)}"]
    for m in stored:
        mark = "  <- this C.120, unchanged" if m.get("unique_id") == uid else ""
        lines.append(
            f"  id {m.get('id')}: {m.get('name', '?')!r}, {m.get('frames_number', '?')} frames, "
            f"{m.get('fps', '?')} fps{mark}"
        )
    return "\n".join(lines)


def upload_with_id(ctr, movie, uid: str) -> int:
    """Like HighControlInterface.upload_movie, but with our own unique_id. Returns the movie slot id."""
    res = ctr.set_movies_new(MOVIE_NAME, uid, ctr.led_profile.lower() + "_raw", ctr.num_leds, FRAMES, FPS)
    movie.seek(0)
    ctr.set_movies_full(movie)
    return res["id"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Upload C.120 to a Twinkly string with xled_plus.")
    parser.add_argument("host", help="the string's IP address")
    parser.add_argument("--yes", action="store_true", help="upload the movie and play it")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--delete-existing-movies", action="store_true", help="delete stored movies, then upload")
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
    listing = ctr.get_movies() if multi else {"movies": []}
    stored = listing["movies"]

    movie = make_movie(ctr)
    uid = movie_id_for(movie.getvalue(), FPS, ctr.num_leds)
    same = [m for m in stored if m.get("unique_id") == uid]
    storage = describe_storage(ctr, listing, uid)
    print(storage)
    if same and not args.delete_existing_movies:
        print(f"{MOVIE_NAME} is already stored and unchanged. Nothing was uploaded.")
        if args.yes:
            ctr.show_movie(same[0]["id"])
            print("Playing it. The dimmer was left as it is.")
        else:
            print("Re-run with --yes to play it.")
        return 0

    if stored and not (args.delete_existing_movies or args.append):
        names = ", ".join(repr(m.get("name", "?")) for m in stored)
        print(f"The string already stores {len(stored)} other movie(s): {names}. Nothing was written.\n"
              f"  --append                   keep them and add C.120 (needs {FRAMES} free frames; "
              f"{frame_summary(ctr, listing)})\n"
              "  --delete-existing-movies   delete ALL stored movies, then upload C.120",
              file=sys.stderr)
        return 1
    if args.append and not multi:
        print("This firmware holds one movie, so --append is not possible. "
              "Uploading replaces it: drop --append.", file=sys.stderr)
        return 1
    if not args.yes:
        print(f"{MOVIE_NAME}: {FRAMES} frames at {FPS} fps, id {uid}. Nothing was written. "
              "Re-run with --yes to upload.")
        return 0

    if not multi:
        # One movie slot and no list to read back, so there is no id to keep.
        ctr.show_movie(movie, FPS, MOVIE_NAME)
    else:
        if args.append:
            if listing["available_frames"] - 1 < FRAMES:
                print("Not enough free frames to append C.120. Nothing was written. "
                      "Use --delete-existing-movies to clear the stored movies first.", file=sys.stderr)
                return 1
        elif args.delete_existing_movies:
            ctr.clear_movies()
        slot = upload_with_id(ctr, movie, uid)
        ctr.show_movie(slot)
    ctr.set_brightness(BRIGHTNESS_PERCENT)
    print(f"Uploaded {MOVIE_NAME} and set the dimmer to {BRIGHTNESS_PERCENT}%.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
