"""
"""

# Created on 2014.09.08
#
# Author: Giovanni Cannata
#
# Copyright 2014 Giovanni Cannata
#
# This file is part of python3-ldap.
#
# python3-ldap is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# python3-ldap is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with python3-ldap in the COPYING and COPYING.LESSER files.
# If not, see <http://www.gnu.org/licenses/>.

from ..core.exceptions import LDAPInvalidDnError, LDAPExceptionError
from string import hexdigits


STATE_ANY = 0
STATE_ESCAPE = 1
STATE_ESCAPE_HEX = 2

def _add_ava(ava, decompose, remove_space, space_around_equal):
    if not ava:
        return ''

    space = ' ' if space_around_equal else ''
    attr_name, _, value = ava.partition('=')
    if decompose:
        if remove_space:
            component = (attr_name.strip(), value.strip())
        else:
            component = (attr_name, value)
    else:
        if remove_space:
            component = attr_name.strip() + space + '=' + space + value.strip()
        else:
            component = attr_name + space + '=' + space + value

    return component


def to_dn(iterator, decompose=False, remove_space=False, space_around_equal=False, separate_rdn=False):
    """
    Convert an iterator to a list of dn parts
    if decompose=True return a list of tuple (one for each dn component) else return a list of strings
    if remove_space=True removes unneeded spaces
    if space_around_equal=True add spaces around equal in returned strings
    if separate_rdn=True consider multiple RDNs as different component of DN
    """
    dn = []
    component = ''
    escape_sequence = False
    for c in iterator:
        if c in '\\':  # escape sequence
            escape_sequence = True
        elif escape_sequence and c not in ' ':
            escape_sequence = False
        elif c in '+' and separate_rdn:
            dn.append(_add_ava(component, decompose, remove_space, space_around_equal))
            component = ''
            continue
        elif c == ',':
            if '=' in component:
                dn.append(_add_ava(component, decompose, remove_space, space_around_equal))
                component = ''
                continue

        component += c

    dn.append(_add_ava(component, decompose, remove_space, space_around_equal))
    return dn


def get_next_ava(dn):
    comma = dn.find(',')
    plus = dn.find('+')
    if plus > 0 and plus < comma:
        if dn.find('=', plus, comma) > 0:  # break dn at + only if an equal is still present
            return dn[:plus], '+'
        else:
            return dn[:comma], ','
    elif comma > 0:
        return dn[:comma], ','

    return dn, ''


def split_ava(ava, escape = False, strip = True):
    equal = ava.rfind('=')
    while equal > 0:
        if ava[equal - 1] != '\\': # not an escaped equal so it must be an ava separator
            attribute_type = ava[0:equal].strip() if strip else ava[0:equal]
            if strip:
                attribute_type = ava[0:equal].strip()
                attribute_value = escape_attribute_value(ava[equal + 1:].strip()) if escape else ava[equal + 1:].strip()
            else:
                attribute_type = ava[0:equal]
                attribute_value = escape_attribute_value(ava[equal + 1:]) if escape else ava[equal + 1:]

            return attribute_type, attribute_value
        equal = ava.rfind('=', 0, equal)

    return '', (ava.strip if strip else ava)  # if no equal found return only value

def validate_attribute_type(attribute_type):
    if not attribute_type:
        return False
    for c in attribute_type:
        if not c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-':  # allowed uppercase and lowercase letters, digits and hyphen as per RFC 4512
            raise LDAPInvalidDnError('character ' + c + ' not allowed in Attribute Type')

    if attribute_type[0] in '0123456789-':  # digits and hyphen not allowed as first character
        raise LDAPInvalidDnError('character ' + attribute_type[0] + ' not allowed as first character of Attribute Type')

    return True

def validate_attribute_value(attribute_value):
    if not attribute_value:
        return False

    if attribute_value[0] == '#':  # only hex characters are valid
        for c in attribute_value:
            if not 'c' in hexdigits:  # allowed only hex digits as per RFC 4514
                raise LDAPInvalidDnError('character ' + c + ' not allowed in hex representation of Attribute_Value')
        if len(attribute_value) % 2 == 0:  # string must be # + HEX HEX (an odd number of chars)
            raise LDAPInvalidDnError('hex representation must be in the form of <HEX><HEX> pairs')
    if attribute_value[0] == ' ':  # space cannot be used as first or last character
        raise LDAPInvalidDnError('SPACE not allowed as first character of Attribute Value')
    if attribute_value[-1] == ' ':
        raise LDAPInvalidDnError('SPACE not allowed as last character of Attribute Value')

    state = STATE_ANY
    for c in (attribute_value):
        if state == STATE_ANY:
            if c == '\\':
                state = STATE_ESCAPE
            elif c in '"#+,;<=>\00':
                raise LDAPInvalidDnError('special characters ' + c + ' must be escaped')
        elif state == STATE_ESCAPE:
            if c in hexdigits:
                state = STATE_ESCAPE_HEX
            elif c in ' "#+,;<=>\\\00':
                state = STATE_ANY
            else:
                raise LDAPInvalidDnError('invalid escaped character ' + c)
        elif state == STATE_ESCAPE_HEX:
            if c in hexdigits:
                state = STATE_ANY
            else:
                raise LDAPInvalidDnError('invalid escaped character ' + c)


    # final state
    if state != STATE_ANY:
        raise LDAPInvalidDnError('invalid final character')

    return True


def escape_attribute_value(attribute_value):
    if not attribute_value:
        return ''

    if attribute_value[0] == '#':  # with leading SHARP only pairs of hex characters are valid
        valid = True
        if len(attribute_value) % 2 == 0:  # string must be # + HEX HEX (an odd number of chars)
            valid = False

        if valid:
            for c in attribute_value:
                if not 'c' in hexdigits:  # allowed only hex digits as per RFC 4514
                    valid = False
                    break

        if valid:
            return attribute_value

    state = STATE_ANY
    escaped = ''
    buffer = ''
    for c in (attribute_value):
        if state == STATE_ANY:
            if c == '\\':
                state = STATE_ESCAPE
            elif c in '"#+,;<=>\00':
                escaped += '\\' + c
            else:
                escaped += c
        elif state == STATE_ESCAPE:
            if c in hexdigits:
                buffer = c
                state = STATE_ESCAPE_HEX
            elif c in ' "#+,;<=>\\\00':
                escaped += '\\' + c
                state = STATE_ANY
            else:
                escaped += '\\\\' + c
        elif state == STATE_ESCAPE_HEX:
            if c in hexdigits:
                escaped += '\\' + buffer + c
            else:
                escaped += '\\\\' + buffer + c
            buffer = ''
            state = STATE_ANY

    # final state
    if state == STATE_ESCAPE:
        escaped += '\\\\'
    elif state == STATE_ESCAPE_HEX:
        escaped += '\\\\' + buffer

    if escaped[0] == ' ':  # leading  SPACE must be escaped
        escaped = '\\' + escaped

    if escaped[-1] == ' ' and len(escaped) > 1 and escaped[-2] != '\\':  # trailing SPACE must be escaped
        escaped = escaped[:-1] + '\\ '

    return escaped

def parse_dn(dn, escape=False, strip=True):
    done = False
    rdns = []
    while not done:
        ava, separator = get_next_ava(dn)
        if ava:
            attribute_type, attribute_value = split_ava(ava, escape, strip)
            if not validate_attribute_type(attribute_type):
                raise LDAPInvalidDnError('unable to validate attribute type: ' + attribute_type)

            if not validate_attribute_value(attribute_value):
                raise LDAPInvalidDnError('unable to validate attribute value: ' + attribute_value)

            rdns.append((attribute_type, attribute_value, separator))
            dn = dn[len(ava) + 1:]
        else:
            done = True

    return rdns

def safe_dn(dn):
    safe_dn = ''
    for rdn in parse_dn(dn, escape=True):
        safe_dn += rdn[0] + '=' + rdn[1] + rdn[2]

    return safe_dn