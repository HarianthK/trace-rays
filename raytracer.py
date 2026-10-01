# A ray tracer: spheres, a checkered floor, shadows, reflections, writing its own PNG.
# Run: python raytracer.py [-o out.png] [-w 640] [-s 2] [-p processes]. DOCS.md explains the maths.
import math
import multiprocessing
import os
import struct
import sys
import zlib

BLACK = (0.0, 0.0, 0.0)


def add(a, b): return (a[0] + b[0], a[1] + b[1], a[2] + b[2])
def sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def mul(a, k): return (a[0] * k, a[1] * k, a[2] * k)
def dot(a, b): return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
def cross(a, b): return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
def length(a): return math.sqrt(dot(a, a))


def unit(a):
    n = length(a)
    return (a[0] / n, a[1] / n, a[2] / n)


class Sphere:
    def __init__(self, centre, radius, colour, reflect=0.0):
        self.centre, self.radius, self.colour, self.reflect = centre, radius, colour, reflect

    def hit(self, origin, direction):
        # |origin + t*direction - centre| = radius, solved as a quadratic in t.
        oc = sub(origin, self.centre)
        b = dot(oc, direction)
        c = dot(oc, oc) - self.radius * self.radius
        disc = b * b - c
        if disc < 0:
            return None
        root = math.sqrt(disc)
        for t in (-b - root, -b + root):
            if t > 1e-4:
                return t
        return None

    def normal_at(self, point):
        return unit(sub(point, self.centre))

    def colour_at(self, point):
        return self.colour


class Plane:
    def __init__(self, height, colours, reflect=0.0):
        self.height, self.colours, self.reflect = height, colours, reflect

    def hit(self, origin, direction):
        if abs(direction[1]) < 1e-6:
            return None
        t = (self.height - origin[1]) / direction[1]
        return t if t > 1e-4 else None

    def normal_at(self, point):
        return (0.0, 1.0, 0.0)

    def colour_at(self, point):
        # A checker is just the parity of the floored coordinates.
        odd = (math.floor(point[0]) + math.floor(point[2])) % 2
        return self.colours[odd]


SCENE = [
    Plane(-0.5, [(0.85, 0.85, 0.88), (0.18, 0.20, 0.24)], reflect=0.15),
    Sphere((0.0, 0.3, -2.4), 0.8, (0.85, 0.25, 0.25), reflect=0.35),
    Sphere((-1.35, -0.05, -1.9), 0.45, (0.25, 0.55, 0.85), reflect=0.1),
    Sphere((1.25, 0.0, -2.0), 0.5, (0.95, 0.80, 0.30), reflect=0.6),
]
LIGHT = (-2.2, 3.0, 0.4)
AMBIENT = 0.12


def nearest(origin, direction):
    best_t, best_obj = float("inf"), None
    for obj in SCENE:
        t = obj.hit(origin, direction)
        if t is not None and t < best_t:
            best_t, best_obj = t, obj
    return best_t, best_obj


def shade(origin, direction, depth=0):
    t, obj = nearest(origin, direction)
    if obj is None:
        # Sky: a vertical gradient, so the reflections have something to show.
        k = 0.5 * (unit(direction)[1] + 1.0)
        return add(mul((1.0, 1.0, 1.0), 1 - k), mul((0.45, 0.62, 0.95), k))

    point = add(origin, mul(direction, t))
    normal = obj.normal_at(point)
    to_light = unit(sub(LIGHT, point))

    # A shadow is the same question again: does anything block the way to the light?
    shadow_t, blocker = nearest(add(point, mul(normal, 1e-3)), to_light)
    lit = 0.0 if blocker is not None and shadow_t < length(sub(LIGHT, point)) else max(0.0, dot(normal, to_light))

    base = obj.colour_at(point)
    colour = mul(base, AMBIENT + lit)
    if lit > 0:
        # Specular highlight: how closely the reflected light points back at us.
        half = unit(add(to_light, mul(direction, -1)))
        colour = add(colour, mul((1.0, 1.0, 1.0), 0.4 * max(0.0, dot(normal, half)) ** 48))

    if obj.reflect > 0 and depth < 4:
        bounce = sub(direction, mul(normal, 2 * dot(direction, normal)))
        reflected = shade(add(point, mul(normal, 1e-3)), unit(bounce), depth + 1)
        colour = add(mul(colour, 1 - obj.reflect), mul(reflected, obj.reflect))
    return colour


def camera(width, height):
    # Off to one side, so the checker boundary at x=0 does not split the picture down the middle.
    eye = (0.8, 0.75, 1.4)
    target = (-0.1, 0.1, -2.1)
    forward = unit(sub(target, eye))
    right = unit(cross(forward, (0.0, 1.0, 0.0)))
    up = cross(right, forward)
    half_w = math.tan(math.radians(55) / 2)
    return eye, forward, right, up, half_w, half_w * height / width


def render_row(job):
    y, width, height, samples = job
    eye, forward, right, up, half_w, half_h = camera(width, height)
    row = bytearray()
    for x in range(width):
        total = BLACK
        for sy in range(samples):
            for sx in range(samples):
                # Sample the pixel on a grid, which is what removes the jagged edges.
                u = (2 * ((x + (sx + 0.5) / samples) / width) - 1) * half_w
                v = (1 - 2 * ((y + (sy + 0.5) / samples) / height)) * half_h
                direction = unit(add(forward, add(mul(right, u), mul(up, v))))
                total = add(total, shade(eye, direction))
        n = samples * samples
        for channel in mul(total, 1.0 / n):
            # sRGB gamma, without which everything looks too dark.
            row.append(min(255, max(0, round(255 * min(1.0, channel) ** (1 / 2.2)))))
    return bytes(row)


def render(width=480, height=270, samples=2, processes=None):
    # No pixel depends on another, so rows can be drawn in any order on any core. One
    # core is left free by default, so the machine stays usable while it renders.
    jobs = [(y, width, height, samples) for y in range(height)]
    processes = processes or max(1, (os.cpu_count() or 2) - 1)
    if processes == 1:
        return [render_row(job) for job in jobs]
    with multiprocessing.Pool(processes) as pool:
        return pool.map(render_row, jobs, chunksize=max(1, height // (processes * 8)))


def png(rows, width, height):
    def chunk(tag, payload):
        return struct.pack(">I", len(payload)) + tag + payload + struct.pack(">I", zlib.crc32(tag + payload))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)  # 8-bit, truecolour
    # Every scanline is prefixed with its filter type; 0 means the bytes are as they are.
    raw = b"".join(b"\0" + row for row in rows)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


if __name__ == "__main__":
    argv = sys.argv[1:]
    out = argv[argv.index("-o") + 1] if "-o" in argv else "render.png"
    width = int(argv[argv.index("-w") + 1]) if "-w" in argv else 480
    samples = int(argv[argv.index("-s") + 1]) if "-s" in argv else 2
    processes = int(argv[argv.index("-p") + 1]) if "-p" in argv else None
    height = round(width * 9 / 16)
    rows = render(width, height, samples, processes)
    open(out, "wb").write(png(rows, width, height))
    print(f"{out}: {width}x{height}, {samples * samples} samples per pixel")
