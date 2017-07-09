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
    (open c)

to
    (close c)
where
    c is container
must
    (open c)
then
    not (open c)
    (closed c)

to
    (fetch o c)
where
    o is object
    c is container
must
    (in o c)
    (open c)
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
    (open c)
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
    (not-on-ground h)
    not (on-ground h)
    not (have jack)

to
    (jack-down h)
where
    h is hub
must
    (not-on-ground h)
then
    not (not-on-ground h)
    (on-ground h)
    (have jack)

to
    (undo n h)
where
    n is nut
    h is hub
must
    (not-on-ground h)
    (fastened h)
    (have wrench)
    (loose n h)
then
    (have n)
    (unfastened h)
    not (fastened h)
    not (loose n h)

to
    (do-up n h)
where
    n is nut
    h is hub
must
    (have wrench)
    (unfastened h)
    (not-on-ground h)
    (have n)
then
    (loose n h)
    (fastened h)
    not (unfastened h)
    not (have n)

to
    (remove-wheel w h)
where
    w is wheel
    h is hub
must
    (not-on-ground h)
    (on w h)
    (unfastened h)
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
    (unfastened h)
    (not-on-ground h)
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
    (not-inflated w)
    (intact w)
then
    not (not-inflated w)
    (inflated w)

to
    cuss
then
    not annoyed
""")

fixit_1 = fixit_domain.substitute("""
object: wrench jack pump the-hub nuts wheel1 wheel2
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
(not-inflated wheel2)
(unlocked boot)
(fastened the-hub)
#(closed boot)
(open boot)
""",
goal="""
(on wheel2 the-hub)
(in wheel1 boot)
(inflated wheel2)
(in wrench boot)
(in jack boot)
(in pump boot)
(tight nuts the-hub)
#(closed boot)
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
(not-inflated wheel2)
(unlocked boot)
(fastened the-hub)
#(closed boot)
(open boot)
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

fixit_2_problem.solve(print_increment=True)
print(fixit_2_problem.log)
