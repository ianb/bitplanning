"""
Represents the set of true/false values for states, used throughout the planner.

See `BitMask`
"""

import string

class IncompatibleAdd(Exception):
    """Raised if bitmask.add() would modify the value"""
    pass

class BitMask:
    """Represents a field of bits, with a mask of the bits we care about.

    The values are represented as `self._bits` and the mask is `self._mask`:
    the only bits that matter are those where the mask bit is set to 1.

    BitMasks are treated as immutable, and all methods return new values.

    A BitMask also has a width, though that is only used occasionally for the
    repr() of the BitMask and a small number of other methods.

    Typically you'd create a `BitMask.null(width)` and then modify it.  The null
    BitMask is one where all bits are seen as unimportant (really neither 0 or 1)
    """

    # Instead of using 1/0 (and counting positions), we give each
    # position a letter, with upper-case being 1 and lower-case being 0
    on_names = string.ascii_uppercase
    off_names = string.ascii_lowercase

    def __init__(self, bits, mask, width):
        """Creates a new BitMask with the given bits, mask, and width.

        Typically you create a BitMask with BitMask.null(width), then
        modify it.
        """
        self._bits = bits & mask
        self._mask = mask
        self._width = width

    @classmethod
    def from_string(cls, s):
        """Takes the string, as given by repr(), and recreates the BitMask.
        """
        s = s.strip("<").strip(">")
        if s.startswith("BitMask "):
            s = s[len("BitMask "):]
        s = s.strip()
        width = len(s)
        bits = 0
        mask = 0
        for i in range(width):
            pos = 1 << i
            c = s[i]
            if c == "-":
                continue
            mask |= pos
            if c in cls.on_names:
                bits |= pos
            elif c not in cls.off_names:
                raise Exception("Got bad character: {}".format(c))
            # FIXME: would be nice to test the character is in the right position
        return cls(bits, mask, width)

    def __eq__(self, other):
        return isinstance(other, BitMask) and self._mask == other._mask and self._bits == other._bits and self._width == other._width

    def __hash__(self):
        return self._bits

    def add(self, pos, bit, force=False):
        """Adds a bit at the given position. The position is itself a bit (e.g.,
        `1 << 5` for the 5th bit).

        Unless force is true, it is an error if this modifies a known bit."""
        if not force:
            if pos & self._mask and (pos & self._bits) != (pos & (~0 if bit else 0)):
                raise IncompatibleAdd(".add() bit does not match")
        if bit:
            bits = self._bits | pos
        else:
            bits = self._bits & (~pos)
        mask = self._mask | pos
        return BitMask(bits, mask, self._width)

    def is_set(self, pos):
        """Asks if the given bit (e.g., `1 << 5` for the 5th bit) is known"""
        return self._mask & pos

    def all_set(self):
        """Checks that all the bits (up to the width) are known (1 or 0)"""
        for i in range(self._width):
            pos = 1 << i
            if not self._mask & pos:
                return False
        return True

    def count_set(self):
        """Count the number of bits that are set/known"""
        count = 0
        for i in range(self._width):
            pos = 1 << i
            if self._mask & pos:
                count += 1
        return count

    def is_null(self):
        """Is this a null BitMask?"""
        return self._mask == 0

    def known_and_matches(self, pos, bit):
        """Asks if a given bit (as a pos like `1 << 5`) is both known and has
        the given value (`bit` is 1 or 0)"""
        if not self.is_set(pos):
            return False
        if bit:
            return self._bits & pos
        else:
            return not self._bits & pos

    def conflicts(self, other):
        """Do any known bits conflict with any known bits of the other BitMask?"""
        mask = self._mask & other._mask
        my_bits = self._bits & mask
        other_bits = other._bits & mask
        return my_bits ^ other_bits

    def accomplishes_something(self, goal):
        """Tests if any of our bits match a desired bit in the goal BitMask"""
        mask = self._mask & goal._mask
        my_bits = self._bits & mask
        goal_bits = (~goal._bits) & mask
        return my_bits ^ goal_bits

    def unset_from_action(self, action_then, force=False):
        """Unset any bits that are set by the `action_then` BitMask.

        Unless `force` is true, it is an error if any overlapping bits don't match"""
        if not force:
            assert not self.conflicts(action_then)
        return BitMask(self._bits, self._mask & (~action_then._mask), self._width)

    def difference(self, other):
        """Return a BitMask with all of our bits that don't match the bits in `other`"""
        mask = self._mask & other._mask
        diff = (self._bits & mask) ^ (other._bits & mask)
        return BitMask(self._bits, diff, self._width)

    def without_matching(self, other):
        """All our bits, except those that match what is in other"""
        matching_mask = self._mask & other._mask & (other._bits ^ (~ self._bits))
        new_mask = self._mask & (~ matching_mask)
        return BitMask(self._bits, new_mask, self._width)

    def carry_forward(self, previous):
        """Used as in a case when we have a state, and apply `then`, but want
        to prefer the bits in self, but any known bits in `previous` will be carried
        forward"""
        combined_mask = previous._mask | self._mask
        carry_mask = self._mask ^ combined_mask
        bits = self._bits & (previous._bits | (~carry_mask))
        bits = bits | (previous._bits & carry_mask)
        return BitMask(bits, combined_mask, self._width)

    def satisfies(self, goal):
        """Tests if all bits in `goal` are set by and match this BitMask"""
        our = self._mask & goal._mask
        if our ^ goal._mask:
            return False
        return not self.conflicts(goal)

    def except_satisfied_by(self, action_results):
        """Take our bits, and change any bits that are satisfied by `action_results`
        into unset bits"""
        # satisfied will have 1 for all bits that are the same
        satisfied = action_results._bits ^ (~ self._bits)
        satisfied = satisfied & self._mask & action_results._mask
        # Now we need to take our mask and remove any bits that are set to one in satisfied
        new_mask = self._mask & (~ satisfied)
        return BitMask(self._bits, new_mask, self._width)

    def __repr__(self):
        return '<BitMask {}>'.format(self.mask_str())

    def mask_str(self):
        s = ''
        for i in range(self._width):
            pos = 1 << i
            letter_pos = i % len(self.on_names)
            if self._mask & pos:
                if self._bits & pos:
                    s += self.on_names[letter_pos]
                else:
                    s += self.off_names[letter_pos]
            else:
                s += '-'
        return s

    @classmethod
    def null(cls, width):
        """Create a null BitMask of the given width"""
        return cls(0, 0, width)

    @classmethod
    def all_union(cls, items):
        """Create the union of all items (a sequence).

        It is an error if there is a conflict among the items"""
        mask = 0
        bits = 0
        for i, item in enumerate(items):
            width = item._width
            for other in items[i + 1:]:
                if item.conflicts(other):
                    raise Exception("all_union conflict: {} with {}".format(item, other))
                if item._width != other._width:
                    raise Exception("all_union width mismatch: {} with {}".format(item, other))
        for item in items:
            mask |= item._mask
            bits |= item._mask & item._bits
            bits &= ~(item._mask & (~item._bits))
        return BitMask(bits, mask, width)

    def union(self, other):
        """Creates a union of this BitMask and the other; no conflicts are allowed"""
        return BitMask.all_union([self, other])
