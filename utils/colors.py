def linear_to_srgb(c: float) -> float:
    a = .055
    if c <= .0031308:
        return 12.92 * c
    else:
        return (1+a) * c ** (1/2.4) - a


def srgb_to_linear(c: float) -> float:
    a = .055
    if c <= .04045:
        return c / 12.92
    else:
        return ((c+a) / (1+a)) ** 2.4
