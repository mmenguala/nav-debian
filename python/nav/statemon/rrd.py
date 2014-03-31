#
# Copyright (C) 2003, 2004 Norwegian University of Science and Technology
# Copyright (C) 2010, 2011 UNINETT AS
#
# This file is part of Network Administration Visualized (NAV).
#
# NAV is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License version 2 as published by
# the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
# details.  You should have received a copy of the GNU General Public License
# along with NAV. If not, see <http://www.gnu.org/licenses/>.
#
"""
Module for creating and updating rrd-objects
"""
import os
import shutil
import event
from debug import debug
import rrdtool as rrd
import db

try:
    import nav.path
    RRDDIR = nav.path.localstatedir + '/rrd'
except ImportError:
    # Not properly installed
    RRDDIR = '/var/rrd'
RRD_STEP = 300
_database = db.db()

def create(filename, netboxid, serviceid=None, handler=""):
    """Creates a new RRD file and registers it in the database"""
    dirname = os.path.dirname(filename)
    if not os.path.exists(dirname):
        os.mkdir(dirname)
    args = (str(filename),
            '-s %s' % RRD_STEP,
            'DS:STATUS:GAUGE:600:0:1',
            'DS:RESPONSETIME:GAUGE:600:0:300',
            'RRA:AVERAGE:0.5:1:288',
            'RRA:AVERAGE:0.5:6:336',
            'RRA:AVERAGE:0.5:12:720',
            'RRA:MAX:0.5:12:720',
            'RRA:AVERAGE:0.5:288:365',
            'RRA:MAX:0.5:288:365',
            'RRA:AVERAGE:0.5:288:1095',
            'RRA:MAX:0.5:288:1095')
    rrd.create(*args)
    debug("Created rrd file %s" % filename)
    verify_rrd_registry(filename, netboxid, serviceid, handler)

def register_rrd(filename, netboxid, serviceid=None, handler=""):
    """Registers an RRD file in the db registry."""
    if serviceid:
        key = "serviceid"
        val = serviceid
        subsystem = "serviceping"
        statusdescr = "%s availability" % handler
        responsedescr = "%s responsetime" % handler
        unit = '-100%'
    else:
        key = ""
        val = ""
        subsystem = "pping"
        statusdescr = "Packet loss"
        responsedescr = "Roundtrip time"
        unit = '100%'
    rrd_fileid = _database.registerRrd(filename, RRD_STEP, netboxid,
                                       subsystem, key, val)
    _database.registerDS(rrd_fileid, "RESPONSETIME",
                         responsedescr, "GAUGE", "s")

    _database.registerDS(rrd_fileid, "STATUS", statusdescr, "GAUGE", unit)

def verify_rrd_registry(filename, netboxid, serviceid=None, handler=""):
    """Verifies that an RRD file is known in the RRD registry.

    If the file is known, but disconnected, it will be reconnected.  If the
    file is unknown, it will be registered from scratch.

    """
    try:
        registered_netboxid = _database.verify_rrd(filename)
    except db.UnknownRRDFileError:
        register_rrd(filename, netboxid, serviceid, handler)
    else:
        if registered_netboxid is None:
            _database.reconnect_rrd(filename, netboxid)
        # We don't handle the unusual case where a netboxid in the db differs
        # from the one we are working with
    return True


def update(netboxid, sysname, time, status, responsetime, serviceid=None,
           handler=""):
    """
    time: 'N' or time.time()
    status: 'UP' or 'DOWN' (from Event.status)
    responsetime: 0-300 or '' (undef)
    """
    filename = resolve_rrd_file(netboxid, sysname, serviceid, handler)
    if not filename:
        debug("No RRD file to update for %s:%s" % (sysname, serviceid), 3)
        return

    if status == event.Event.UP:
        rrdstatus = 0
    else:
        rrdstatus = 1

    args = (str(filename),
            '%s:%i:%s' % (time, rrdstatus, responsetime))
    try:
        rrd.update(*args)
    except Exception, err:
        debug("Failed to update %s" % filename, 7)
        debug("Exception: %s" % err)
    else:
        debug("Updated %s" % filename, 7)

def resolve_rrd_file(netboxid, sysname, serviceid, handler):
    """Resolves and returns the name of an RRD file to update.

    This function will create the RRD file if necessary, and resolves most
    problems that can occur from differences between the file system and the
    database RRD registry, and from device sysname changes.

    """
    wanted_filename = os.path.normpath(make_rrd_filename(sysname, serviceid))
    db_filename = _get_rrd_for(netboxid, serviceid)

    wanted_file_exists = os.path.exists(wanted_filename)
    wanted_file_known = _is_rrd_known(wanted_filename)

    db_file_exists = db_filename and os.path.exists(db_filename)

    if wanted_filename == db_filename:
        if not wanted_file_exists:
            create(wanted_filename, netboxid, serviceid, handler)
        return wanted_filename
    else:
        if wanted_file_known:
            if db_filename:
                debug("Want to rename %s to %s but the latter is already in "
                      "use by something else" % (db_filename, wanted_filename),
                      7)
                if not db_file_exists:
                    create(db_filename, netboxid, serviceid, handler)
                return db_filename
            else:
                debug("Want to update %s for %s, but it is already in use by "
                      "something else" % (wanted_filename, sysname), 3)
                return
        else:
            if db_file_exists:
                debug("Renaming %s to %s" % (db_filename, wanted_filename), 7)
                shutil.move(db_filename, wanted_filename)
                _database.rename_rrd(db_filename, wanted_filename)
            elif wanted_file_exists:
                verify_rrd_registry(wanted_filename, netboxid, serviceid,
                                    handler)
            else:
                create(wanted_filename, netboxid, serviceid, handler)
            return wanted_filename

def _is_rrd_known(filename):
    try:
        _database.verify_rrd(filename)
    except db.UnknownRRDFileError:
        return False
    else:
        return True

def _get_rrd_for(netboxid, serviceid):
    try:
        return os.path.normpath(
            _database.get_existing_rrd(netboxid, serviceid))
    except db.UnknownRRDFileError:
        return None

def make_rrd_filename(sysname, serviceid=None):
    """Returns the desired RRD filename for the given sysname/serviceid"""
    if serviceid:
        return os.path.join(RRDDIR, '%s.%s.rrd' % (sysname, serviceid))
        # typically ludvig.ntnu.no.54.rrd
    else:
        return os.path.join(RRDDIR, '%s.rrd' % (sysname))
        # typically ludvig.ntnu.no.rrd