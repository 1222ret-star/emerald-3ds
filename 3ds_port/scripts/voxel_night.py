"""Authored exterior glass regions, without recolouring frames or roof art."""

NIGHT_WINDOWS = {
    "littleroot_house_w": ((17, 61, 23, 69), (25, 61, 31, 69)),
    "littleroot_house_e": ((17, 61, 23, 69), (25, 61, 31, 69)),
    "littleroot_lab": ((18, 61, 30, 69), (34, 61, 46, 69)),
    "oldale_house": ((34, 42, 46, 54),),
    "kit_house_4": ((34, 42, 46, 54),),
    "kit_house_5": ((18, 42, 30, 54), (50, 42, 62, 54)),
    "flower_shop": ((9, 42, 15, 53), (65, 42, 71, 53), (81, 42, 87, 53)),
}


def window_mask(art, rectangles):
    width, height = art.size
    mask = bytearray(width * height)
    pixels = art.load()
    for left, top, right, bottom in rectangles:
        if not (0 <= left < right <= width and 0 <= top < bottom <= height):
            raise ValueError("window rectangle is outside the building art")
        for ypos in range(top, bottom):
            for xpos in range(left, right):
                red, green, blue, alpha = pixels[xpos, ypos]
                if alpha >= 128 and red >= 90 and green > red and blue > red + 12:
                    mask[ypos * width + xpos] = min(255, 128 + (red + green + blue) // 6)
    return mask
