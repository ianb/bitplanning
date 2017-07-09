"""
Parses domain representations, and generates concrete domains
"""
import re
import itertools
from domain import (
    ConcreteDomain, State, Constraint, Action)

class UnboundState:

    is_constraint = is_action = False
    is_state = True

    def __init__(self, name=None, where=None):
        self.name = name
        self.where = where
        self.pos = "name"

    def add_line(self, line):
        if line == "where":
            if not self.name:
                raise Exception("No name for state")
            self.pos = "where"
            self.where = Where()
            return
        if self.pos == "where":
            self.where.add_line(line)
            return
        elif self.pos == "name":
            if self.name:
                raise Exception("Name already set")
            self.name = line
        else:
            assert False

    def finish(self):
        if not self.name:
            raise Exception("State without name")
        if self.where and not self.where.clauses:
            raise Exception("Empty where in state")
        self.pos = None

    def expand(self, bindings):
        if not self.where:
            return [State(self.name)]
        var_sets = self.where.expand(bindings)
        result = []
        for var_set in var_sets:
            result.append(State(var_set.sub(self.name)))
        return result


class UnboundConstraint:

    is_state = is_action = False
    is_constraint = True

    def __init__(self, state=None, then=None, where=None):
        self.state = state
        self.then = then or []
        self.where = where
        self.pos = "state"

    def add_line(self, line):
        if line == "then":
            if not self.state:
                raise Exception("Got if/then without state name")
            self.pos = "then"
            return
        if line == "where":
            if not self.state:
                raise Exception("Got if/where without if state")
            self.pos = "where"
            return
        if self.pos == "state":
            if self.state:
                raise Exception("More than one name for state (%r then %r)" % (self.state, line))
            self.state = line
        elif self.pos == "then":
            self.then.append(line)
        elif self.pos == "where":
            if not self.where:
                self.where = Where()
            self.where.add_line(line)
        else:
            assert False

    def finish(self):
        if not self.state:
            raise Exception("No state name given in constraint")
        elif not self.then:
            raise Exception("No conclusions given in constraint")
        self.pos = None

    def expand(self, bindings):
        var_sets = self.where.expand(bindings)
        result = []
        for var_set in var_sets:
            result.append(Constraint(
                var_set.sub(self.state),
                [var_set.sub(t) for t in self.then]))
        return result

class UnboundAction:

    is_state = is_constraint = False
    is_action = True

    def __init__(self, action=None, must=None, then=None, where=None):
        self.action = action
        self.must = must or []
        self.then = then or []
        self.where = where
        self.pos = "action"

    def add_line(self, line):
        if line == "must":
            if not self.action:
                raise Exception("Got must without action name")
            self.pos = "must"
            return
        elif line == "then":
            if not self.action:
                raise Exception("Got then without action name")
            self.pos = "then"
            return
        elif line == "where":
            if not self.action:
                raise Exception("Got where without action name")
            self.pos = "where"
            return
        if self.pos == "action":
            if self.action:
                raise Exception("Got more than one action name (%r then %r)" % (self.action, line))
            self.action = line
        elif self.pos == "must":
            self.must.append(line)
        elif self.pos == "then":
            self.then.append(line)
        elif self.pos == "where":
            if not self.where:
                self.where = Where()
            self.where.add_line(line)
        else:
            assert False

    def finish(self):
        if not self.action:
            raise Exception("No action name")
        if not self.then:
            raise Exception("No action conclusions")
        self.pos = None

    def expand(self, bindings):
        if not self.where:
            return [Action(self.action, self.must, self.then)]
        var_sets = self.where.expand(bindings)
        result = []
        for var_set in var_sets:
            result.append(Action(
                var_set.sub(self.action),
                [var_set.sub(t) for t in self.must],
                [var_set.sub(t) for t in self.then]))
        return result

class Where:

    is_re = re.compile(r'^(\w+)\s+is\s+(\w+)$')
    not_equal_re = re.compile(r'^(\w+)\s*!=\s*(\w+)$')

    def __init__(self, clauses=None):
        self.clauses = clauses or []

    def add_line(self, line):
        match = self.is_re.search(line)
        if match:
            self.clauses.append((match.group(1), 'is', match.group(2)))
            return
        match = self.not_equal_re.search(line)
        if match:
            self.clauses.append((match.group(1), '!=', match.group(2)))
            return
        raise Exception("Cannot understand where clause: %s" % line)

    def expand(self, bindings):
        not_equals = []
        var_sources = []
        for clause in self.clauses:
            if clause[1] == "!=":
                not_equals.append((clause[0], clause[2]))
            elif clause[1] == "is":
                var_sources.append((clause[0], clause[2]))
            else:
                assert False
        assignments = itertools.product(
            *[[(name, value) for value in bindings[binding_name]]
              for name, binding_name in var_sources])
        assignments = [dict(item) for item in assignments]
        for not_equal_1, not_equal_2 in not_equals:
            assignments = [item for item in assignments
                           if item[not_equal_1] != item[not_equal_2]]
        assignments = [VarSub(item) for item in assignments]
        return assignments

class VarSub:

    def __init__(self, assignments):
        self.assignments = assignments

    def sub(self, string):
        for name in self.assignments:
            regex = re.compile(r'\b%s\b' % re.escape(name))
            string = regex.sub(self.assignments[name], string)
        return string

    def __repr__(self):
        return '<VarSub assignments={}>'.format(self.assignments)

class Domain:
    """Represents a domain: a world and actions, but without concrete/bound
    variables.
    """

    def __init__(self, name, domain_string):
        self.name = name
        self.parse_domain_string(domain_string)

    keywords = {
        "state": (UnboundState, "states"),
        "if": (UnboundConstraint, "constraints"),
        "to": (UnboundAction, "actions"),
    }

    def parse_domain_string(self, string):
        current_expr = None
        exprs = {
            "states": [],
            "constraints": [],
            "actions": [],
        }
        for line in string.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line in self.keywords:
                # Start a new expression
                if current_expr:
                    current_expr.finish()
                ExprClass, bucket = self.keywords[line]
                current_expr = ExprClass()
                exprs[bucket].append(current_expr)
                continue
            if not current_expr:
                raise Exception("Unexpected line: %r" % line)
            current_expr.add_line(line)
        current_expr.finish()
        self.expressions = exprs

    def _type_names(self):
        """Get all the names of types (e.g., "plane")"""
        names = set()
        for expr in self.exprs:
            where = getattr(expr, "where", None)
            if where:
                for clause in where.clauses:
                    if clause[1] == "is":
                        names.add(clause[2])
        return names

    def substitute(self, bindings):
        """Substitute all the unbound variables in the definition, returning
        a ConcreteDomain.

        bindings can be lines of `variables: V1 V2 V3`, or `{"variables": ["V1", "V2", "V3"]}`
        """
        bindings = self._convert_bindings(bindings)
        names = set(bindings.keys())
        if names != self._type_names():
            raise Exception("Missing some type names: %r" % self._type_names())
        return ConcreteDomain(self.name, self.exprs, bindings)

    def problem(self, *, bindings=None, start, goal):
        """Bind variables and generate a problem at the same time"""
        domain = self.substitute(bindings or {})
        return domain.problem(start=start, goal=goal)

    def _convert_bindings(self, bindings):
        if isinstance(bindings, str):
            result = {}
            last_var = None
            for line in bindings.splitlines():
                line = re.sub(r'#.*', "", line)
                match = re.search(r'^(\w+):', line)
                if match:
                    last_var = match.group(1)
                    line = line[len(match.group(0)):].strip()
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if not last_var:
                    raise Exception("Variable value without 'name:': %r" % line)
                values = [value.strip(",").strip(";") for value in line.split()]
                values = [value for value in values if value]
                existing = result.setdefault(last_var, [])
                existing.extend(values)
            bindings = result
        return bindings
