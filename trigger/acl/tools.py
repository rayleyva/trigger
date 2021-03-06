# -*- coding: utf-8 -*-

"""
Various tools for use in scripts or other modules. Heavy lifting from tools
that have matured over time have been moved into this module. 
"""

__author__ = 'Jathan McCollum, Eileen Tschetter'
__maintainer__ = 'Jathan McCollum'
__email__ = 'jathan.mccollum@teamaol.com'
__copyright__ = 'Copyright 2010-2011, AOL Inc.'

from collections import defaultdict
import datetime
import IPy
import os
import re
import sys
import tempfile
from trigger.acl.parser import *
from trigger.conf import settings


# Defaults
DEBUG = False
DATE_FORMAT = "%Y-%m-%d"
DEFAULT_EXPIRE = 6 * 30 # 6 months


# Exports
__all__ = ('create_trigger_term', 'create_access', 'check_access', 'ACLScript',
          'process_bulk_loads', 'get_bulk_acls', 'get_comment_matches', 
           'write_tmpacl', 'diff_files', 'worklog')


# Functions
def create_trigger_term(source_ips=[],
                       dest_ips=[],
                       source_ports=[],
                       dest_ports=[],
                       protocols=[], 
                       action=['accept'],
                       name="generated_term"):
    """Constructs & returns a Term object from constituent parts."""
    term = Term()
    term.action = action
    term.name = name
    for key, data in {'source-address': source_ips,
                     'destination-address': dest_ips,
                     'source-port': source_ports,
                     'destination-port': dest_ports,
                     'protocol': protocols}.iteritems():
        for n in data:
            if key in term.match:
                term.match[key].append(n)
            else:
                term.match[key] = [n] 
    return term

def check_access(terms_to_check, new_term, quiet=True, format='junos'):
    """
    Determine whether access is permitted by a given ACL (list of terms).

    Tests a new term against a list of terms. Return True if access in new term
    is permitted, or False if not.

    Optionally displays the terms that apply and what edits are needed.
    """
    permitted = None
    matches = {
            'source-address':       new_term.match.get('source-address',[]),
            'destination-address':  new_term.match.get('destination-address',[]),
            'protocol':             new_term.match.get('protocol',[]),
            'destination-port':     new_term.match.get('destination-port',[]),
            'source-port':          new_term.match.get('source-port',[]) }

    for t in terms_to_check:
        hit = True
        complicated = False

        for comment in t.comments:
            #print comment
            if 'trigger: make discard' in comment:
                t.setaction('discard') #.action[0] = 'discard'

        for k,v in t.match.iteritems():

            if k not in matches or not matches[k]:
                complicated = True

            else:
                for test in matches[k]:
                    if test not in v:
                        hit = False
                        break

        if hit and not t.inactive:
            if not complicated and permitted is None:

                if t.action[0] == 'accept':
                    permitted = True
                    if not quiet: 
                        t.comments.append(Comment('check_access: PERMITTED HERE'))

                elif t.action[0] in ('discard', 'reject'):
                    permitted = False
                    if not quiet:
                        print '\n'.join(new_term.output(format))
            if not quiet:
                print '\n'.join(t.output(format))

    return permitted
        
def create_access(terms_to_check, new_term):
    """
    Breaks a new_term up into separate constituent parts so that they can be 
    compared in a check_access test.
    
    Returns a list of terms that should be inserted.
    """
    protos      = new_term.match.get('protocol', ['any'])
    sources     = new_term.match.get('source-address', ['any'])
    dests       = new_term.match.get('destination-address', ['any'])
    sourceports = new_term.match.get('source-port', ['any'])
    destports   = new_term.match.get('destination-port', ['any'])
    
    ret = []
    for proto in protos:
        for source in sources:
            for sourceport in sourceports:
                for dest in dests:
                    for destport in destports:
                        t = Term()
                        if str(proto) != 'any':
                            t.match['protocol'] = [proto]
                        if str(source) != 'any':
                            t.match['source-address'] = [source]
                        if str(dest) != 'any':
                            t.match['destination-address'] = [dest]
                        if str(sourceport) != 'any':
                            t.match['source-port'] = [sourceport]
                        if str(destport) != 'any':
                            t.match['destination-port'] = [destport]
                        if not check_access(terms_to_check, t):
                            ret.append(t)

    return ret

def get_bulk_acls():
    """
    Returns a dict of acls with an applied count over settings.AUTOLOAD_BULK_THRESH
    """
    from trigger.netdevices import NetDevices
    nd = NetDevices()
    all_acls = defaultdict(int)
    for dev in nd.all():
        for acl in dev.acls:
            all_acls[acl] += 1

    bulk_acls = {}
    for acl, count in all_acls.items():
        if count >= settings.AUTOLOAD_BULK_THRESH and acl != '':
            bulk_acls[acl] = count

    return bulk_acls

def process_bulk_loads(work, max_hits=settings.BULK_MAX_HITS_DEFAULT, force_bulk=False):
    """
    Formerly "process --ones".

    Processes work dict and determines tuple of (prefix, site) for each device.  Stores
    tuple as a dict key in prefix_hits. If prefix_hits[(prefix, site)] is greater than max_hits,
    remove all further matching devices from work dict.

    By default if a device has no acls flagged as bulk_acls, it is not removed from the work dict.

    Example:
        * Device 'foo1-xyz.example.com' returns ('foo', 'xyz') as tuple.
        * This is stored as prefix_hits[('foo', 'xyz')] = 1
        * All further devices matching that tuple increment the hits for that tuple
        * Any devices matching hit counter exceeds max_hits is removed from work dict

    You may override max_hits to increase the num. of devices on which to load a bulk acl.
    You may pass force_bulk=True to treat all loads as bulk loads.
    """

    prefix_pat = re.compile(r'^([a-z]+)\d{0,2}-([a-z0-9]+)')
    prefix_hits = defaultdict(int)
    import trigger.acl.db as adb
    bulk_acls = adb.get_bulk_acls()
    nd = adb.get_netdevices()

    if DEBUG:
        print 'DEVLIST:', sorted(work)

    # Sort devices numerically
    #for router in sorted(work):
        #dev = nd.find(router)
    for dev in sorted(work):
        if DEBUG: print 'Doing', dev

        #testacls = dev.bulk_acls
        #if force_bulk:
        #    testacls = dev.acls
        testacls = dev.acls if force_bulk else dev.bulk_acls

        for acl in testacls:  #only look at each acl once, but look at all acls if bulk load forced
            if acl in work[dev]:
            #if acl in work[router]:
                if DEBUG: print 'Determining threshold for acl ', acl, ' on device ', dev, '\n'
                if acl in settings.BULK_MAX_HITS:
                    max_hits = settings.BULK_MAX_HITS[acl]

                try:
                    prefix_site = prefix_pat.findall(dev.nodeName)[0]
                except IndexError:
                    continue
                
                # Mark a hit for this tuple, and dump remaining matches
                prefix_hits[prefix_site] += 1

                if DEBUG: print prefix_site, prefix_hits[prefix_site]
                if prefix_hits[prefix_site] > max_hits:
                                
                    msg =  "Removing %s on %s from job queue: threshold of %d exceeded for " \
                           "'%s' devices in '%s'" % (acl, dev, max_hits, prefix_site[0], prefix_site[1])
                    print msg
                    if 'log' in globals():
                        log.msg(msg)

                    # Remove that acl from being loaded, but still load on that device
                    work[dev].remove(acl)
                    #work[router].remove(acl)

    #done with all the devices                
    return work

def get_comment_matches(aclobj, requests):
    """Given an ACL object and a list of ticket numbers return a list of matching comments."""
    matches = set()
    for t in aclobj.terms:
        for req in requests:
            for c in t.comments:
                if req in c:
                    matches.add(t)
            #[matches.add(t) for c in t.comments if req in c]

    return matches
    
def update_expirations(matches, numdays=DEFAULT_EXPIRE):
    """Update expiration dates on matching terms. This modifies mutable objects, so use cautiously."""
    print 'matching terms:', [term.name for term in matches]
    for term in matches:
        date = None
        for comment in term.comments:
            try:
                date = re.search(r'(\d{4}\-\d\d\-\d\d)', comment.data).group()
            except AttributeError:
                #print 'No date match in term: %s, comment: %s' % (term.name, comment)
                continue

            try:
                dstamp = datetime.datetime.strptime(date, DATE_FORMAT)
            except ValueError, err:
                print 'BAD DATE FOR THIS COMMENT:'
                print 'comment:', comment.data
                print 'bad date:', date
                print err
                print 'Fix the date and start the job again!'
                import sys
                sys.exit()
    
            new_date = dstamp + datetime.timedelta(days=numdays)
            #print 'Before:\n' + comment.data + '\n'
            print 'Updated date for term: %s' % term.name
            comment.data = comment.data.replace(date, datetime.datetime.strftime(new_date, DATE_FORMAT))
            #print 'After:\n' + comment.data

def write_tmpacl(acl, process_name='_tmpacl'):
    """Write a temporary file to disk from an Trigger acl.ACL object & return the filename"""
    tmpfile = tempfile.mktemp() + process_name
    f = open(tmpfile, 'w')
    for x in acl.output(acl.format, replace=True):
        f.write(x)
        f.write('\n')
    f.close()

    return tmpfile

def diff_files(old, new):
    """Return a unified diff between two files"""
    return os.popen('diff -Naur %s %s' % (old, new)).read()

def worklog(title, diff, log_string='updated by express-gen'):
    """Save a diff to the ACL worklog"""
    from time import strftime,localtime
    from trigger.utils.rcs import RCS

    date = strftime('%Y%m%d', localtime())
    file = os.path.join(settings.FIREWALL_DIR, 'workdocs', 'workdoc.' + date)
    rcs = RCS(file)

    if not os.path.isfile(file):
        print 'Creating new worklog %s' % file
        f = open(file,"w")
        f.write("# vi:noai:\n\n")
        f.close()
        rcs.checkin('.')

    print 'inserting the diff into the worklog %s' % file
    rcs.lock_loop()
    fd = open(file,"a")
    fd.write('"%s"\n' % title)
    fd.write(diff)
    fd.close()

    print 'inserting %s into the load queue' % title
    rcs.checkin(log_string)

    # Use acl to insert into queue, should be replaced with API call
    os.spawnlp(os.P_WAIT, 'acl', 'acl', '-i', title)


# Classes
class ACLScript:
    """
    Interface to generating or modifying access-lists. Intended for use in
    creating command-line utilities using the ACL API.
    """
    def __init__(self, acl=None, mode='insert', cmd='acl_script',
      show_mods=True, no_worklog=False, no_changes=False):
        self.source_ips   = []
        self.dest_ips     = []
        self.protocol     = []
        self.source_ports = []
        self.dest_ports   = []
        self.modify_terms = []
        self.bcomments    = []
        self.tempfiles    = []
        self.acl          = acl
        self.cmd          = cmd
        self.mode         = mode
        self.show_mods    = show_mods
        self.no_worklog   = no_worklog
        self.no_changes   = no_changes

    def cleanup(self):
        for file in self.tempfiles:
            os.remove(file)

    def genargs(self,interactive=False):
        if not self.acl:
            raise "need acl defined"

        argz = []
        argz.append('-a %s' % self.acl)

        if self.show_mods:
            argz.append('--show-mods')

        if self.no_worklog:
            argz.append('--no-worklog')

        if self.no_changes:
            argz.append('--no-changes')

        if not interactive:
            argz.append('--no-input')

        if self.mode == 'insert':
            argz.append('--insert-defined')

        elif self.mode == 'replace':
            argz.append('--replace-defined')

        else:
            raise "invalid mode"

        for k,v in {'--source-address-from-file':self.source_ips,
                    '--destination-address-from-file':self.dest_ips,
                   }.iteritems():
            if len(v) == 0:
                continue
            tmpf = tempfile.mktemp() + '_genacl'
            self.tempfiles.append(tmpf)
            try:
                f = open(tmpf,'w')
            except:
                print "UNABLE TO OPEN TMPFILE"
                raise "YIKES!"
            for x in v:
                f.write('%s\n' % x.strNormal())
            f.close()

            argz.append('%s %s' % (k,tmpf))

        for k,v in {'-p':self.source_ports,
                    '-P':self.dest_ports}.iteritems():

            if not len(v):
                continue

            for x in v:
                argz.append('%s %d' % (k,x))

        if len(self.modify_terms) and len(self.bcomments):
            print "Can only define either modify_terms or between comments"
            raise "Can only define either modify_terms or between comments"

        if self.modify_terms:
            for x in self.modify_terms:
                argz.append('-t %s' % x)
        else:
            for x in self.bcomments:
                (b,e) = x
                argz.append('-c "%s" "%s"' % (b,e))

        for proto in self.protocol:
            argz.append('--protocol %s' % proto)

        return argz

    def parselog(self, log):
        return log

    def run(self, interactive=False):
        args = self.genargs(interactive=interactive)
        log = []
        #print self.cmd + ' ' + ' '.join(args)
        if interactive:
            os.system(self.cmd + ' ' + ' '.join(args))
        else:
            f = os.popen(self.cmd + ' ' + ' '.join(args))
            line = f.readline()
            while line:
                line = line.rstrip()
                log.append(line)
                line = f.readline()
        return log

    def errors_from_log(self, log):
        errors = ''
        for l in log:
            if '%%ERROR%%' in l:
                l = l.spit('%%ERROR%%')[1]
                errors += l[1:] + '\n'
        return errors

    def diff_from_log(self, log):
        diff = ""
        for l in log:
            if '%%DIFF%%' in l:
                l = l.split('%%DIFF%%')[1]
                diff += l[1:] + '\n'
        return diff

    def set_acl(self, acl):
        self.acl=acl

    def _add_addr(self, to, src):
        if isinstance(src,list):
            for x in src:
                if IPy.IP(x) not in to:
                    to.append(IPy.IP(x))
        else:
            if IPy.IP(src) not in to:
                to.append(IPy.IP(src))

    def _add_port(self, to, src):
        if isinstance(src, list):
            for x in src:
                if x not in to:
                    to.append(int(x))
        else:
            if int(src) not in to:
                to.append(int(src))

    def add_protocol(self, src):
        to = self.protocol
        if isinstance(src, list):
            for x in src:
                if x not in to:
                    to.append(x)
        else:
            if src not in to:
                to.append(src)

    def add_src_host(self, data):
        self._add_addr(self.source_ips, data)
    def add_dst_host(self, data):
        self._add_addr(self.dest_ips, data)
    def add_src_port(self, data):
        self._add_port(self.source_ports, data)
    def add_dst_port(self, data):
        self._add_port(self.dest_ports, data)
    def add_modify_between_comments(self, begin, end):
        del self.modify_terms
        self.modify_terms = []
        self.bcomments.append((begin,end))
    def add_modify_term(self, term):
        del self.bcomments
        self.bcomments = []
        if term not in self.modify_terms:
            self.modify_terms.append(term)
    def get_protocols(self):
        return self.protocol
    def get_src_hosts(self):
        return self.source_ips
    def get_dst_hosts(self):
        return self.dest_ips
    def get_src_ports(self):
        return self.source_ports
    def get_dst_ports(self):
        return self.dest_ports

