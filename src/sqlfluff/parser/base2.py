""" This is a rewrite of the parser from the ground up """

import re
import six


class sqlfluffParseError(Exception):
    def __init__(self, rule, expected, found):
        self.rule = rule
        self.expected = expected
        self.found = found[:16]
        if len(found[16:]) > 0:
            self.found += '...'

        message = "Rule {0} expected to find {1} and actually found {2}".format(
            self.rule.name,
            self.expected,
            self.found)
        # Call the base class constructor with the parameters it needs
        super(sqlfluffParseError, self).__init__(message)


class Node(object):
    def __init__(self, nodes, rule_stack, name='-', complete=False):
        self.nodes = nodes
        self.rule_stack = rule_stack
        self.name = name
        # This will get set to true when it's fully parsed
        self.complete = complete

    def fmt(self, indent=0, deep_indent=50):
        line_buff = []
        line_buff.append(('  ' * indent) + self.name + ':')
        for nd in self.nodes:
            line_buff += nd.fmt(indent=indent+1, deep_indent=deep_indent)
        return line_buff
    
    def prnt(self, deep_indent=50):
        return '\n'.join(self.fmt(deep_indent=deep_indent))



class Terminal(object):
    """ Like a node, but has no children """
    def __init__(self, s, token, rule_stack):
        self.s = s
        self.token = token
        self.rule_stack = rule_stack

    def fmt(self, indent=0, deep_indent=50):
        line_buff = []
        line_buff.append(
            ('  ' * indent) + self.token + ':'
             + (' ' * (deep_indent - ((indent * 2) + len(self.token) + 1)))
             + repr(self.s))
        return line_buff


class Dialect(object):
    """ A dialect is a collection of rules """
    def __init__(self, name, root_rule, rules):
        self.name = name
        self.root_rule = root_rule
        # Populate the rule set
        self.rules = {}
        for rule in rules:
            if rule.name in self.rules:
                raise ValueError("Rule with name {0!r} already exists in dialect {1}!".format(rule.name, self.name))
            else:
                self.rules[rule.name] = rule
        # Check that the root rule is accessible (raise expection if not)
        self.get_rule(self.root_rule)

    def get_rule(self, name):
        if name not in self.rules:
            raise ValueError("Rule {0!r} not found in set of rules provided for dialect {1}".format(name, self.name))
        else:
            return self.rules[name]

    def parse(self, s, rule_stack=None):
        rule = self.get_rule(self.root_rule)
        # Parse and make a tree recursively, passing self as the dialect
        # We should assume there's no existing rule stack, so pass an empty one in
        tree, remainder = rule.parse(s, rule_stack=rule_stack or tuple(), dialect=self)
        return tree, remainder


class Rule(object):
    """ The base class for patterns """
    def __init__(self, name, sequence):
        self.name = name
        # sequence can be any iterable (but the types of the elements are important)
        self.sequence = sequence

    def parse(self, s, rule_stack, dialect):
        # Update the pass-through stack
        pass_stack = rule_stack + (self.name,)
        # Create a local variable to keep track of the remaining string
        s_buff = s
        # Create a local buffer for notes
        node_buff = []
        # Run through the elements of the sequence in order
        for elem in self.sequence:
            # Could create subrules here?

            # Is it a compulsary rule reference?
            if isinstance(elem, six.string_types):
                rule = dialect.get_rule(elem)
                nd, s_buff = rule.parse(s_buff, pass_stack, dialect=dialect)
                if nd:
                    # Got a match, stick it onto the buffer.
                    node_buff += [nd]
                    # s_buff is already updated (so no need to do that)
                else:
                    # No match - we're greedy, and this is a required field.
                    # that means even if we've partially matched, we can't proceed.
                    raise sqlfluffParseError(rule, elem, s_buff)
            # Is it a list (i.e. an optional element which can appear zero or one times)
            elif isinstance(elem, list):
                # how many elements does the list have?
                if len(elem) == 0:
                    raise ValueError("Found a zero length optional element in rule {0}!".format(self.name))
                elif len(elem) == 1:
                    rule_name = elem[0]
                    rule = dialect.get_rule(rule_name)
                    try:
                        nd, s_buff = rule.parse(s_buff, pass_stack, dialect=dialect)
                        if nd:
                            # Got a match! stick it onto the buffer.
                            node_buff += [nd]
                    except sqlfluffParseError:
                        # if we get an error, it's no biggie - it's optional!!
                        pass
                else:
                    raise NotImplementedError("Not implemented optional elements of length > 1 yet")
            else:
                # Unknown type found in the sequence!
                raise RuntimeError("Unknown type found in the sequence {0} {1!r}".format(type(elem), elem))
        # Assuming we get this far, spit back out a completed node
        return Node(node_buff, rule_stack, name=self.name, complete=True), s_buff


class TerminalRule(Rule):
    """ TerminalRules are just special cases of Rules """
    def __init__(self, pattern, name=None, case_sensitive=False):
        self.name = name or pattern
        # Precompile the pattern
        if case_sensitive:
            self.pattern = re.compile(pattern)
        else:
            self.pattern = re.compile(pattern, re.IGNORECASE)

    def parse(self, s, rule_stack, dialect):
        """ NB: Same interface as for rules """
        m = self.pattern.match(s)
        if m:
            last_pos = m.end()
            return Terminal(s[:last_pos], self.name, rule_stack), s[last_pos:]
        return None, s


ansi_rules = [
    TerminalRule(r'select'),
    TerminalRule(r'from'),
    TerminalRule(r'group by', name='groupby'),
    TerminalRule(r'order by', name='orderby'),
    TerminalRule(r'[a-z_]+', name='object_literal'),
    TerminalRule(r'\s+', name='whitespace'),
    # Rule('select_stmt', ['select', 'whitespace', 'col_expr', 'whitespace', 'from',
    #                      'whitespace', 'table_expr']),
    Rule('select_stmt', ['select', 'whitespace', 'col_expr', 'whitespace', 'from',
                         'whitespace', 'table_expr', ['group_by_expr'], ['order_by_expr']]),
    Rule('col_expr', ['object_literal']),
    Rule('table_expr', ['object_literal']),
    Rule('group_by_expr', ['whitespace', 'groupby', 'whitespace', 'col_expr']),
    Rule('order_by_expr', ['whitespace', 'orderby', 'whitespace', 'col_expr'])
]

ansi = Dialect('ansi', 'select_stmt', ansi_rules)