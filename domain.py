"""
Representation and solving of problem domains

Generally `parsedomain.Domain` is used to create domains, but that generates
the `ConcreteDomain` in this module, which is where all the work is done.
"""
from bitmask import BitMask, IncompatibleAdd
import time
import re

class IncompatibleConstraints(Exception):
    def __init__(self, message, *, constraint, init_state, then_state, then_mask, action=None):
        self.constraint = constraint
        self.init_state = init_state
        self.then_state = then_state
        self.then_mask = then_mask
        self.action = action
    def __str__(self):
        s = 'Constraint puts state into conflict; constraint={}, state={}, then clause={}/{}'.format(
            self.constraint, self.init_state.mask_str(), self.then_state, self.then_mask.mask_str())
        if self.action:
            s += ' while constraining action: {}/must={}/then={}'.format(
                self.action, self.action.must_bits.mask_str(), self.action.then_bits.mask_str())
        return s


class State:
    """States are atomic true/false reflections of the planning world

    States only really have a name, an opaque string which identifies the
    state. UnboundState uses substitution to *generate* these states, but
    they are never parsed after that."""

    def __init__(self, name):
        self.name = name

    def repr(self):
        return '[%s]' % self.name


class Constraint:
    """
    A constraint indicates how states relate to each other.

    A `state` implies a list of other states (with a true/false state for
    each state)
    """

    def __init__(self, state, then):
        self.state = state
        self.then = then

    def __repr__(self):
        return '[%s ⇒ %s]' % (self.state, '∧'.join(self.then))


class Action:
    """Represents an action.

    Actions have a name, a list of precondition states (`must`), and a list
    of results (`then`).

    Constraints will be applied to `must`, so that all implications of the
    preconditions will be reflected.
    """

    def __init__(self, action, must, then):
        self.action = action
        self.must = must
        self.then = then

    def is_mutex(self, other_action):
        """Is this action mutex with another action?

        This means that this action can't happen concurrently with another
        action, we either have to specify that the other action comes before
        or after this action."""
        if self.must_bits.conflicts(other_action.must_bits):
            return True
        ## FIXME: I'm not sure if this conflict matters:
        ## (specifically in the case when we don't care about
        ## the conflicting bits)
        if self.then_bits.conflicts(other_action.then_bits):
            return True
        if self.must_bits.conflicts(other_action.then_bits):
            return True
        if self.then_bits.conflicts(other_action.must_bits):
            return True
        return False

    def __repr__(self):
        return '<Action %s>' % self.action

class ConcreteDomain:
    """Represents a problem domain, with fully bound variables.
    """

    def __init__(self, name, exprs, bindings):
        self.name = name
        self.bindings = bindings
        self.constraints = [
          item
          for expr in exprs['constraints']
          for item in expr.expand(bindings)
        ]
        self.actions = [
          item
          for expr in exprs['actions']
          for item in expr.expand(bindings)
        ]
        self.states = [
          item
          for expr in exprs['states']
          for item in expr.expand(bindings)
        ]
        if not self.states:
            # Must be implied states, since none were given
            implied_states = set()
            for action in self.actions:
                old_implied = set(implied_states)
                implied_states.update([
                    state[4:] if state.startswith("not ") else state
                    for state in action.must + action.then])
                #print("Updated", action, "must", action.must, "then", action.then,
                #    "before", len(old_implied), "now", len(implied_states),
                #    "added", implied_states - old_implied)
            self.states = [State(name) for name in implied_states]
        self.states.sort(key=lambda x: x.name)
        for i, state in enumerate(self.states):
            state.domain = self
            state.bit = 1 << i
            state.bit_mask = BitMask(state.bit, state.bit, len(self.states))
        self.state_bits = dict((state.name, state.bit) for state in self.states)
        self.actions.sort(key=lambda x: x.action)
        self.null = BitMask.null(len(self.states))
        for action in self.actions:
            action.domain = self
            action.must_bits = BitMask.null(len(self.states))
            for must in action.must:
                bit = 1
                if must.startswith("not "):
                    bit = 0
                    must = must[4:]
                action.must_bits = action.must_bits.add(self.state_bits[must], bit)
            action.must_bits = self.apply_constraints(action.must_bits)
            action.then_bits = self.null
            for then in action.then:
                bit = 1
                if then.startswith("not "):
                    bit = 0
                    then = then[4:]
                action.then_bits = action.then_bits.add(self.state_bits[then], bit)
            try:
                action.then_bits = self.apply_constraints(action.then_bits)
            except IncompatibleConstraints as e:
                e.action = action
                raise
            action.then_bits = action.then_bits.carry_forward(action.must_bits)
        for action in self.actions:
            action.mutex = set()
            for other_action in self.actions:
                if other_action is action:
                    continue
                if action.is_mutex(other_action):
                    action.mutex.add(other_action)

    def get_action_by_name(self, action_name):
        for action in self.actions:
            if action.action == action_name:
                return action
        raise KeyError("No action with the name {}".format(action_name))

    def goal(self, state_strings):
        """
        Creates a goal BitMask, given a line-separated string or list of
        strings with state names (and 'not' prefixes as appropriate)
        """
        init_state, options = self._parse_state_strings(state_strings)
        return init_state

    def _parse_state_strings(self, state_strings):
        options = {}
        if isinstance(state_strings, str):
            state_strings = [
              line.strip()
              for line in state_strings.splitlines()
              if line.strip() and not line.strip().startswith("#")]
        init_state = BitMask.null(len(self.states))
        for set_state in state_strings:
            if set_state == "default_false":
                options['default_false'] = True
                continue
            bit = 1
            if set_state.startswith("not "):
                bit = 0
                set_state = set_state[4:]
            set_state_bit = self.state_bits[set_state]
            if init_state.is_set(set_state_bit):
                raise Exception("Tried to set state twice: %s" % set_state)
            init_state = init_state.add(set_state_bit, bit)
        return init_state, options

    def create_start_state(self, state_strings, default_false=False):
        """Creates an initial state given a set of state strings (or a
        line-separated string with states)

        Constraints will be applied to fill out states. If `default_false`
        is true, or `default_false` is in the action strings, then all
        not-specified states will be set to false.
        """
        init_state, options = self._parse_state_strings(state_strings)
        default_false = options.get('default_false', default_false)
        init_state = self.apply_constraints(init_state)
        if default_false:
            for state in self.states:
                if not init_state.is_set(state.bit):
                    init_state = init_state.add(state.bit, 0)
        if not init_state.all_set():
            not_set = []
            for state in self.states:
                if not init_state.is_set(state.bit):
                    not_set.append(state.name)
            raise Exception("set_state did not set all values: {}, missing: {}".format(
                init_state.mask_str(), "; ".join(not_set)))
        return init_state

    def apply_constraints(self, init_state):
        """Apply all the domain constraints to some given state.

        It is an error if a constraint is in conflict with the state.
        """
        for constraint in self.constraints:
            bit = 1
            state = constraint.state
            if state.startswith("not "):
                bit = 0
                state = state[4:]
            state_bit = self.state_bits[state]
            if init_state.known_and_matches(state_bit, bit):
                for then_state in constraint.then:
                    then_bit = 1
                    if then_state.startswith("not "):
                        then_bit = 0
                        then_state = then_state[4:]
                    then_bit_pos = self.state_bits[then_state]
                    try:
                        init_state = init_state.add(then_bit_pos, then_bit)
                    except IncompatibleAdd:
                        then_mask = self.null.add(then_bit_pos, then_bit)
                        raise IncompatibleConstraints(
                            "Constraint puts state info conflict",
                            constraint=constraint,
                            init_state=init_state,
                            then_state=then_state,
                            then_mask=then_mask)
        return init_state

    def strict_accomplishment_actions(self, goal):
        """Return a list of actions that satisfy something in the goal, and
        do not invalidate anything in the goal.
        """
        actions = []
        for action in self.actions:
            important_then_bits = action.then_bits.without_matching(action.must_bits)
            if not action.then_bits.conflicts(goal) and important_then_bits.accomplishes_something(goal) and not action.must_bits.unset_from_action(action.then_bits, force=True).conflicts(goal):
                actions.append(action)
        return actions

    def strict_accomplishment_pools(self, goal):
        """Create a list of ActionPools of actions that accomplish something
        for the goal, do not invalidate anything in the goal, and where none
        of the actions are mutually exclusive.

        All (unordered) combinations of applicable actions are found.
        """
        assert not goal.is_null()
        actions = self.strict_accomplishment_actions(goal)
        def group_actions(included_actions, possible_actions, remaining_goal):
            if not possible_actions:
                return
            next_action = possible_actions[0]
            rest_actions = possible_actions[1:]
            if not any(next_action in included.mutex for included in included_actions):
                if next_action.then_bits.accomplishes_something(remaining_goal):
                    #print("Adding", next_action.action, 'to', [a.action for a in included_actions], 'in order to', remaining_goal)
                    next_remaining = remaining_goal.unset_from_action(next_action.then_bits)
                    next_included = included_actions + [next_action]
                    yield ActionPool(next_included)
                    yield from group_actions(next_included, rest_actions, next_remaining)
            yield from group_actions(included_actions, rest_actions, remaining_goal)
        return list(group_actions([], actions, goal))

    def score_accomplishment_pool(self, pool, goal, start):
        """Scores an ActionPool, given a goal and initial state.

        This returns a tuple, with each item being a different tie-breaker"""
        remaining = goal.unset_from_action(pool.then_bits)
        requirement = pool.must_bits
        union = BitMask.all_union([remaining, requirement])
        if start:
            start_score = start.difference(union).count_set()
        else:
            start_score = 0
        if hasattr(pool, "action_count"):
            count_score = pool.action_count()
        else:
            count_score = 0
        score = (remaining.count_set(), union.count_set(), start_score, count_score)
        return score

    def problem(self, *, start, goal):
        """Create a Problem given a start and goal
        """
        start_state = self.create_start_state(start)
        goal = self.goal(goal)
        return Problem(self, start_state, goal)

    def __str__(self):
        return self.as_str(bits=False)

    def _repr_html_(self):
        import tempita
        return tempita.HTMLTemplate("""
        <h3>{{self.name}}</h3>
        <div style="display: flex; flex-wrap: wrap">
          <div style="margin; 1em">
            <table>
              <tr>
                <th>State name</th>
                <th>BitMask</th>
              {{for state in self.states}}
                <tr>
                  <td>{{state.name}}</td>
                  <td><code>{{ state.bit_mask.mask_str() }}</code></td>
                </tr>
              {{endfor}}
            </table>
          </div>
          {{for action in self.actions}}
            <div style="border: 1px solid #99f; border-radius: 2px; min-width: 20em; margin: 1em; flex: 1 0 auto">
              <div><strong>{{action.action}}</strong></div>
              <div>
                Must:
                  <code style="white-space: nowrap">{{action.must_bits.mask_str()}}</code>
                  {{"; ".join(action.must)}}<br>
                Then:
                  <code style-"white-space: nowrap">{{action.then_bits.mask_str()}}</code>
                  {{"; ".join(action.then)}}
              </div>
            </div>
          {{endfor}}
        </div>
        """).substitute({"self": self})

    def as_str(self, bits=False, mutex=False):
        lines = ['Domain {}'.format(self.name)]
        for name in sorted(self.bindings):
            lines.append('  {} = {}'.format(name, '; '.join(sorted(self.bindings[name]))))
        lines.append('States:')
        if not bits:
            lines.append('  ')
            for state in self.states:
                if len(lines[-1]) + len(state.name) < 78:
                    if lines[-1].strip():
                        lines[-1] += '; '
                    lines[-1] += state.name
                else:
                    lines.append('  {}'.format(state.name))
        else:
            for state in self.states:
                lines.append('  {} {}'.format(state.bit_mask.mask_str(), state.name))
        lines.append('Actions:')
        for action in sorted(self.actions, key=lambda x: x.action):
            lines.append('  {}:'.format(action.action))
            lines.append('    must: {}'.format('; '.join(action.must)))
            if bits:
                lines.append('      {}'.format(action.must_bits.mask_str()))
            lines.append('    then: {}'.format('; '.join(action.then)))
            if bits:
                lines.append('      {}'.format(action.then_bits.mask_str()))
                lines.append('      {}'.format(action.then_bits.without_matching(action.must_bits).mask_str()))
            if mutex:
                lines.append('    mutex: {}'.format('; '.join(sorted([a.action for a in action.mutex]))))
        return '\n'.join(lines)


class ActionPool:
    """A collection of non-conflicting actions that can occur simultaneously
    (or at least in any order)
    """

    def __init__(self, actions):
        for i, a in enumerate(actions):
            for a2 in actions[i + 1:]:
                assert a is not a2
                assert a2 not in a.mutex
                assert a not in a2.mutex
        self.actions = actions
        self.must_bits = BitMask.all_union([a.must_bits for a in actions])
        self.then_bits = BitMask.all_union([a.then_bits for a in actions])

    def __contains__(self, action):
        if isinstance(action, ActionPool):
            return False
        if not isinstance(action, Action):
            raise TypeError("ActionPools can only contain Actions")
        return action in self.actions

    def __repr__(self):
        return '<ActionPool %s>' % (' '.join(a.action for a in self.actions))


class ActionSequence:
    """A sequence of ordered actions

    Each action is a pool (pools may have only one real action), and typically
    the last action is a GoalPool
    """

    def __init__(self, actions, null):
        self.null = null
        self.must_bits = null
        self.then_bits = null
        for action in reversed(actions):
            assert not action.then_bits.conflicts(self.must_bits)
            current_must_bits = self.must_bits.except_satisfied_by(action.then_bits)
            assert not action.must_bits.conflicts(current_must_bits)
            self.must_bits = action.must_bits.union(current_must_bits)
        for action in actions:
            assert not action.must_bits.conflicts(self.then_bits)
            self.then_bits = action.then_bits.carry_forward(self.then_bits)
        self.actions = actions

    def with_prepend(self, action):
        """Returns another ActionSequence, with the new action at the beginning"""
        return ActionSequence([action] + self.actions, self.null)

    def action_count(self):
        """Total number of actions (including a count of actions inside pools)"""
        return sum(len(pool.actions) for pool in self.actions)

    def __contains__(self, action):
        if not isinstance(action, (Action, ActionPool)):
            raise TypeError("An ActionSequence can only contain Action and ActionPool")
        if action in self.actions:
            return True
        return any(action in action_pool for action_pool in self.actions)

    def __repr__(self):
        pools = [' '.join(a.action for a in pool.actions) for pool in self.actions]
        return '<ActionSequence %s>' % (': '.join(pools))

    def __str__(self):
        lines = ['Sequence:']
        lines.append('  must: {}'.format(self.must_bits.mask_str()))
        lines.append('  then: {}'.format(self.then_bits.mask_str()))
        lines.append('  sequence:')
        for pool in self.actions:
            lines.append('    {}'.format(pool))
        return '\n'.join(lines)

    def _repr_html_(self, *, header=True):
        import tempita
        parts = {}
        must_bits = self.null
        then_bits = self.null
        for action in reversed(self.actions):
            current_must_bits = must_bits.except_satisfied_by(action.then_bits)
            must_bits = action.must_bits.union(current_must_bits)
            parts[action] = {"must_bits": must_bits}
            parts[action]["action"] = action
            if isinstance(action, GoalPool):
                parts[action]["repr"] = "Goal"
            elif len(action.actions) > 1:
                parts[action]["repr"] = "In any order: {}".format(", ".join(a.action for a in action.actions))
            else:
                parts[action]["repr"] = action.actions[0].action
        for action in self.actions:
            then_bits = action.then_bits.carry_forward(then_bits)
            parts[action]["then_bits"] = then_bits
        parts[self.actions[0]]["must_style"] = "font-weight: bold"
        parts[self.actions[-1]]["then_style"] = "font-weight: bold"
        parts_seq = [parts[action] for action in self.actions]
        return tempita.HTMLTemplate("""
        {{if header}}
          <h3>Action sequence:</h3>
        {{endif}}
        <ol>
          {{for info in parts_seq}}
            <li>{{info["repr"]}}
              <ul>
                <li>Must:
                  <code style="{{info.get('must_style')}}">{{info["must_bits"].mask_str()}}</code></li>
                <li>Then:
                  <code style="{{info.get('then_style')}}">{{info["then_bits"].mask_str()}}</code></li>
              </ul>
            </li>
          {{endfor}}
        </ol>
        """).substitute({"self": self, "parts_seq": parts_seq, "header": header})

class GoalPool:
    """Represents a goal, in a way that it appears like an ActionPool
    """

    # This satisfies the ActionPool interface:
    actions = ()

    def __init__(self, goal):
        self.must_bits = goal
        self.then_bits = BitMask.null(goal._width)

    def __contains__(self, action):
        return False

    def __repr__(self):
        return '<Goal %s>' % self.must_bits.mask_str()

class Problem:
    """Represents a problem: a concrete domain, with a initial start state, and a goal
    """

    def __init__(self, domain, start_state, goal):
        self.domain = domain
        self.start_state = start_state
        self.goal = goal
        self._has_solution = None

    @property
    def has_solution(self):
        if self._has_solution is None:
            raise ReferenceError(".solve() has not yet been called")
        return self._has_solution

    def _print_pause_help(self):
        print("Paused; Enter to continue, P to unpause (but print), Q to run quietly")
        print("  Enter a number to pause only ever N increments.")
        print("  Enter 'watch ActionName' to pause when seen")

    def solve(self, *, pause=False, print_increment=None, no_activity=False):
        self.log = ProblemLog(self.start_state, self.goal, self.domain, no_activity=no_activity)
        seen = set()
        watch_for_actions = []
        seen_help = False
        blank_seq = ActionSequence([GoalPool(self.goal)], null=self.domain.null)
        frontier = [(blank_seq, self.domain.score_accomplishment_pool(blank_seq, self.goal, self.start_state))]
        if pause and print_increment is None:
            print_increment = True
        count = 0
        pause_every = 0
        while frontier:
            count += 1
            self.log.pick_frontier(frontier_length=len(frontier))
            if seen and not count % 5:
                #print("Random...")
                best, best_score = frontier.pop(len(frontier)//2)
            else:
                best, best_score = frontier.pop(0)
            if best.must_bits in seen:
                self.log.skip_already_seen(action=best, score=best_score)
                continue
            seen.add(best.must_bits)
            self.log.attempt_solution(action=best, score=best_score, alternative_count=len(frontier))
            if print_increment and (not pause_every or not count % pause_every):
                self.log.print_increment()
            if pause and (not pause_every or not count % pause_every):
                try:
                    if not seen_help:
                        self._print_pause_help()
                        seen_help = True
                    result = input("> ").strip()
                    if result == "?" or result == "help":
                        self._print_pause_help()
                    if result.upper() == "P":
                        pause = False
                    if result.upper() == "Q":
                        pause = False
                        print_increment = False
                    if re.search(r'^\d+$', result):
                        pause_every = int(result)
                    if result.startswith("watch "):
                        watch_action_name = result.split(None, 1)[1]
                        watch_for_actions.append(self.domain.get_action_by_name(watch_action_name))
                        print("Watching for {} (use P to cruise until we find it".format(watch_for_actions[-1]))
                except KeyboardInterrupt:
                    print("Aborting search")
                    self.log.abort_solution()
                    return None
            self.log.goal_tests += 1
            if not self.start_state.conflicts(best.must_bits) and best.then_bits.satisfies(self.goal):
                self.log.solution(action=best, remaining_count=len(frontier), expansions=len(seen))
                self.solution = best
                self._has_solution = True
                return best
            new_seqs = [best.with_prepend(pool) for pool in self.domain.strict_accomplishment_pools(best.must_bits)]
            self.log.expansions += 1
            self.log.new_nodes += len(new_seqs)
            if not new_seqs:
                self.log.no_accomplishments(action=best)
            if watch_for_actions:
                if any(a in a_seq for a in watch_for_actions for a_seq in new_seqs):
                    print("Found action, entering pause mode")
                    print("Basis sequence:")
                    print(best)
                    for i, seq in enumerate(s for s in new_seqs if any(a in s for a in watch_for_actions)):
                        print("Derived sequence {}:".format(i + 1))
                        print(seq)
                    input("> ")
                    pause = True
            frontier.extend([
                (seq, self.domain.score_accomplishment_pool(seq, self.goal, self.start_state))
                for seq in new_seqs
                if seq.must_bits not in seen])
            frontier.sort(key=lambda x: x[1])
        self.log.no_solution()
        self._has_solution = False
        return None

class ProblemLog:
    """A kind-of-log object that belongs to Problems, and describes how the solution
    was found
    """

    def __init__(self, start_state, goal, domain, *, no_activity=False):
        self.seen_count = self.skipped_count = self.total_count = 0
        self.activity = []
        self.start_state = start_state
        self.goal = goal
        self.domain = domain
        self.start = time.time()
        self.activity_increment = 0
        self.no_activity = no_activity
        # Equivalent to succs in InstrumentedProblem
        self.expansions = 0
        # Equivalent to goal_tests
        self.goal_tests = 0
        # Equivalent to states
        self.new_nodes = 0
    def add_activity(self, item):
        if not self.no_activity:
            self.activity.append(item)
    def print_increment(self):
        lines = []
        for item in self.activity[self.activity_increment:]:
            line = str(item)
            if line:
                lines.append(line)
        self.activity_increment = len(self.activity)
        print("\n".join(lines))
    def pick_frontier(self, *, frontier_length):
        self.total_count += 1
        self.add_activity(LogPickFrontier(frontier_length))
    def skip_already_seen(self, *, action, score):
        self.skipped_count += 1
        self.add_activity(LogSkipAlreadySeen(action, score))
    def attempt_solution(self, *, action, score, alternative_count):
        self.seen_count += 1
        self.add_activity(LogAttemptSolution(action, score, alternative_count))
    def no_accomplishments(self, *, action):
        self.add_activity(LogNoAccomplishments(action))
    def solution(self, *, action, remaining_count, expansions):
        self.add_activity(LogSolution(action, remaining_count, expansions))
        self.end = time.time()
    def no_solution(self):
        self.add_activity(LogNoSolution())
        self.end = time.time()
    def abort_solution(self):
        self.end = time.time()
    def __str__(self, short=False):
        lines = ['Problem solution log:']
        lines.append('  Tried {} sequences, skipped {}, explored {}'.format(
            self.total_count, self.skipped_count, self.seen_count))
        lines.append('  Took {:0.5} seconds'.format(self.end - self.start))
        lines.append('  Expansions: {} Goal tests: {} New nodes: {}'.format(
            self.expansions, self.goal_tests, self.new_nodes))
        if short:
            return '\n'.join(lines)
        lines.append('  Starting state: {}'.format(self.start_state.mask_str()))
        lines.append('  Goal state:     {}'.format(self.goal.mask_str()))
        activities = self.activity
        if self.activity_increment:
            activities = activities[-1:]
        for log in activities:
            line = str(log)
            if line:
                lines.append("    " + line)
        return '\n'.join(lines)
    def _repr_html_(self, short=False):
        import tempita
        htmls = []
        for log in self.activity:
            if hasattr(log, "_repr_html_"):
                htmls.append({"html": log._repr_html_()})
            else:
                text = str(log)
                if text:
                    htmls.append({"text": text})
        start_states = []
        goal_states = []
        for state in self.domain.states:
            if self.start_state.is_set(state.bit_mask._bits) and not self.start_state.conflicts(state.bit_mask):
                start_states.append(state.name)
            if self.goal.is_set(state.bit_mask._bits) and not self.goal.conflicts(state.bit_mask):
                goal_states.append(state.name)
        return tempita.HTMLTemplate("""
        {{if not short}}
        <aside style="float: right; background-color: #ddd; padding: 0.75em">
          <div>
            Start state:<br>
            <code>{{self.start_state.mask_str()}}</code>
              <ul style="list-style: none; margin: 0">
                {{for item in start_states}}
                  <li>{{item}}</li>
                {{endfor}}
              </ul>
          </div>
          <div>
            Goal:<br>
            <code>{{self.goal.mask_str()}}</code>
              <ul style="list-style: none; margin: 0">
                {{for item in goal_states}}
                  <li>{{item}}</li>
                {{endfor}}
              </ul>
          </div>
        </aside>
        {{endif}}
        <h3>Problem solution log:</h3>
        <ul style="list-style: none">
          <li>Tried: <strong>{{self.total_count}}</strong></li>
          <li>Skipped: <strong>{{self.skipped_count}}</strong> ({{int(100*self.skipped_count/self.total_count)}}%)</li>
          <li>Explored: <strong>{{self.seen_count}}</strong></li>
          <li>Time: <strong>{{"{:0.5}".format(self.end - self.start)}}s</strong></li>
          <li>Expansions: {{self.expansions}}</li>
          <li>Goal tests: {{self.goal_tests}}</li>
          <li>New nodes: {{self.new_nodes}}</li>
        </ul>
        {{if not short}}
        <ol>
          {{for h in htmls}}
            {{if h.get("html")}}
              <li>{{h.get("html") | html}}</li>
            {{else}}
              <li>{{h.get("text")}}</li>
            {{endif}}
          {{endfor}}
        </ol>
        {{endif}}
        """).substitute({"self": self, "htmls": htmls, "start_states": start_states, "goal_states": goal_states, "short": short})
    @property
    def short(self):
        return _ShortRepr(str=self.__str__(short=True), html=self._repr_html_(short=True))

class _ShortRepr:
    def __init__(self, str, html):
        self.str = str
        self.html = html
    def __str__(self):
        return self.str
    def _repr_html_(self):
        return self.html
    def __repr__(self):
        return str(self)

class LogPickFrontier:
    def __init__(self, length):
        self.length = length
    def __str__(self):
        return ''

class LogSkipAlreadySeen:
    def __init__(self, action, score):
        self.action = action
        self.score = score
    def __str__(self):
        return 'Skipped because must={} has been seen: {}'.format(
            self.action.must_bits.mask_str(), self.action)
    def _repr_html_(self):
        return """Skipped adding action {} because must=<code>{}</code> has been seen
        <button style="font-size: 80%; border: none" onclick="
        if (! this.nextSibling.style.display) {{
          this.nextSibling.style.display = 'none';
          this.textContent = 'show action';
        }} else {{
          this.nextSibling.style.display = '';
          this.textContent = 'hide';
        }}
        ">show action</button><div style="display: none">{}</div>
        """.format(
            self.action.actions[0].actions[0].action, self.action.must_bits.mask_str(), self.action._repr_html_(header=False))

class LogAttemptSolution:
    def __init__(self, action, score, alternative_count):
        self.action = action
        self.score = score
        self.alternative_count = alternative_count
    def __str__(self):
        return 'Attempted action of {} alternatives: (score {}) {}'.format(
            self.alternative_count, self.score, self.action)
    def _repr_html_(self):
        return 'Attempted action of {} alternatives: (score <code>{}</code>) {}'.format(
            self.alternative_count, self.score, self.action._repr_html_(header=False))

class LogNoAccomplishments:
    def __init__(self, action):
        self.action = action
    def __str__(self):
        return 'No actions can accomplish the prerequisite {} from: {}'.format(
            self.action.must_bits.mask_str(), self.action)
    def _repr_html_(self):
        return 'No actions can accomplish the prerequisite <code>{}</code> from: {}'.format(
            self.action.must_bits.mask_str(), self.action._repr_html_(header=False))

class LogSolution:
    def __init__(self, action, remaining_count, expansions):
        self.action = action
        self.remaining_count = remaining_count
        self.expansions = expansions
    def __str__(self):
        return 'Found solution with {} alternatives unexplored: {}'.format(
            self.remaining_count, self.action)
    def _repr_html_(self):
        return 'Found solution with {} alternatives unexplored: {}'.format(
            self.remaining_count, self.action._repr_html_(header=False))

class LogNoSolution:
    def __init__(self):
        pass
    def __str__(self):
        return 'Found no solution'
