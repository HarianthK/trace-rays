# Run: python test_raytracer.py. The PNG is read back by Pillow, which is not our code.
import io
import math
import sys

import raytracer as rt


def main():
    # A ray down the -z axis at a unit sphere two units away enters at z=-1, so t is 1.
    sphere = rt.Sphere((0.0, 0.0, -2.0), 1.0, (1.0, 0.0, 0.0))
    assert abs(sphere.hit((0.0, 0.0, 0.0), (0.0, 0.0, -1.0)) - 1.0) < 1e-9
    # A ray that passes beside it, and one pointing the other way, must miss.
    assert sphere.hit((0.0, 1.5, 0.0), (0.0, 0.0, -1.0)) is None
    assert sphere.hit((0.0, 0.0, 0.0), (0.0, 0.0, 1.0)) is None
    # Grazing the edge exactly touches it: the ray at y=1 meets the sphere at one point.
    assert abs(sphere.hit((0.0, 1.0, 0.0), (0.0, 0.0, -1.0)) - 2.0) < 1e-6
    # From inside, the hit is the exit point ahead, never the one behind.
    assert abs(sphere.hit((0.0, 0.0, -2.0), (0.0, 0.0, -1.0)) - 1.0) < 1e-9
    # The normal points outward.
    assert rt.dot(sphere.normal_at((0.0, 0.0, -1.0)), (0.0, 0.0, 1.0)) > 0.99

    # The floor's checker alternates every unit, in both directions.
    plane = rt.Plane(0.0, [(1.0, 1.0, 1.0), (0.0, 0.0, 0.0)])
    assert plane.colour_at((0.5, 0.0, 0.5)) != plane.colour_at((1.5, 0.0, 0.5))
    assert plane.colour_at((0.5, 0.0, 0.5)) != plane.colour_at((0.5, 0.0, 1.5))
    assert plane.colour_at((0.5, 0.0, 0.5)) == plane.colour_at((1.5, 0.0, 1.5))
    # A ray parallel to the floor never lands on it.
    assert plane.hit((0.0, 1.0, 0.0), (1.0, 0.0, 0.0)) is None

    # Shadows: the same patch of floor, with and without the sphere that blocks the
    # light. Comparing one point to itself keeps the checker's own colour out of it.
    down = (0.0, -1.0, 0.0)
    blocker = rt.SCENE[1]
    in_shadow = (0.65, 3.0, -3.23)  # where the light, through that sphere, meets the floor

    def floor_brightness(point):
        return sum(rt.shade(point, down)) / 3

    dark = floor_brightness(in_shadow)
    rt.SCENE.remove(blocker)
    bright = floor_brightness(in_shadow)
    rt.SCENE.insert(1, blocker)
    assert dark < bright * 0.6, f"the sphere casts no real shadow: {dark:.3f} vs {bright:.3f}"
    # And a point well clear of it must be unaffected by removing the sphere.
    clear = (-2.5, 3.0, -1.0)
    before = floor_brightness(clear)
    rt.SCENE.remove(blocker)
    assert abs(floor_brightness(clear) - before) < 0.02, "the sphere changes floor it does not touch"
    rt.SCENE.insert(1, blocker)

    # Nothing in the scene may come back as a negative or a NaN, which is what a
    # bad normal or a stray division produces and which the gamma step would hide.
    for x in (-2.0, -0.5, 0.0, 0.9, 2.2):
        for z in (-3.0, -2.0, -1.0):
            for channel in rt.shade((x, 3.0, z), down):
                assert channel == channel and channel >= 0.0, (x, z, channel)

    # The PNG: render something tiny, then let Pillow tell us what we wrote.
    rows = rt.render(48, 27, samples=1, processes=1)
    data = rt.png(rows, 48, 27)
    assert data[:8] == b"\x89PNG\r\n\x1a\n"

    from PIL import Image  # noqa: E402

    image = Image.open(io.BytesIO(data))
    image.load()
    assert image.format == "PNG" and image.size == (48, 27) and image.mode == "RGB"
    for y in (0, 13, 26):
        for x in (0, 24, 47):
            expected = tuple(rows[y][x * 3:x * 3 + 3])
            assert image.getpixel((x, y)) == expected, f"pixel {x},{y}: {image.getpixel((x, y))} != {expected}"

    # The top row is sky and the bottom row is floor, so the picture is the right way up.
    sky = sum(rows[0][:9]) / 9
    floor = sum(rows[-1][:9]) / 9
    assert sky > 150 and abs(sky - floor) > 10, (sky, floor)

    print(f"ok ({image.size[0]}x{image.size[1]} read back by Pillow, {len(data)} bytes)")

    # Rows drawn by several processes, in whatever order they finish, must make exactly
    # the same file as one process drawing them top to bottom.
    alone = rt.png(rt.render(64, 36, samples=2, processes=1), 64, 36)
    shared = rt.png(rt.render(64, 36, samples=2, processes=3), 64, 36)
    assert shared == alone, "the parallel render differs from the single-process one"
    print("parallel render identical to the single-process one")


# Each worker process imports this file again, so nothing may run on import alone.
if __name__ == "__main__":
    main()
    sys.exit(0)
