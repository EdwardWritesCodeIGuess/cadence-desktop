"""Widget placement helpers. Pure Python so they can be tested without AppKit."""


def snap_origin(origin, size, area, threshold=14., margin=16.):
    """Pull a dragged widget onto the screen's edges or centre lines.

    origin and size describe the widget; area is the usable screen rectangle
    as (x, y, width, height). Positions further than `threshold` are untouched.
    """
    (x, y), (width, height), (left, bottom, across, up) = origin, size, area

    def near(value, targets):
        best = min(targets, key=lambda target: abs(target-value))
        return best if abs(best-value) <= threshold else value

    return (near(x, (left+margin, left+(across-width)/2, left+across-width-margin)),
            near(y, (bottom+margin, bottom+(up-height)/2, bottom+up-height-margin)))
