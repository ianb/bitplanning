"""
Runs the fixit examples from http://www.cs.cmu.edu/afs/cs.cmu.edu/usr/avrim/Planning/Graphplan/

The algorithm can't solve these examples. You can see what it tries by running
this file (Jupyter doesn't handle the ongoing output that well)
"""

from parsedomain import Domain

fixit_domain = Domain("fixit", """
to
    (open c)
where
    c is container
must
    (unlocked c)
    (closed c)
then
    not (closed c)

to
    (close c)
where
    c is container
must
    not (closed c)
then
    (closed c)

to
    (fetch o c)
where
    o is object
    c is container
must
    (in o c)
    not (closed c)
then
    not (in o c)
    (have o)

to
    (put-away o c)
where
    o is object
    c is container
must
    (have o)
    not (closed c)
then
    (in o c)
    not (have o)

to
    (loosen n h)
where
    n is nut
    h is hub
must
    (have wrench)
    (tight n h)
    (on-ground h)
then
    (loose n h)
    not (tight n h)

to
    (tighten n h)
where
    n is nut
    h is hub
must
    (have wrench)
    (loose n h)
    (on-ground h)
then
    (tight n h)
    not (loose n h)

to
    (jack-up h)
where
    h is hub
must
    (on-ground h)
    (have jack)
then
    not (on-ground h)
    not (have jack)

to
    (jack-down h)
where
    h is hub
must
    not (on-ground h)
then
    (on-ground h)
    (have jack)

to
    (undo n h)
where
    n is nut
    h is hub
must
    not (on-ground h)
    (fastened h)
    (have wrench)
    (loose n h)
then
    (have n)
    not (fastened h)
    not (loose n h)

to
    (do-up n h)
where
    n is nut
    h is hub
must
    (have wrench)
    not (fastened h)
    not (on-ground h)
    (have n)
then
    (loose n h)
    (fastened h)
    not (have n)

to
    (remove-wheel w h)
where
    w is wheel
    h is hub
must
    not (on-ground h)
    (on w h)
    not (fastened h)
then
    (have w)
    (free h)
    not (on w h)

to
    (put-on-wheel w h)
where
    w is wheel
    h is hub
must
    (have w)
    (free h)
    not (fastened h)
    not (on-ground h)
then
    (on w h)
    not (free h)
    not (have w)

to
    (inflate w)
where
    w is wheel
must
    (have pump)
    not (inflated w)
    (intact w)
then
    (inflated w)

# Encompasses:
# (loosen n h) (jack-up h) (undo n h) (remove-wheel w h) (jack-down h)
to
    (entire-take-off-wheel w h)
where
    w is wheel
    h is hub
    n is nut
must
    never-do
    (on w h)
    (have wrench)
    (tight n h)
    (fastened h)
    (on-ground h)
    (have jack)
then
    (free h)
    (have w)
    (have n)
    not (fastened h)
    not (on w h)
    not (tight n h)

# Encompases:
# (jack-up h) (put-on-wheel w h) (do-up n h) (jack-down h) (tighten n h)
to
    (entire-put-on-wheel w h)
where
    w is wheel
    h is hub
    n is nut
must
    never-do
    (have w)
    (free h)
    not (fastened h)
    (have n)
    (have wrench)
    (have jack)
    (on-ground h)
then
    not (have w)
    not (free h)
    (fastened h)
    not (have n)
    (tightened n h)

# Encompasses:
# optionally open/close boot, (fetch jack boot) (fetch wrench boot) (fetch pump boot)
to
    (fetch-tools)
must
    not (have jack)
    not (have wrench)
    not (have pump)
    (in jack boot)
    (in wrench boot)
    (in pump boot)
then
    (have jack)
    (have wrench)
    (have pump)
    not (in jack boot)
    not (in wrench boot)
    not (in pump boot)

# Encompasses:
# optionally open/close boot, (put-away wrench boot) (put-away jack boot) (put-away pump boot)
to
    (put-away-tools)
must
    (have jack)
    (have wrench)
    (have pump)
then
    not (have jack)
    not (have pump)
    not (have wrench)
    (in jack boot)
    (in pump boot)
    (in wrench boot)

if
    (have o)
where
    o is object
    c is container
then
    not (in o c)

if
    (in o c)
where
    o is object
    c is container
then
    not (have o)

if
    (fastened h)
where
    h is hub
then
    not (free h)

if
    (loose n h)
where
    n is nut
    h is hub
then
    not (free h)
    (fastened h)

if
    (tight n h)
where
    n is nut
    h is hub
then
    not (loose n h)
    not (free h)
    (fastened h)

if
    (have n)
where
    n is nut
    h is hub
then
    not (loose n h)
    not (tight n h)
""")

fixit_1 = fixit_domain.substitute("""
object: wrench jack pump nuts wheel1 wheel2
hub: the-hub
nut: nuts
container: boot
wheel: wheel1 wheel2
""")


fixit_1_problem = fixit_1.problem(
start="""
default_false
(intact wheel2)
(in jack boot)
(in pump boot)
(in wheel2 boot)
(in wrench boot)
(on wheel1 the-hub)
(on-ground the-hub)
(tight nuts the-hub)
not (inflated wheel2)
(unlocked boot)
(fastened the-hub)
(closed boot)
""",
goal="""
(on wheel2 the-hub)
(in wheel1 boot)
(inflated wheel2)
(in wrench boot)
(in jack boot)
(in pump boot)
(tight nuts the-hub)
(closed boot)
""")

#fixit_1_problem.solve(print_increment=True)

fixit_2_problem = fixit_domain.problem(
bindings="""
object: wrench jack pump the-hub nuts wheel1 wheel2
hub: the-hub
nut: nuts
container: boot
wheel: wheel1 wheel2
""",
start="""
default_false
(intact wheel2)
(in jack boot)
(in pump boot)
(in wheel2 boot)
(in wrench boot)
(on wheel1 the-hub)
(on-ground the-hub)
(tight nuts the-hub)
not (inflated wheel2)
(unlocked boot)
(fastened the-hub)
#(closed boot)
""",
goal="""
(tight nuts the-hub)
#(closed boot)
(in jack boot)
(in pump boot)
(in wheel1 boot)
(in wrench boot)
(inflated wheel2)
(on wheel2 the-hub)
""")

problem = fixit_1_problem

print(problem.domain.as_str(bits=True))

try:
    problem.solve(pause=True, print_increment=True)
except KeyboardInterrupt:
    print("Break!\n\n")
    problem.log.abort_solution()
    problem.log.activity = []
print(problem.log)
