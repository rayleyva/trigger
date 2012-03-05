#!/usr/bin/env python
# -*- coding: utf-8 -*- 

"""
autoacl.py - This file controls when ACLs get auto-applied to network devices,
in addition to what is explicitly specified in :class:`~trigger.acl.db.AclsDB`.

After editing this file, run ``python autoacl.py`` to make sure the
syntax is ok.  Several things will break if you break this file.

You can also run this with '-v' to output the list of all devices
and what ACLs will be applied to them.  You can save this output
before editing and compare it to the output after your change.

Skip down a bit to find the part you should edit.
"""

import os
import sys

from trigger.conf import settings
from trigger.acl import acl_exists


# Exports
__all__ = ('autoacl',)

#===============================
# BEGIN USER-SERVICEABLE PARTS
#===============================

OWNERS = settings.VALID_OWNERS

def autoacl(dev, explicit_acls=None):
    """
    Given a NetDevice object, returns a set of **implicit** (auto) ACLs. We require
    a device object so that we don't have circular dependencies between netdevices
    and autoacl.
    
    This function MUST return a set() of acl names or you will break the ACL
    associations. An empty set is fine, but it must be a set!

    :param dev: A :class:`~trigger.netdevices.NetDevice` object.
    :param explicit_acls: A set containing names of ACLs. Default: set()

    >>> dev = nd.find('test1-abc')
    >>> dev.manufacturer
    JUNIPER
    >>> autoacl(dev)
    set(['juniper-router-protect', 'juniper-router.policer'])
    """
    # Explicitly pass a set of explicit_acls so that we can use it as a
    # dependency for assigning implicit_acls. Defaults to an empty set.
    if explicit_acls is None:
        explicit_acls = set()

    # Skip anything not owned by valid groups
    if dev.owningTeam not in OWNERS:
        return set()

    # Skip firewall devices
    if dev.deviceType == 'FIREWALL':
        return set()

    # Skip bad dns
    if 'aol' not in dev.nodeName and 'atdn' not in dev.nodeName:
        return set()

    # Prep acl set
    acls = set()

    # 
    # ACL Magic starts here
    # 
    if dev.manufacturer in ('BROCADE', 'CISCO SYSTEMS', 'FOUNDRY'):
        acls.add('118')
        acls.add('119')

    #
    # Other GSR acls
    #
    if dev.manufacturer == 'CISCO SYSTEMS':
        acls.add('117')
        if dev.make == '12000 SERIES' and dev.nodeName.startswith('pop') or dev.nodeName.startswith('bb'):
            acls.add('backbone-acl')
        elif dev.make == '12000 SERIES':
            acls.add('gsr-acl')
    #
    # Juniper acls
    #
    if dev.manufacturer == 'JUNIPER':
        if dev.deviceType == 'SWITCH':
            acls.add('juniper-switch-protect')
        else:
            acls.add('juniper-router-protect')
            acls.add('juniper-router.policer')

    #
    # Explicit ACL example
    #
    # Only add acl '10' (or variants) to the device if 'acb123.special' is not
    # explicitly associated with the device.
    if '10.special' in explicit_acls:
        pass
    elif dev.deviceType == 'ROUTER':
        acls.add('10')
    elif dev.deviceType == 'SWITCH':
        acls.add('10.sw')

    return acls

#===============================
# END USER-SERVICEABLE PARTS
#===============================

def main():
    """A simple syntax check and dump of all we see and know!"""
    print 'Syntax ok.'
    if len(sys.argv) > 1:
        from trigger.netdevices import NetDevices
        nd = NetDevices()
        names = sorted(nd)
        for name in names:
            dev = nd[name]
            if dev.deviceType not in ('ROUTER', 'SWITCH'):
                continue
            acls = sorted(dev.acls)
            print '%-39s %s' % (name, ' '.join(acls))

if __name__ == '__main__':
    main()

