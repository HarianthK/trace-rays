# What I learned writing a ray tracer

## The light goes the wrong way on purpose

Physically, light leaves a lamp, bounces around and a little of it reaches the
eye. Simulating that means tracing billions of rays that never arrive. So a
ray tracer runs it backwards: one ray per pixel, out from the eye, and asks
what it meets. The lamp is only consulted once a surface is found, to ask
whether it can see the light. Everything else in the renderer is that same
question reused: a shadow is a ray from the surface to the lamp, a reflection
is a ray from the surface along the bounce, and both call the same routine
that made the first ray.

## The sphere is the easy shape, and that is why everyone uses it

A point is on the sphere when its distance from the centre is the radius.
Substituting the ray into that gives a quadratic in t, and the two roots are
where the ray enters and leaves. The near root is the visible surface, unless
it is behind you, in which case the far one is (which is what being inside the
sphere means). That is the whole intersection test, four lines, and it is why
every ray tracing tutorial starts with spheres rather than triangles.

## The two lines nobody mentions

**Epsilon.** A ray starting exactly on a surface immediately hits that same
surface at t near zero, so every surface shadows itself and the image turns
into grainy black noise. The fix is to start shadow and reflection rays a
thousandth of a unit along the normal, and to ignore hits closer than that.

**Gamma.** Screens are not linear: doubling the number in the file does not
double the light. The renderer's arithmetic is linear, so the result has to be
raised to the power 1/2.2 before it is written. Without it everything looks
dim and muddy, which is the single most common reason a first render looks
wrong when the maths is right.

## Antialiasing is just asking more than once

One ray per pixel gives a hard yes-or-no at every edge, so edges come out as
staircases. Sending a grid of rays through each pixel and averaging gives the
edge pixels a value in between, which is what the eye reads as a smooth line.
Three by three is nine times the work for a noticeably better picture, which
is the whole economy of rendering in one decision.

## Composition is a bug you can see

The first render put the camera on the axis at x=0, exactly where the
checkered floor changes square. The result had a seam straight down the
middle of the image, through the centre sphere, and it looked like a rendering
error. It was not: it was the geometry doing precisely what it was told. The
fix was to move the camera to one side, which is a reminder that in graphics,
"looks wrong" and "is wrong" are two different investigations.

## A PNG is simpler than it looks

Eight magic bytes, then chunks: each is a length, a four-letter tag, the
payload and a CRC32. The image chunk is the pixels zlib-compressed, with one
extra byte before every row saying which filter that row used. Zero means no
filter, which is legal and costs only a little size. Drop that byte and the
whole stream decodes shifted and every reader rejects it, which is exactly
what the test caught when I broke it on purpose.

## Testing a picture without looking at it

An image test that compares against a saved image only tells you something
changed, never whether it is right, and it fails the day you improve the
renderer. So these checks pin things that must be true regardless of how it
looks: a ray fired at a known sphere hits at a known distance, a grazing ray
touches at exactly one point, no channel is ever negative or NaN, and one
floor point gets darker when the sphere that blocks its light is put in the
scene and no darker when a distant sphere is removed. The PNG is then handed
to Pillow, because a file read back by my own reader would only prove my two
halves agree with each other.

## Using every core

No pixel depends on another, which makes a ray tracer the easiest kind of
program to spread across processors: hand out rows, collect them, write the
file. Threads would not help here, because Python runs one thread's bytecode at
a time; separate processes each get their own interpreter. The rows come back
through `Pool.map`, which returns results in the order they were asked for,
whatever order they finish in.

The full 640 by 360 image, nine samples a pixel:

| processes | time | speed-up |
| --- | --- | --- |
| 1 | 67.8s | 1x |
| 4 | 25.1s | 2.7x |
| 7 | 21.6s | 3.1x |

The machine reports eight processors, but Windows says four physical cores:
each runs two hardware threads, and a second thread on a core adds only about
15% to arithmetic like this. The default is every processor but one, so the
computer stays usable while it renders.

The check is the strictest one available: the image drawn by three processes
must be byte for byte the same file as the one drawn by one. Collecting rows in
the order they finish instead of the order they were asked for, the usual
mistake, fails it at once.

One Windows detail shaped the test file. A new process there starts by
importing the script that launched it, so a test file that ran its checks at
the top level would run them again in every worker, and its final `sys.exit`
would end the workers before they did anything. The checks now live in a
function that only runs when the file is the program being run.

## Glass is the same question asked twice more

A glass surface sends every ray on in two directions: some of it reflects, and
the rest bends through by Snell's law, n1 sin(a) = n2 sin(b). Both rays are
followed, and their colours are mixed by how much light each carries. Glass has
no colour of its own; it is only ever what it reflects plus what shows through.

The direction of travel matters in three places, and each was a bug the tests
caught when put back. On the way out the ratio of indices flips, 1.5 instead of
1/1.5. The surface normal must be turned to face the ray, or Snell's formula
bends the ray the wrong way. And going from glass to air past about 41.8
degrees, the formula asks for the square root of a negative number: no light
gets out at all, which is total internal reflection and the reason a glass ball
has a bright rim.

How much reflects comes from Schlick's approximation, 4% head on rising to all
of it at a grazing angle. The angle it wants is the one on the air side. Using
the angle inside the glass on the way out gives 4% just short of the critical
angle, so the light would drop from 96% transmitted to none in a single step.
The first version of the tests missed that and passed with it broken; a check
just under the critical angle now catches it.

The ball also turns the floor behind it upside down, as a real lens does, which
nobody wrote any code for.

The shadow was a shortcut at first: the shadow ray stopped at the first thing
in its way, and if that was glass it let 60% of the light through. A solid ball
behind the glass, between it and the lamp, would then cast no shadow at all.
Now the shadow ray goes on past glass, charging 60% once per ball, on the way
in, and stops at the first solid thing. Two glass balls in a row pass 36%. The
rendered scene came out pixel for pixel the same, since nothing in it sits
behind the glass, which is exactly why the shortcut had gone unnoticed; the
test adds a ball there to see it. What is still missing is caustics, the
bright spot real glass focuses onto the floor, which would mean following
light from the lamp rather than back from the eye.

## Every surface is a mirror at a glancing angle

The shiny spheres and the floor used to reflect a fixed share of the light,
whatever the angle. Real surfaces do not: look along a polished floor and it
mirrors the sky near the horizon, though straight down it barely reflects at
all. The glass already used Schlick's approximation for this, so it moved into
its own `schlick(cos, r0)` and every reflective surface uses it, with its
`reflect` value now meaning the share head on. The far floor fades into the
reflected sky and the spheres' edges turn to mirror, with no extra rays.

The test is a black mirror sphere in an empty sky, lit from behind so it shows
nothing of its own. Seen dead centre it must be exactly its head-on share of the
sky behind the eye; seen near its rim, exactly Schlick's share of the sky along
the bounce, over nine tenths. Both compare against `schlick` itself, which would
pass a wrong formula, so one value is also worked by hand: 0.04 + 0.96 x 0.5^5
is 0.07. Changing the fifth power to a fourth was caught only by that line.

Writing this test turned up a crash. With the light exactly opposite the eye,
the halfway vector for the highlight is zero, and normalising it divided by zero.
Since the glass change it had been worked out even where no light lands; it is
now computed only where it is used.


## Triangles, which is what everything else is made of

Spheres are easy, but almost every real model is a mesh of triangles. A
triangle is the points a + u*e1 + v*e2, where e1 and e2 are two of its edges,
and the point is inside when u, v and 1-u-v are all at least zero. Setting that
equal to the ray gives three equations in t, u and v. Moller and Trumbore's
trick is to solve them by Cramer's rule with two cross products, and to give up
as soon as u or v is out of range, before t is ever worked out. The plane the
triangle lies in is never computed at all.

The determinant is zero when the ray runs along the triangle's plane, so that
is a miss. Its sign says which side the ray came from. Renderers that only draw
closed meshes skip back faces by refusing a negative determinant, but here a
shadow ray from the floor meets the pyramid's faces from behind, so both signs
count. The normal comes from the winding: corners listed counter-clockwise, as
seen from outside, give a normal that points out.

The pyramid has four sides and no base, since the base sits on the floor and
nothing can see it. It made the render 1.68 times slower, timed with and
without it in turn in one process, because every ray now asks nine objects
instead of five, and the full picture went from 53 seconds to 87. A mesh of
thousands of triangles needs something better, which came next.

The checks work the hit out by hand for one triangle, and then compare 3,000
random rays at random triangles with a second method that meets the plane
first and then asks whether the point is on the inner side of all three edges.
Rays within a millionth of an edge are skipped, since the two methods may call
those either way. Ten breakages, and nine fail it. The tenth drops the u > 1
test, which is only an early exit: u + v > 1 rejects the same rays a step later.

The pyramid's shadow check was wrong at first. It looked straight down from
high above, like the sphere's, but that ray landed on the red sphere, and the
difference it measured was the pyramid's reflection in it. Turning off the
pyramid's shadow left the check passing. It now starts just above the floor.

## Meshes and the box tree

A ring made of 1,024 triangles, tested one by one, makes every ray ask 1,034
objects instead of ten. A small render of the scene took 26.4 seconds that
way against 0.28 without the ring. So a `Mesh` keeps its triangles in a tree
of boxes, a bounding volume hierarchy: the root box holds all of them, and
each box splits its triangles in two at the median of their centres, along
the axis where those centres spread widest, until four or fewer are left. A
ray tests a box by slabs: between each pair of parallel faces it is inside
for some stretch of t, and it is inside the box where all three stretches
overlap. Only boxes it enters are opened, and a box that starts further away
than the nearest hit so far is not opened at all. The same render took 0.40
seconds, 66 times faster than the loose triangles and the same picture to the
byte; the ring costs about what two spheres do. The full 640x360 render went
from 87 seconds to 112 on four cores, and is 318 on one, identical either way.

`nearest` asks a mesh for the triangle it hit, not just how far, since the
triangle is what knows the normal and the colour.

Flat triangles make a curved surface look cut from facets. So a triangle can
carry a normal at each corner, and the normal at a point is the three blended
by how near the point is to each corner, worked out from the point itself:
its barycentric weights. The ring gives each corner its true normal from the
torus, and an OBJ file gives them on `vn` lines. The shape is still the flat
triangles, so a shadow ray from near the edge of the lit side can meet the
triangle beside it; at 1,024 triangles that is not visible.

`load_obj` reads the parts of Wavefront OBJ that describe shape: `v` and `vn`
lines and `f` lines, with corners written as `i`, `i/j`, `i//k` or `i/j/k`,
counted from 1, or from the end when negative. A face of four or more corners
is fanned into triangles from its first corner. An index of 0 or past the end
is refused with its line, as is a face of fewer than three corners.

The checks: 2,000 random rays must find, through the tree, the very triangle
that testing all 1,024 finds; every face of the ring must be wound the way
its corner normals point; the blended normal must be each corner's own at the
corner and their average at the centre; a ray straight down onto the ring in
the scene must come back with one of its triangles; and OBJ text using every
corner form, negative indices and a quad must give triangles with exactly the
expected corners. Seven breakages fail it: slab ends not put in order, a box
that leaves out one corner of each triangle, the blend weights swapped, a
negative index one off, index 0 let through, a mesh answering as itself
rather than its triangle, and the ring wound inward. The first run missed
two of them, because the OBJ test only shot a ray at the square, and any
triangle in the same plane passes that; it now checks the corners. Changes
that only make the tree slower, such as splitting on the wrong axis, were not
counted, since every answer stays right.
