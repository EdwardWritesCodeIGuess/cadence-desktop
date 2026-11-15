"""Album-artwork colours. Pure Python so it can be tested without AppKit."""
import colorsys
import math

DEFAULT_ACCENT = '#A8BAFF'
DEFAULT_SECONDARY = '#7355B8'


def to_hex(rgb):
    return '#'+''.join(f'{round(max(0., min(1., v))*255):02X}' for v in rgb)


def from_hex(value):
    try:
        number = int(value.lstrip('#'), 16)
    except (AttributeError, ValueError):
        number = 0xA8BAFF
    return ((number >> 16) & 255)/255, ((number >> 8) & 255)/255, (number & 255)/255


def readable(hue, saturation, floor=.5):
    """Brightest colour of this hue that stays legible on a dark backdrop."""
    saturation = max(.38, min(.78, saturation))
    while True:
        rgb = colorsys.hsv_to_rgb(hue, saturation, 1.)
        if .2126*rgb[0]+.7152*rgb[1]+.0722*rgb[2] >= floor or saturation <= .2:
            return rgb
        saturation -= .04


def album_palette(samples):
    """(accent, secondary) hex colours from an iterable of 0..1 RGB samples.

    The accent is the most vivid hue family in the artwork rather than one
    lucky pixel; the secondary is a second family, or a neighbouring hue.
    """
    bins = [[0., 0., 0., 0.] for _ in range(12)]
    for red, green, blue in samples:
        hue, saturation, value = colorsys.rgb_to_hsv(red, green, blue)
        if saturation < .15 or value < .15:
            continue
        weight = saturation*saturation*(.25+value)
        slot = bins[int(hue*12) % 12]
        slot[0] += weight
        slot[1] += weight*math.cos(2*math.pi*hue)
        slot[2] += weight*math.sin(2*math.pi*hue)
        slot[3] += weight*saturation
    best = max(range(12), key=lambda i: bins[i][0])
    if bins[best][0] <= 0:
        return DEFAULT_ACCENT, DEFAULT_SECONDARY

    def describe(index):
        weight, x, y, saturation = bins[index]
        return (math.atan2(y, x)/(2*math.pi)) % 1., saturation/weight

    hue, saturation = describe(best)
    others = [i for i in range(12) if min((i-best) % 12, (best-i) % 12) >= 2 and bins[i][0] >= .15*bins[best][0]]
    if others:
        second_hue, second_saturation = describe(max(others, key=lambda i: bins[i][0]))
    else:
        second_hue, second_saturation = (hue+.09) % 1., saturation
    secondary = colorsys.hsv_to_rgb(second_hue, max(.4, min(.8, second_saturation)), .75)
    return to_hex(readable(hue, saturation)), to_hex(secondary)
