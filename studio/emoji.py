"""Color emoji for rendered cards and subtitles.

Pillow draws Korean/Latin text with the chosen subtitle font, which has no emoji
glyphs (they became tofu boxes). Text is split into emoji clusters (ZWJ
sequences, skin tones, flags, keycaps, tag sequences, variation selectors) and
plain-text runs. Each cluster is rasterised in color with the system emoji font:
on macOS through AppKit, which shapes every sequence exactly like the rest of
the system; elsewhere through Pillow's color-font support (single glyphs only).
"""
import math
import threading
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ZWJ, VS15, VS16, KEYCAP = '\u200d', '\ufe0e', '\ufe0f', '\u20e3'
INVISIBLE = {ZWJ, VS15, VS16}

# Emoji_Presentation characters below U+1F300 (shown as emoji without VS16).
_DEFAULT_EMOJI = {
    0x231A, 0x231B, *range(0x23E9, 0x23ED), 0x23F0, 0x23F3, 0x25FD, 0x25FE, 0x2614, 0x2615,
    *range(0x2648, 0x2654), 0x267F, 0x2693, 0x26A1, 0x26AA, 0x26AB, 0x26BD, 0x26BE, 0x26C4,
    0x26C5, 0x26CE, 0x26D4, 0x26EA, 0x26F2, 0x26F3, 0x26F5, 0x26FA, 0x26FD, 0x2705, 0x270A,
    0x270B, 0x2728, 0x274C, 0x274E, *range(0x2753, 0x2756), 0x2757, *range(0x2795, 0x2798),
    0x27B0, 0x27BF, 0x2B1B, 0x2B1C, 0x2B50, 0x2B55, 0x1F004, 0x1F0CF, 0x1F18E,
    *range(0x1F191, 0x1F19B), 0x1F201, 0x1F21A, 0x1F22F, *range(0x1F232, 0x1F237),
    *range(0x1F238, 0x1F23B), 0x1F250, 0x1F251}
# Text-default pictographs that become emoji only with VS16, a skin tone or a ZWJ.
_TEXT_DEFAULT = {
    0x00A9, 0x00AE, 0x203C, 0x2049, 0x2122, 0x2139, *range(0x2194, 0x219A), 0x21A9, 0x21AA,
    0x2328, 0x23CF, *range(0x23ED, 0x23F0), 0x23F1, 0x23F2, *range(0x23F8, 0x23FB), 0x24C2,
    0x25AA, 0x25AB, 0x25B6, 0x25C0, 0x25FB, 0x25FC, 0x2934, 0x2935, *range(0x2B05, 0x2B08),
    0x3030, 0x303D, 0x3297, 0x3299, 0x1F170, 0x1F171, 0x1F17E, 0x1F17F, 0x1F202, 0x1F237}


def _ri(char):
    return 0x1F1E6 <= ord(char) <= 0x1F1FF


def _modifier(char):
    return 0x1F3FB <= ord(char) <= 0x1F3FF


def _tag(char):
    return 0xE0020 <= ord(char) <= 0xE007F


def _pictographic(char):
    cp = ord(char)
    return (cp in _DEFAULT_EMOJI or cp in _TEXT_DEFAULT or 0x2600 <= cp <= 0x27BF
            or 0x1F300 <= cp <= 0x1FAFF)


def _default_emoji(char):
    cp = ord(char)
    return cp in _DEFAULT_EMOJI or 0x1F300 <= cp <= 0x1FAFF


def _element(text, i):
    """End index of one emoji element starting at i and whether it asks for emoji style."""
    char, i = text[i], i + 1
    emoji = _default_emoji(char)
    if i < len(text) and text[i] in (VS15, VS16):
        emoji = text[i] == VS16
        i += 1
    if i < len(text) and _modifier(text[i]):
        emoji, i = True, i + 1
    while i < len(text) and _tag(text[i]):
        emoji, i = True, i + 1
    return i, emoji


def _scan(text):
    """Yield (is_emoji, start, end) for every emoji cluster and single text character."""
    i = 0
    while i < len(text):
        char, end, emoji = text[i], i + 1, False
        if _ri(char):
            end, emoji = (i + 2 if i + 1 < len(text) and _ri(text[i+1]) else i + 1), True
        elif char in '0123456789#*' and (text[i+1:i+2] == KEYCAP or text[i+1:i+3] == VS16 + KEYCAP):
            end, emoji = i + (2 if text[i+1] == KEYCAP else 3), True
        elif _pictographic(char):
            end, emoji = _element(text, i)
            while end + 1 < len(text) and text[end] == ZWJ and _pictographic(text[end+1]):
                end, _ = _element(text, end + 1)
                emoji = True
        yield emoji, i, end
        i = end


def segments(text):
    """Split text into [(is_emoji, string)] runs; adjacent text characters are merged.

    Stray joiners and variation selectors are dropped from text runs because the
    subtitle fonts draw them as boxes. A text-style pictograph (VS15 or no VS16)
    stays in the text run and uses the subtitle font.
    """
    result = []
    for emoji, start, end in _scan(text):
        value = text[start:end]
        if not emoji:
            value = ''.join(char for char in value if char not in INVISIBLE)
            if not value:
                continue
            if result and not result[-1][0]:
                result[-1] = (False, result[-1][1] + value)
                continue
        result.append((emoji, value))
    return result


def has_emoji(text):
    return any(emoji for emoji, _, _ in _scan(text))


def needs_split(text):
    """True when text contains emoji or invisible joiners that the subtitle font cannot draw."""
    return any(char in INVISIBLE for char in text) or has_emoji(text)


def units(text):
    """Characters for text and whole clusters for emoji, the smallest unbreakable pieces."""
    result = []
    for emoji, value in segments(text):
        result += [value] if emoji else list(value)
    return result


def safe_cut(text, cut):
    """Move a cut position back so it never lands inside a multi-character cluster."""
    for _, start, end in _scan(text):
        if start < cut < end:
            return start or end
    return cut


APPLE = Path('/System/Library/Fonts/Apple Color Emoji.ttc')
FALLBACK_FONTS = [APPLE, Path('C:/Windows/Fonts/seguiemj.ttf'),
                  Path('/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf'),
                  Path('/usr/share/fonts/noto/NotoColorEmoji.ttf')]
# Bitmap color fonts (sbix/CBDT) only open at their embedded strike sizes.
STRIKES = (160, 137, 109, 96, 64)
_lock = threading.Lock()


def _appkit(cluster, size):
    import AppKit
    import objc
    with objc.autorelease_pool():
        face = AppKit.NSFont.fontWithName_size_('Apple Color Emoji', size)
        if face is None:
            return None
        string = AppKit.NSAttributedString.alloc().initWithString_attributes_(
            cluster, {AppKit.NSFontAttributeName: face})
        advance = string.size().width
        descent = -face.descender()
        width, height = max(1, math.ceil(advance)), max(1, math.ceil(face.ascender() + descent))
        rep = AppKit.NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
            None, width, height, 8, 4, True, False, AppKit.NSDeviceRGBColorSpace, width * 4, 32)
        context = AppKit.NSGraphicsContext.graphicsContextWithBitmapImageRep_(rep)
        AppKit.NSGraphicsContext.saveGraphicsState()
        try:
            AppKit.NSGraphicsContext.setCurrentContext_(context)
            # drawAtPoint places the line's descent above the point, so the
            # baseline sits `descent` pixels above the bottom edge.
            string.drawAtPoint_((0, 0))
            context.flushGraphics()
        finally:
            AppKit.NSGraphicsContext.restoreGraphicsState()
        raw = bytes(rep.bitmapData())
    image = Image.frombuffer('RGBa', (width, height), raw, 'raw', 'RGBa', width * 4, 1).convert('RGBA')
    return image, advance, height - descent


@lru_cache(maxsize=8)
def _pillow_face(path):
    try:
        return ImageFont.truetype(str(path), 109 if 'Noto' in path.name else 160), True
    except OSError:
        pass
    for strike in STRIKES:
        try:
            return ImageFont.truetype(str(path), strike), True
        except OSError:
            continue
    return None, False


def _pillow(cluster, size):
    # Without text shaping only the base glyph of a sequence can be drawn.
    base = cluster if len(cluster) == 1 or (len(cluster) == 2 and _ri(cluster[0])) else cluster[0]
    for path in FALLBACK_FONTS:
        if not path.exists():
            continue
        face, _ = _pillow_face(path)
        if face is None:
            continue
        ascent, descent = face.getmetrics()
        advance = face.getlength(base)
        canvas = Image.new('RGBA', (max(1, math.ceil(advance)), ascent + descent))
        ImageDraw.Draw(canvas).text((0, 0), base, font=face, embedded_color=True)
        if not canvas.getbbox():
            continue
        scale = size / face.size
        image = canvas.resize((max(1, round(canvas.width * scale)), max(1, round(canvas.height * scale))),
                              Image.Resampling.LANCZOS)
        return image, advance * scale, ascent * scale
    return None


@lru_cache(maxsize=512)
def glyph(cluster, size):
    """(RGBA image, advance, baseline row in the image) for an emoji cluster, or None."""
    with _lock:
        if APPLE.exists():
            try:
                rendered = _appkit(cluster, size)
                if rendered:
                    return rendered
            except Exception:  # noqa: BLE001 - AppKit missing or unusable; fall back to Pillow.
                pass
        return _pillow(cluster, size)


def advance(cluster, size):
    rendered = glyph(cluster, size)
    return rendered[1] if rendered else size
