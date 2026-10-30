# Run: python test_raytracer.py. The PNG is read back by Pillow, which is not our code.
import io
import math
import os
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

    # Glass. Head on, a ray goes straight in; at 45 degrees the sine of its angle drops by 1.5.
    straight = rt.refract((0.0, 0.0, -1.0), (0.0, 0.0, 1.0), 1 / 1.5)
    assert max(abs(a - b) for a, b in zip(straight, (0.0, 0.0, -1.0))) < 1e-12, straight
    bent = rt.unit(rt.refract(rt.unit((1.0, 0.0, -1.0)), (0.0, 0.0, 1.0), 1 / 1.5))
    assert abs(bent[0] - math.sin(math.radians(45)) / 1.5) < 1e-12, bent
    # From inside, steeper than the critical angle of 41.8 degrees, all of it reflects.
    steep = (math.sin(math.radians(50)), 0.0, -math.cos(math.radians(50)))
    assert rt.refract(steep, (0.0, 0.0, 1.0), 1.5) is None
    assert [w for w, _, _ in rt.glass((0.0, 0.0, 0.0), steep, (0.0, 0.0, -1.0), 1.5)] == [1.0]
    # Schlick: 4% reflects head on, and nearly all of it at a grazing angle.
    head_on = rt.glass((0.0, 0.0, 0.0), (0.0, 0.0, -1.0), (0.0, 0.0, 1.0), 1.5)
    assert abs(head_on[0][0] - 0.04) < 1e-12 and abs(head_on[0][0] + head_on[1][0] - 1) < 1e-12
    grazing = rt.glass((0.0, 0.0, 0.0), rt.unit((1.0, 0.0, -0.01)), (0.0, 0.0, 1.0), 1.5)
    assert grazing[0][0] > 0.9, grazing[0][0]
    # Leaving glass just under the critical angle, the light outside grazes the surface, so
    # most of it reflects: the share must climb toward all of it, not stay at 4%.
    leaving = (math.sin(math.radians(40)), 0.0, -math.cos(math.radians(40)))
    assert rt.glass((0.0, 0.0, 0.0), leaving, (0.0, 0.0, -1.0), 1.5)[0][0] > 0.2

    # Through a glass ball half a radius off centre: in at 30 degrees, bent to 19.47 inside,
    # out at 30 again, turned toward the axis by 2 * (30 - 19.47) degrees in all.
    ball = rt.Sphere((0.0, 0.0, -3.0), 1.0, rt.BLACK, ior=1.5)
    origin, way = (0.0, 0.5, 0.0), (0.0, 0.0, -1.0)
    for _ in range(2):
        point = rt.add(origin, rt.mul(way, ball.hit(origin, way)))
        normal = ball.normal_at(point)
        _, origin, way = rt.glass(point, way, normal, 1.5)[-1]
    turned = 2 * (math.radians(30) - math.asin(0.5 / 1.5))
    assert abs(math.asin(-way[1]) - turned) < 5e-3, math.degrees(math.asin(-way[1]))
    assert abs(math.degrees(math.acos(rt.dot(way, normal))) - 30) < 0.5

    # The ball in the scene: looking straight down onto it gives a real colour, and the
    # floor under it is shadowed, but less than under the solid red sphere.
    for channel in rt.shade((0.35, 3.0, -1.1), down):
        assert channel == channel and channel >= 0.0, channel
    under_glass = (0.633, -0.4, -1.267)  # just above where the light, through the ball, meets the floor
    shaded = floor_brightness(under_glass)
    ball = rt.SCENE.pop()
    unshaded = floor_brightness(under_glass)
    rt.SCENE.append(ball)
    assert 0.3 * unshaded < shaded < 0.95 * unshaded, (shaded, unshaded)
    # A solid ball further along the same line, between the glass and the light: the glass
    # no longer decides alone, and the floor is as dark as under any solid shadow.
    behind = rt.Sphere((-0.67, 1.11, -0.5), 0.2, (0.5, 0.5, 0.5))
    rt.SCENE.append(behind)
    both = floor_brightness(under_glass)
    rt.SCENE.remove(behind)
    assert both < 0.5 * shaded, (both, shaded)
    # Two glass balls in a row let through 0.6 of 0.6, not 0.6 once.
    second = rt.Sphere((-0.67, 1.11, -0.5), 0.2, rt.BLACK, ior=1.5)
    assert abs(rt.light_reaching((0.633, -0.5, -1.267), rt.unit(rt.sub(rt.LIGHT, (0.633, -0.5, -1.267)))) - 0.6) < 1e-9
    rt.SCENE.append(second)
    twice = rt.light_reaching((0.633, -0.5, -1.267), rt.unit(rt.sub(rt.LIGHT, (0.633, -0.5, -1.267))))
    rt.SCENE.remove(second)
    assert abs(twice - 0.36) < 1e-9, twice

    # Fresnel: the head-on share at a right angle, all of it at a grazing one, and more in between.
    assert rt.schlick(1.0, 0.25) == 0.25 and rt.schlick(0.0, 0.25) == 1.0
    assert rt.schlick(1.0, 0.25) < rt.schlick(0.7, 0.25) < rt.schlick(0.2, 0.25) < 1.0
    # One value worked by hand, so the formula is not only checked against itself: 0.04 + 0.96 * 0.5^5.
    assert abs(rt.schlick(0.5, 0.04) - 0.07) < 1e-12, rt.schlick(0.5, 0.04)
    # A black mirror sphere, lit from behind so it shows nothing of its own: hit dead centre, it is
    # exactly its head-on share of the sky straight behind the eye; hit at its rim, nearly all sky.
    real_scene, real_light = rt.SCENE[:], rt.LIGHT
    rt.SCENE[:] = [rt.Sphere((0.0, 0.0, -5.0), 1.0, rt.BLACK, reflect=0.5)]
    rt.LIGHT = (0.0, 0.0, -20.0)
    try:
        sky_behind = rt.shade((0.0, 0.0, 100.0), (0.0, 0.0, 1.0))  # nothing back there but sky
        centre = rt.shade((0.0, 0.0, 0.0), (0.0, 0.0, -1.0))
        assert all(abs(c - 0.5 * s) < 1e-9 for c, s in zip(centre, sky_behind)), (centre, sky_behind)
        # Near the rim the ray bounces off at a glancing angle, so the sky it shows is a different
        # part of the gradient: compare with the sky along the bounce itself.
        ray = rt.unit((0.0, 0.204, -1.0))  # the tangent is at 1 / sqrt(24), about 0.2041
        point = rt.mul(ray, rt.SCENE[0].hit((0.0, 0.0, 0.0), ray))
        normal = rt.SCENE[0].normal_at(point)
        bounce = rt.unit(rt.sub(ray, rt.mul(normal, 2 * rt.dot(ray, normal))))
        mirror = rt.SCENE.pop()
        sky_there = rt.shade((0.0, 0.0, 0.0), bounce)
        rt.SCENE.append(mirror)
        share = rt.schlick(-rt.dot(ray, normal), 0.5)
        rim = rt.shade((0.0, 0.0, 0.0), ray)
        assert share > 0.9, share
        assert all(abs(c - share * s) < 1e-9 for c, s in zip(rim, sky_there)), (rim, sky_there, share)
    finally:
        rt.SCENE[:], rt.LIGHT = real_scene, real_light

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

    # Triangles. A ray from the origin at (0.25, 0.25, -2) hits the triangle in the z=-2
    # plane at that point; one at (0.6, 0.6, -2) is past the long edge.
    tri = rt.Triangle((0.0, 0.0, -2.0), (1.0, 0.0, -2.0), (0.0, 1.0, -2.0), (1.0, 1.0, 1.0))
    to = rt.unit((0.25, 0.25, -2.0))
    assert abs(tri.hit((0.0, 0.0, 0.0), to) - rt.length((0.25, 0.25, -2.0))) < 1e-9
    assert tri.hit((0.0, 0.0, 0.0), rt.unit((0.6, 0.6, -2.0))) is None
    assert tri.hit((0.0, 0.0, 0.0), rt.unit((-0.1, 0.5, -2.0))) is None
    assert tri.hit((0.0, 0.0, 0.0), rt.unit((0.5, -0.1, -2.0))) is None
    # Behind the ray, side on, and seen from the back, which shadow rays need.
    assert tri.hit((0.0, 0.0, 0.0), rt.mul(to, -1)) is None
    assert tri.hit((0.0, 0.2, -2.0), (1.0, 0.0, 0.0)) is None
    assert abs(tri.hit((0.25, 0.25, -3.0), (0.0, 0.0, 1.0)) - 1.0) < 1e-9
    assert tri.normal_at(None) == (0.0, 0.0, 1.0)

    # Random rays against another method: meet the plane, then ask whether the point is on
    # the inner side of all three edges. Rays too close to an edge to call are skipped.
    import random
    rng = random.Random(7)

    def point():
        return tuple(rng.uniform(-2, 2) for _ in range(3))

    hits = compared = 0
    while compared < 3000:
        a, b, c, origin = point(), point(), point(), point()
        direction = rt.unit(rt.sub(rt.add(rt.mul(rt.add(a, b), 0.5), point()), origin))
        n = rt.cross(rt.sub(b, a), rt.sub(c, a))
        if abs(rt.dot(n, direction)) < 1e-3 * rt.length(n):
            continue
        t = rt.dot(n, rt.sub(a, origin)) / rt.dot(n, direction)
        p = rt.add(origin, rt.mul(direction, t))
        sides = [rt.dot(rt.cross(rt.sub(q, o), rt.sub(p, o)), n) / rt.length(n) / rt.length(rt.sub(q, o))
                 for o, q in ((a, b), (b, c), (c, a))]
        if min(abs(x) for x in sides) < 1e-6 or abs(t) < 1e-3:
            continue
        expected = t if t > 0 and min(sides) > 0 else None
        got = rt.Triangle(a, b, c, rt.BLACK).hit(origin, direction)
        assert (got is None) == (expected is None) and (got is None or abs(got - t) < 1e-6), (a, b, c, origin, direction, got, t)
        hits += expected is not None
        compared += 1
    assert hits > 300, hits

    # The pyramid's faces must point out, or its lit sides would shade as if facing away.
    faces = rt.pyramid((1.0, 0.0, -3.0), 0.5, 1.0, rt.BLACK)
    middle = (1.0, 0.25, -3.0)
    for face in faces:
        centroid = rt.add(face.a, rt.mul(rt.add(face.e1, face.e2), 1 / 3))
        assert rt.dot(face.normal, rt.sub(centroid, middle)) > 0, "a face of the pyramid points inward"
    # And the one in the scene casts a shadow, found the same way as the sphere's.
    green = [obj for obj in rt.SCENE if isinstance(obj, rt.Triangle)]
    behind = (-0.36, -0.4, -1.78)  # just outside the base and just above the floor, in its shadow
    dark = floor_brightness(behind)
    kept = list(rt.SCENE)
    rt.SCENE[:] = [obj for obj in kept if obj not in green]
    bright = floor_brightness(behind)
    rt.SCENE[:] = kept
    assert dark < bright * 0.6, f"the pyramid casts no real shadow: {dark:.3f} vs {bright:.3f}"
    print(f"triangles: {compared} random rays agree with a second method, {hits} of them hits")

    # -H sets the height on the command line; without it the picture stays 16:9.
    import subprocess
    out = os.path.join(os.path.dirname(os.path.abspath(rt.__file__)), "t-size.png")
    try:
        for flags, size in ((["-w", "40", "-H", "30"], (40, 30)), (["-w", "32"], (32, 18))):
            subprocess.run([sys.executable, rt.__file__, *flags, "-s", "1", "-p", "1", "-o", out], check=True, capture_output=True)
            got = Image.open(out)
            got.load()
            assert got.size == size, f"{flags} made {got.size}, not {size}"
    finally:
        if os.path.exists(out):
            os.remove(out)
    print("-H sets the height, and 16:9 is the default")


# Each worker process imports this file again, so nothing may run on import alone.
if __name__ == "__main__":
    main()
    sys.exit(0)
