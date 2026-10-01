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

