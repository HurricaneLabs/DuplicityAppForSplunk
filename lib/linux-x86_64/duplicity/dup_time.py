# -*- Mode:Python; indent-tabs-mode:nil; tab-width:4 -*-
#
# Copyright 2002 Ben Escoto <ben@emerose.org>
# Copyright 2007 Kenneth Loafman <kenneth@loafman.com>
#
# This file is part of duplicity.
#
# Duplicity is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 2 of the License, or (at your
# option) any later version.
#
# Duplicity is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with duplicity; if not, write to the Free Software Foundation,
# Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307 USA

u"""Provide time related exceptions and functions"""
from __future__ import division

from past.utils import old_div
from builtins import map

import time
import types
import re
import calendar
import sys
from duplicity import globals
from duplicity import util

# For type testing against both int and long types that works in python 2/3
if sys.version_info < (3,):
    integer_types = (int, types.LongType)
else:
    integer_types = (int,)


class TimeException(Exception):
    pass


_interval_conv_dict = {u"s": 1, u"m": 60, u"h": 3600, u"D": 86400,
                       u"W": 7 * 86400, u"M": 30 * 86400, u"Y": 365 * 86400}
_integer_regexp = re.compile(u"^[0-9]+$")
_interval_regexp = re.compile(u"^([0-9]+)([smhDWMY])")
_genstr_date_regexp1 = re.compile(u"^(?P<year>[0-9]{4})[-/]"
                                  u"(?P<month>[0-9]{1,2})[-/]"
                                  u"(?P<day>[0-9]{1,2})$")
_genstr_date_regexp2 = re.compile(u"^(?P<month>[0-9]{1,2})[-/]"
                                  u"(?P<day>[0-9]{1,2})[-/]"
                                  u"(?P<year>[0-9]{4})$")
_genstr_date_regexp3 = re.compile(u"^(?P<year>[0-9]{4})"
                                  u"(?P<month>[0-9]{2})"
                                  u"(?P<day>[0-9]{2})Z$")
curtime = curtimestr = None
prevtime = prevtimestr = None

bad_interval_string = _(u"""Bad interval string "%s"

Intervals are specified like 2Y (2 years) or 2h30m (2.5 hours).  The
allowed special characters are s, m, h, D, W, M, and Y.  See the man
page for more information.""")

bad_time_string = _(u"""Bad time string "%s"

The acceptible time strings are intervals (like "3D64s"), w3-datetime
strings, like "2002-04-26T04:22:01-07:00" (strings like
"2002-04-26T04:22:01" are also acceptable - duplicity will use the
current time zone), or ordinary dates like 2/4/1997 or 2001-04-23
(various combinations are acceptable, but the month always precedes
the day).""")


def setcurtime(time_in_secs=None):
    u"""Sets the current time in curtime and curtimestr"""
    global curtime, curtimestr
    t = time_in_secs or int(time.time())
    assert type(t) in integer_types
    curtime, curtimestr = t, timetostring(t)


def setprevtime(time_in_secs):
    u"""Sets the previous time in prevtime and prevtimestr"""
    global prevtime, prevtimestr
    assert type(time_in_secs) in integer_types, prevtime
    prevtime, prevtimestr = time_in_secs, timetostring(time_in_secs)


def timetostring(timeinseconds):
    u"""Return w3 or duplicity datetime compliant listing of timeinseconds"""

    if globals.old_filenames:
        # We need to know if DST applies to append the correct offset. So
        #    1. Save the tuple returned by localtime.
        #    2. Pass the DST flag into gettzd
        lcltime = time.localtime(timeinseconds)
        return time.strftime(u"%Y-%m-%dT%H" + globals.time_separator +
                             u"%M" + globals.time_separator + u"%S",
                             lcltime) + gettzd(lcltime[-1])
    else:
        # DST never applies to UTC
        lcltime = time.gmtime(timeinseconds)
        return time.strftime(u"%Y%m%dT%H%M%SZ", lcltime)


def stringtotime(timestring):
    u"""Return time in seconds from w3 or duplicity timestring

    If there is an error parsing the string, or it doesn't look
    like a valid datetime string, return None.
    """
    try:
        date, daytime = timestring[:19].split(u"T")
        if len(timestring) == 16:
            # new format for filename time
            year, month, day = list(map(int,
                                    [date[0:4], date[4:6], date[6:8]]))
            hour, minute, second = list(map(int,
                                        [daytime[0:2], daytime[2:4], daytime[4:6]]))
        else:
            # old format for filename time
            year, month, day = list(map(int, date.split(u"-")))
            hour, minute, second = list(map(int,
                                        daytime.split(globals.time_separator)))
        assert 1900 < year < 2100, year
        assert 1 <= month <= 12
        assert 1 <= day <= 31
        assert 0 <= hour <= 23
        assert 0 <= minute <= 59
        assert 0 <= second <= 61  # leap seconds
        # We want to return the time in units of seconds since the
        # epoch. Unfortunately the only functin that does this
        # works in terms of the current timezone and we have a
        # timezone offset in the string.
        timetuple = (year, month, day, hour, minute, second, -1, -1, 0)

        if len(timestring) == 16:
            # as said in documentation, time.gmtime() and timegm() are each others' inverse.
            # As far as UTC format is used in new file format,
            # do not rely on system's python DST and tzdata settings
            # and use functions that working with UTC
            utc_in_secs = calendar.timegm(timetuple)
        else:
            # mktime assumed that the tuple was a local time. Compensate
            # by subtracting the value for the current timezone.
            # We don't need to worry about DST here because we turned it
            # off in the tuple
            local_in_secs = time.mktime(timetuple)
            utc_in_secs = local_in_secs - time.timezone
        # Now apply the offset that we were given in the time string
        # This gives the correct number of seconds from the epoch
        # even when we're not in the same timezone that wrote the
        # string
        if len(timestring) == 16:
            return int(utc_in_secs)
        else:
            return int(utc_in_secs + tzdtoseconds(timestring[19:]))
    except (TypeError, ValueError, AssertionError):
        return None


def timetopretty(timeinseconds):
    u"""Return pretty version of time"""
    return time.asctime(time.localtime(timeinseconds))


def stringtopretty(timestring):
    u"""Return pretty version of time given w3 time string"""
    return timetopretty(stringtotime(timestring))


def inttopretty(seconds):
    u"""Convert num of seconds to readable string like "2 hours"."""
    partlist = []
    hours, seconds = divmod(seconds, 3600)
    if hours > 1:
        partlist.append(u"%d hours" % hours)
    elif hours == 1:
        partlist.append(u"1 hour")

    minutes, seconds = divmod(seconds, 60)
    if minutes > 1:
        partlist.append(u"%d minutes" % minutes)
    elif minutes == 1:
        partlist.append(u"1 minute")

    if seconds == 1:
        partlist.append(u"1 second")
    elif not partlist or seconds > 1:
        if isinstance(seconds, integer_types):
            partlist.append(u"%s seconds" % seconds)
        else:
            partlist.append(u"%.2f seconds" % seconds)
    return u" ".join(partlist)


def intstringtoseconds(interval_string):
    u"""Convert a string expressing an interval (e.g. "4D2s") to seconds"""
    def error():
        raise TimeException(bad_interval_string % util.escape(interval_string))

    if len(interval_string) < 2:
        error()

    total = 0
    while interval_string:
        match = _interval_regexp.match(interval_string)
        if not match:
            error()
        num, ext = int(match.group(1)), match.group(2)
        if ext not in _interval_conv_dict or num < 0:
            error()
        total += num * _interval_conv_dict[ext]
        interval_string = interval_string[match.end(0):]
    return total


def gettzd(dstflag):
    u"""Return w3's timezone identification string.

    Expresed as [+/-]hh:mm.  For instance, PST is -08:00.  Zone is
    coincides with what localtime(), etc., use.

    """
    # time.daylight doesn't help us. It's a flag that indicates that we
    # have a dst option for the current timezone. Compensate by allowing
    # the caller to pass a flag to indicate that DST applies. This flag
    # is in the same format as the last member of the tuple returned by
    # time.localtime()

    if dstflag > 0:
        offset = old_div(-1 * time.altzone, 60)
    else:
        offset = old_div(-1 * time.timezone, 60)
    if offset > 0:
        prefix = u"+"
    elif offset < 0:
        prefix = u"-"
    else:
        return u"Z"  # time is already in UTC

    hours, minutes = list(map(abs, divmod(offset, 60)))
    assert 0 <= hours <= 23
    assert 0 <= minutes <= 59
    return u"%s%02d%s%02d" % (prefix, hours, globals.time_separator, minutes)


def tzdtoseconds(tzd):
    u"""Given w3 compliant TZD, return how far ahead UTC is"""
    if tzd == u"Z":
        return 0
    assert len(tzd) == 6  # only accept forms like +08:00 for now
    assert (tzd[0] == u"-" or tzd[0] == u"+") and \
        tzd[3] == globals.time_separator
    return -60 * (60 * int(tzd[:3]) + int(tzd[4:]))


def cmp(time1, time2):
    u"""Compare time1 and time2 and return -1, 0, or 1"""
    if isinstance(time1, (str, u"".__class__)):
        time1 = stringtotime(time1)
        assert time1 is not None
    if isinstance(time2, (str, u"".__class__)):
        time2 = stringtotime(time2)
        assert time2 is not None

    if time1 < time2:
        return -1
    elif time1 == time2:
        return 0
    else:
        return 1


def genstrtotime(timestr, override_curtime=None):
    u"""Convert a generic time string to a time in seconds"""
    if override_curtime is None:
        override_curtime = curtime
    if timestr == u"now":
        return override_curtime

    def error():
        raise TimeException(bad_time_string % util.escape(timestr))

    # Test for straight integer
    if _integer_regexp.search(timestr):
        return int(timestr)

    # Test for w3-datetime format, possibly missing tzd
    # This is an ugly hack. We need to know if DST applies when doing
    # gettzd. However, we don't have the flag to pass. Assume that DST
    # doesn't apply and pass 0. Getting a reasonable default from
    # localtime() is a bad idea, since we transition to/from DST between
    # calls to this method on the same run

    t = stringtotime(timestr) or stringtotime(timestr + gettzd(0))
    if t:
        return t

    try:  # test for an interval, like "2 days ago"
        return override_curtime - intstringtoseconds(timestr)
    except TimeException:
        pass

    # Now check for dates like 2001/3/23
    match = (_genstr_date_regexp1.search(timestr) or
             _genstr_date_regexp2.search(timestr) or
             _genstr_date_regexp3.search(timestr))
    if not match:
        error()
    timestr = u"%s-%02d-%02dT00:00:00%s" % (match.group(u'year'),
                                            int(match.group(u'month')),
                                            int(match.group(u'day')),
                                            gettzd(0))
    t = stringtotime(timestr)
    if t:
        return t
    else:
        error()
