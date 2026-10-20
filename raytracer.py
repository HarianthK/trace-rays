# A ray tracer: spheres, glass, a checkered floor, shadows, reflections, writing its own PNG.
# Run: python raytracer.py [-o out.png] [-w 640] [-H 360] [-s 2] [-p processes]. DOCS.md explains the maths.
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


def refract(direction, normal, eta):
    # Snell's law, with the normal facing the incoming ray and eta = n1 / n2. None means
    # total internal reflection: the angle is too steep for any light to get out.
    cos_i = -dot(direction, normal)
    k = 1 - eta * eta * (1 - cos_i * cos_i)
    if k < 0:
        return None
    return add(mul(direction, eta), mul(normal, eta * cos_i - math.sqrt(k)))


def schlick(cos, r0):
    # Schlick's approximation: r0 of the light reflects head on, rising to all of it at a grazing angle.
    return r0 + (1 - r0) * (1 - cos) ** 5


def glass(point, direction, normal, ior):
    # The rays a glass surface sends on, each with its share of the light: a reflection,
    # and unless the angle is too steep, the rest bent through.
    entering = dot(direction, normal) < 0
    n = normal if entering else mul(normal, -1)
    bounce = unit(sub(direction, mul(n, 2 * dot(direction, n))))
    reflected = (add(point, mul(n, 1e-3)), bounce)
    bent = refract(direction, n, 1 / ior if entering else ior)
    if bent is None:
        return [(1.0, *reflected)]
    # Schlick's approximation of how much reflects, from the angle on the air side.
    cos = -dot(direction if entering else bent, n)
    r = schlick(cos, ((ior - 1) / (ior + 1)) ** 2)
    return [(r, *reflected), (1 - r, add(point, mul(n, -1e-3)), unit(bent))]


class Sphere:
    def __init__(self, centre, radius, colour, reflect=0.0, ior=None):
        self.centre, self.radius, self.colour, self.reflect = centre, radius, colour, reflect
        self.ior = ior  # index of refraction; set, the sphere is clear glass

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
    ior = None

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
    Sphere((0.35, -0.15, -1.1), 0.35, BLACK, ior=1.5),
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


def light_reaching(point, to_light):
    # A shadow is the same question again: what is in the way to the light? Glass passes 60%
    # and the ray goes on past it, so a solid thing behind the glass still casts its shadow.
    left, through = length(sub(LIGHT, point)), 1.0
    for _ in range(16):
        t, blocker = nearest(point, to_light)
        if blocker is None or t >= left:
            return through
        if not blocker.ior:
            return 0.0
        hit = add(point, mul(to_light, t))
        # Each ball counts once, on the way in; leaving it costs nothing more.
        if dot(blocker.normal_at(hit), to_light) < 0:
            through *= 0.6
        point, left = add(hit, mul(to_light, 1e-3)), left - t - 1e-3
    return through


def shade(origin, direction, depth=0):
    t, obj = nearest(origin, direction)
    if obj is None:
        # Sky: a vertical gradient, so the reflections have something to show.
        k = 0.5 * (unit(direction)[1] + 1.0)
        return add(mul((1.0, 1.0, 1.0), 1 - k), mul((0.45, 0.62, 0.95), k))

    point = add(origin, mul(direction, t))
    normal = obj.normal_at(point)
    to_light = unit(sub(LIGHT, point))

    lit = max(0.0, dot(normal, to_light)) * light_reaching(add(point, mul(normal, 1e-3)), to_light)

    # Specular highlight: how closely the reflected light points back at us.
    highlight = BLACK
    if lit > 0:
        # Only where light lands: with the light straight behind, eye and light cancel and there is no halfway.
        half = unit(add(to_light, mul(direction, -1)))
        highlight = mul((1.0, 1.0, 1.0), 0.4 * max(0.0, dot(normal, half)) ** 48)

    if obj.ior:
        # Glass has no colour of its own: it is what it reflects plus what shows through it.
        colour = highlight
        if depth < 6:
            for weight, start, way in glass(point, direction, normal, obj.ior):
                colour = add(colour, mul(shade(start, way, depth + 1), weight))
        return colour

    colour = add(mul(obj.colour_at(point), AMBIENT + lit), highlight)

    if obj.reflect > 0 and depth < 4:
        bounce = sub(direction, mul(normal, 2 * dot(direction, normal)))
        reflected = shade(add(point, mul(normal, 1e-3)), unit(bounce), depth + 1)
        # reflect is the share head on; like any real surface, more reflects at a glancing angle.
        r = schlick(max(0.0, -dot(direction, normal)), obj.reflect)
        colour = add(mul(colour, 1 - r), mul(reflected, r))
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
    # -H sets the height; without it the picture is 16:9. The camera keeps its width and fits the height.
    height = int(argv[argv.index("-H") + 1]) if "-H" in argv else round(width * 9 / 16)
    rows = render(width, height, samples, processes)
    open(out, "wb").write(png(rows, width, height))
    print(f"{out}: {width}x{height}, {samples * samples} samples per pixel")
