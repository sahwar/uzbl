""" Basic cookie manager
    forwards cookies to all other instances connected to the event manager"""

from collections import defaultdict
import os, re

symbolic = {'domain': 0, 'path':1, 'name':2, 'value':3, 'scheme':4, 'expires':5}

_splitquoted = re.compile("( |\\\".*?\\\"|'.*?')")
def splitquoted(text):
    return [str(p.strip('\'"')) for p in _splitquoted.split(text) if p.strip()]

# allows for partial cookies
# ? allow wildcard in key
def match(key, cookie):
    for k,c in zip(key,cookie):
        if k != c:
            return False
    return True

class NullStore(object):
    def add_cookie(self, rawcookie, cookie):
        pass

    def delete_cookie(self, rkey, key):
        pass

class ListStore(list):
    def add_cookie(self, rawcookie, cookie):
        self.append(rawcookie)

    def delete_cookie(self, rkey, key):
        self[:] = [x for x in self if not match(key, splitquoted(x))]

class TextStore(object):
    def __init__(self, filename):
        self.filename = filename

    def as_event(self, cookie):
        if cookie[0].startswith("#HttpOnly_"):
            domain = cookie[0][len("#HttpOnly_"):]
        elif cookie[0].startswith('#'):
            return None
        else:
            domain = cookie[0]
        return (domain,
            cookie[2],
            cookie[5],
            cookie[6],
            'https' if cookie[3] == 'TRUE' else 'http',
            cookie[4])

    def as_file(self, cookie):
        return (cookie[0],
            'TRUE' if cookie[0].startswith('.') else 'FALSE',
            cookie[1],
            'TRUE' if cookie[4] == 'https' else 'FALSE',
            cookie[5],
            cookie[2],
            cookie[3])

    def add_cookie(self, rawcookie, cookie):
        assert len(cookie) == 6

        # delete equal cookies (ignoring expire time, value and secure flag)
        self.delete_cookie(None, cookie[:-3])

        first = not os.path.exists(self.filename)
        with open(self.filename, 'a+') as f:
            if first:
                print >> f, "# HTTP Cookie File"
            print >> f, '\t'.join(self.as_file(cookie))

    def delete_cookie(self, rkey, key):
        if not os.path.exists(self.filename):
            return

        # read all cookies
        with open(self.filename, 'r') as f:
            cookies = f.readlines()

        # write those that don't match the cookie to delete
        with open(self.filename, 'w') as f:
            for l in cookies:
                c = self.as_event(l.split('\t'))
                if c is None or not match(key, c):
                    print >> f, l,

xdg_data_home = os.environ.get('XDG_DATA_HOME', os.path.join(os.environ['HOME'], '.local/share'))
DefaultStore = TextStore(os.path.join(xdg_data_home, 'uzbl/cookies.txt'))
SessionStore = ListStore()

def accept_cookie(uzbl, cookie):
    for component, match in uzbl.cookie_blacklist:
        if match(cookie[component]) is not None:
            return False
    return True

def expires_with_session(uzbl, cookie):
    return cookie[5] == ''

def get_recipents(uzbl):
    """ get a list of Uzbl instances to send the cookie too. """
    # This could be a lot more interesting
    return [u for u in uzbl.parent.uzbls.values() if u is not uzbl]

def get_store(uzbl, session=False):
    if session:
        return SessionStore
    return DefaultStore

def add_cookie(uzbl, cookie):
    splitted = splitquoted(cookie)
    if accept_cookie(uzbl, splitted):
        for u in get_recipents(uzbl):
            u.send('add_cookie %s' % cookie)
        
        get_store(uzbl, expires_with_session(uzbl, splitted)).add_cookie(cookie, splitted)
    else:
        uzbl.send('delete_cookie %s' % cookie)

def delete_cookie(uzbl, cookie):
    for u in get_recipents(uzbl):
        u.send('delete_cookie %s' % cookie)

    splitted = splitquoted(cookie)
    if len(splitted) == 6:
        get_store(uzbl, expires_with_session(uzbl, splitted)).delete_cookie(cookie, splitted)
    else:
        for store in set([get_store(uzbl, session) for session in (True, False)]):
            store.delete_cookie(cookie, splitted)

def blacklist(uzbl, arg):
    component, regexp = splitquoted(arg)
    try:
        component = symbolic[component]
    except KeyError:
        component = int(component)
    assert component <= 5
    uzbl.cookie_blacklist.append((component, re.compile(regexp).match))

def init(uzbl):
    connect_dict(uzbl, {
        'ADD_COOKIE':       add_cookie,
        'DELETE_COOKIE':    delete_cookie,
        'BLACKLIST_COOKIE': blacklist
    })
    export_dict(uzbl, {
        'cookie_blacklist' : []
    })

    for cookie in get_store(uzbl, True):
        uzbl.send('add_cookie %s' % cookie)
