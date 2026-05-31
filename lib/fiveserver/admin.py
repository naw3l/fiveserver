from twisted.web import static, server, resource
from twisted.internet import reactor, defer
from twisted.words.xish import domish
from xml.sax.saxutils import escape
from fiveserver import log
from fiveserver.model.lobby import MatchState, Match, Match6
from fiveserver.model import util

import os
import urllib
import sys
import hashlib
from datetime import datetime

import base64
base64.decodestring = base64.decodebytes

try: import psutil
except ImportError:
    try:
        import commands
    except ImportError:
        import subprocess as commands


XML_HEADER = """<?xml version="1.0" encoding="UTF-8"?>
<?xml-stylesheet type="text/xsl" href="/xsl/style.xsl"?>
"""

fsroot = os.environ.get('FSROOT','.')
XSL_FILE=fsroot+"""/%(XslFile)s"""


class XslResource(resource.Resource):
    isLeaf = True

    def __init__(self, adminConfig):
        resource.Resource.__init__(self)
        self.xsl = open(XSL_FILE % dict(adminConfig)).read()
        self.lastModified = datetime.utcnow()
        self.etag = hashlib.md5(self.xsl.encode('utf-8')).hexdigest()

    def _sameContent(self, request):
        etag = request.requestHeaders.getRawHeaders('If-None-Match')
        if not etag:
            etag = request.requestHeaders.getRawHeaders('if-none-match')
        if etag:
            return etag[0] == self.etag
        return False

    def render_HEAD(self, request):
        request.setHeader('ETag', self.etag)
        if self._sameContent(request):
            request.setResponseCode(304)
        return b''

    def render_GET(self, request):
        request.setHeader('Content-Type','text/xml')
        request.setHeader('ETag', self.etag)
        if self._sameContent(request):
            request.setResponseCode(304)
            return b''
        return self.xsl.encode('utf-8')


class BaseXmlResource(resource.Resource):

    def __init__(self, adminConfig, config, authenticated=True):
        resource.Resource.__init__(self)
        self.adminConfig = adminConfig
        self.config = config
        self.authenticated = authenticated
        self.xsl = open(XSL_FILE % dict(adminConfig)).read()
        self.username = adminConfig.AdminUser
        self.password = adminConfig.AdminPassword

    def _makeNonAdminURI(self, request, path):
        return 'http://%s:%d%s' % (
                request.getRequestHostname().decode('utf-8'),
                self.adminConfig.FiveserverWebPort, path)

    def render(self, request):
        if not self.authenticated:
            return resource.Resource.render(self, request)
        username, password = request.getUser(), request.getPassword()
        if username:
            username = username.decode('utf-8')
        if password:
            password = password.decode('utf-8')
        if username in [None,b'']:
            request.setHeader('WWW-authenticate',
                'Basic realm="fiveserver"')
            request.setResponseCode(401)
            return b''
        elif username==self.username and password==self.password:
            return resource.Resource.render(self, request)
        else:
            request.setResponseCode(403)
            request.setHeader('Content-Type', 'text/plain')
            return b'Not authorized'

    def renderError(self, error, request, responseCode=500):
        request.setHeader('Content-Type', 'text/xml')
        request.setResponseCode(responseCode)
        log.msg('SERVER ERROR: %s' % str(error.value))
        request.write((
            '%s<error text="server error" href="/home">'
            '<details>%s</details>'
            '</error>' % (XML_HEADER, str(error.value))
        ).encode('utf-8'))
        request.finish()


class AdminRootResource(BaseXmlResource):

    def render_GET(self, request):
        request.setHeader('Content-Type','text/xml')
        return ('%s<adminService version="1.0">\
                <server version="%s" ip="%s"/>\
                <log href="/log"/>\
                <biglog href="/log?n=5000"/>\
                <users href="/users"/>\
                <profiles href="/profiles"/>\
                <onlineUsers href="/users/online"/>\
                <stats href="/stats"/>\
                <userlock href="/userlock"/>\
                <userkill href="/userkill"/>\
                <maxusers value="%d" href="/maxusers"/>\
                <debug enabled="%s" href="/debug"/>\
                <storeSettings enabled="%s" href="/settings"/>\
                <roster href="/roster"/>\
                <banned href="/banned"/>\
                <server-ip href="/server-ip"/>\
                <processInfo href="/ps"/>\
                <cups href="/cups"/>\
                <sendMessage href="/send-message"/>\
                </adminService>' % (
                        XML_HEADER, 
                        self.config.VERSION,
                        self.config.serverIP_wan,
                        self.config.serverConfig.MaxUsers,
                        self.config.serverConfig.Debug,
                        self.config.isStoreSettingsEnabled())).encode('utf-8')


class StatsRootResource(BaseXmlResource):

    def render_GET(self, request):
        request.setHeader('Content-Type','text/xml')
        return ('%s<statsService version="1.0">\
                <server version="%s" ip="%s"/>\
                <users href="/users"/>\
                <profiles href="/profiles"/>\
                <onlineUsers href="/users/online"/>\
                <stats href="/stats"/>\
                <processInfo href="/ps"/>\
                </statsService>' % (
                        XML_HEADER, 
                        self.config.VERSION,
                        self.config.serverIP_wan)).encode('utf-8')


class UsersResource(BaseXmlResource):

    def render_GET(self, request):
        def _renderUsers(results, offset, limit):
            total, records = results
            users = domish.Element((None,'users'))
            users['href'] = '/home'
            users['total'] = str(total)
            for usr in records:
                e = users.addElement('user')
                e['username'] = usr.username
                if usr.nonce is not None:
                    e['locked'] = 'yes'
                    e['href'] = self._makeNonAdminURI(
                        request, '/modifyUser/%s' % usr.nonce)
            next = users.addElement('next')
            next['href'] = '/users?offset=%s&limit=%s' % (
                offset+limit, limit)
            request.setHeader('Content-Type','text/xml')
            request.write(('%s%s' % (
                XML_HEADER, users.toXml())).encode('utf-8'))
            request.finish()
        try: offset = int(request.args['offset'][0])
        except: offset = 0
        try: limit = int(request.args['limit'][0])
        except: limit = 30
        d = self.config.userData.browse(offset=offset, limit=limit)
        d.addCallback(_renderUsers, offset, limit)
        d.addErrback(self.renderError, request)
        return server.NOT_DONE_YET


class UsersOnlineResource(BaseXmlResource):

    def render_GET(self, request):
        request.setHeader('Content-Type','text/xml')
        users = domish.Element((None,'users'))
        users['count'] = str(len(self.config.onlineUsers))
        users['href'] = '/home'
        keys = list(self.config.onlineUsers.keys())
        keys.sort()
        for key in keys:
            usr = self.config.onlineUsers[key]
            e = users.addElement('user')
            try: e['username'] = usr.username
            except AttributeError:
                e['key'] = usr.key
            try: usr.state.lobbyId
            except AttributeError:
                pass
            else:
                if usr.state.lobbyId!=None:
                    try: lobby = self.config.getLobbies()[usr.state.lobbyId]
                    except IndexError:
                        pass
                    else:
                        e['lobby'] = util.toUnicode(lobby.name)
            try: e['profile'] = util.toUnicode(usr.profile.name)
            except AttributeError: pass
            try: e['ip'] = usr.lobbyConnection.addr.host
            except AttributeError: pass
        return ('%s%s' % (XML_HEADER, users.toXml())).encode('utf-8')


class ProfilesResource(BaseXmlResource):
    isLeaf = True

    def render_GET(self, request):
        request.setHeader('Content-Type','text/xml')
        if request.path in [b'/profiles',b'/profiles/']:
            # render list of profiles
            def _renderProfiles(results, offset, limit):
                total, records = results
                profiles = domish.Element((None,'profiles'))
                profiles['href'] = '/home'
                profiles['total'] = str(total)
                for profile in records:
                    e = profiles.addElement('profile')
                    e['name'] = util.toUnicode(profile.name)
                    e['href'] = '/profiles/%s' % profile.id
                next = profiles.addElement('next')
                next['href'] = '/profiles?offset=%s&limit=%s' % (
                    offset+limit, limit)
                request.setHeader('Content-Type','text/xml')
                request.write(('%s%s' % (
                    XML_HEADER, profiles.toXml())).encode('utf-8'))
                request.finish()
            try: offset = int(request.args['offset'][0])
            except: offset = 0
            try: limit = int(request.args['limit'][0])
            except: limit = 30
            d = self.config.profileData.browse(offset=offset, limit=limit)
            d.addCallback(_renderProfiles, offset, limit)
            d.addErrback(self.renderError, request)
            return server.NOT_DONE_YET

        else:
            # specific profile
            def _renderProfileInfo(x):
                profile, stats = x
                root = domish.Element((None, 'profile'))
                root['href'] = '/profiles'
                root['name'] = util.toUnicode(profile.name)
                root['id'] = str(profile.id)
                root.addElement('rank').addContent(str(profile.rank))
                root.addElement('favPlayer').addContent(str(profile.favPlayer))
                root.addElement('favPlayerId').addContent(
                    str(profile.favPlayer & 0x0000ffff))
                root.addElement('favPlayerTeamId').addContent(
                    str((profile.favPlayer >> 16) & 0x0000ffff))
                root.addElement('favTeam').addContent(str(profile.favTeam))
                root.addElement('points').addContent(str(profile.points))
                root.addElement('division').addContent(
                    str(self.config.ratingMath.getDivision(profile.points)))
                root.addElement('disconnects').addContent(
                    str(profile.disconnects))
                root.addElement('playTime').addContent(str(profile.playTime))
                games = stats.wins + stats.draws + stats.losses
                root.addElement('games').addContent(str(games))
                root.addElement('wins').addContent(str(stats.wins))
                root.addElement('draws').addContent(str(stats.draws))
                root.addElement('losses').addContent(str(stats.losses))
                root.addElement('goalsScored').addContent(
                    str(stats.goals_scored))
                root.addElement('goalsAllowed').addContent(
                    str(stats.goals_allowed))
                root.addElement('winningStreakCurrent').addContent(
                    str(stats.streak_current))
                root.addElement('winningStreakBest').addContent(
                    str(stats.streak_best))
                if games>0: 
                    winPct = stats.wins/float(games)
                    avglscr = stats.goals_scored/float(games)
                    avglcon = stats.goals_allowed/float(games)
                else:
                    winPct = 0.0
                    avglscr = 0.0
                    avglcon = 0.0
                root.addElement('winningPct').addContent(
                    '%0.1f%%' % (winPct*100.0))
                root.addElement('goalsScoredAverage').addContent(
                    '%0.2f' % avglscr)
                root.addElement('goalsAllowedAverage').addContent(
                    '%0.2f' % avglcon)
                request.write(('%s%s' % (
                    XML_HEADER, root.toXml())).encode('utf-8'))
                request.finish()
            profile_name = request.path.split(b'/')[-1].decode('utf-8')
            try: 
                profile_id = int(profile_name)
                d = self.config.profileLogic.getFullProfileInfoById(
                    profile_id)
            except ValueError:
                d = self.config.profileLogic.getFullProfileInfoByName(
                    profile_name)
            d.addCallback(_renderProfileInfo)
            d.addErrback(self.renderError, request)
            return server.NOT_DONE_YET


class StatsResource(BaseXmlResource):

    def render_GET(self, request):
        request.setHeader('Content-Type','text/xml')
        root = domish.Element((None,'stats'))
        root['playerCount'] = str(len(self.config.onlineUsers))
        root['href'] = '/home'
        lobbiesElem = root.addElement('lobbies')
        lobbiesElem['count'] = str(len(self.config.lobbies))
        for lobby in self.config.lobbies:
            lobbyElem = lobbiesElem.addElement('lobby')
            lobbyElem['type'] = lobby.typeStr
            lobbyElem['showMatches'] = str(lobby.showMatches)
            lobbyElem['checkRosterHash'] = str(lobby.checkRosterHash)
            lobbyElem['name'] = util.toUnicode(lobby.name)
            lobbyElem['playerCount'] = str(len(lobby.players))
            lobbyElem['roomCount'] = str(len(lobby.rooms))
            m = len([room.match for room in lobby.rooms.values() 
                if room is not None and room.match is not None])
            lobbyElem['matchesInProgress'] = str(m)
            for usr in lobby.players.values():
                userElem = lobbyElem.addElement('user')
                userElem['profile'] = util.toUnicode(usr.profile.name)
                try: userElem['ip'] = usr.lobbyConnection.addr.host
                except AttributeError: pass
            if m>0 and lobby.showMatches:
                matchesElem = lobbyElem.addElement('matches')
                matchRooms = [room for room in lobby.rooms.values()
                    if room is not None and room.match is not None]
                matchRooms.sort()
                for room in matchRooms:
                    matchElem = matchesElem.addElement('match')
                    matchElem['roomName'] = util.toUnicode(room.name)
                    matchElem['matchTime'] = str(room.matchTime)
                    matchElem['score'] = '%d:%d' % (
                        room.match.score_home, room.match.score_away)
                    matchElem['homeTeamId'] = str(room.match.home_team_id)
                    matchElem['awayTeamId'] = str(room.match.away_team_id)
                    if isinstance(room.match, Match):
                        if room.match.home_profile:
                            matchElem['homeProfile'] = util.toUnicode(
                                room.match.home_profile.name)
                        if room.match.away_profile:
                            matchElem['awayProfile'] = util.toUnicode(
                                room.match.away_profile.name)
                    elif isinstance(room.match, Match6):
                        matchElem['clock'] = str(room.match.clock)
                        matchElem['state'] = MatchState.stateText.get(
                            room.match.state, 'Unknown')
                        homeTeam = matchElem.addElement('homeTeam')
                        p = homeTeam.addElement('profile')
                        p['name'] = util.toUnicode(
                            room.teamSelection.home_captain.name)
                        for prf in room.teamSelection.home_more_players:
                            p = homeTeam.addElement('profile')
                            p['name'] = util.toUnicode(prf.name)
                        awayTeam = matchElem.addElement('awayTeam')
                        p = awayTeam.addElement('profile')
                        p['name'] = util.toUnicode(
                            room.teamSelection.away_captain.name)
                        for prf in room.teamSelection.away_more_players:
                            p = awayTeam.addElement('profile')
                            p['name'] = util.toUnicode(prf.name)

        return ('%s%s' % (XML_HEADER, root.toXml())).encode('utf-8')


class UserLockResource(BaseXmlResource):

    def render_GET(self, request):
        request.setHeader('Content-Type','text/html')
        return b'''<html><head><title>FiveServer Admin Service</title>
</head><body>
<h3>Enter the username to lock:</h3>
<form name='userlockForm' action='/userlock' method='POST'>
<input name='username' value='' type='text' size='40'/>
<input name='lock' value='lock' type='submit'/>
</form>
</body></html>'''

    def render_POST(self, request):
        def _lockUser(results):
            def _locked(nonce):
                request.write(('''%s<userLocked username="%s" href="/home">
<unlock href="%s"/></userLocked>''' % (
                    XML_HEADER, username, 
                    self._makeNonAdminURI(
                        request, '/modifyUser/%s' % nonce))
                ).encode('utf-8'))
                request.finish()
            def _error(error):
                request.setResponseCode(500)
                log.msg('SERVER ERROR: %s' % str(error.value))
                request.write(('%s<error text="server error"/>' % XML_HEADER).encode('utf-8'))
                request.finish()
            if not results:
                request.setResponseCode(404)
                request.write((
                    '%s<error text="unknown username"/>' % XML_HEADER).encode('utf-8'))
                request.finish()
            d = self.config.lockUser(username)
            d.addCallback(_locked)
            d.addErrback(_error)
            return d
        request.setHeader('Content-Type','text/xml')
        try: username = request.args[b'username'][0].decode('utf-8')
        except KeyError:
            request.setResponseCode(400)
            return ('%s<error '
                    'text="username parameter missing"/>' % XML_HEADER).encode('utf-8')
        d = self.config.userData.findByUsername(username)
        d.addCallback(_lockUser)
        d.addErrback(self.renderError, request)
        return server.NOT_DONE_YET


class UserKillResource(BaseXmlResource):

    def render_GET(self, request):
        request.setHeader('Content-Type','text/html')
        return b'''<html><head><title>FiveServer Admin Service</title>
</head><body>
<h3>Enter the username to delete:</h3>
<p>NOTE: you may be able to restore this user later.</p>
<form name='userkillForm' action='/userkill' method='POST'>
<input name='username' value='' type='text' size='40'/>
<input name='kill' value='delete' type='submit'/>
</form>
</body></html>'''

    def render_POST(self, request):
        def _deleteUser(results):
            def _deleted(nonce):
                request.write((
                    '%s<userDeleted username="%s" href="/home"/>' % (
                    XML_HEADER, username)
                ).encode('utf-8'))
                request.finish()
            def _error(error):
                request.setResponseCode(500)
                log.msg('SERVER ERROR: %s' % str(error.value))
                request.write(('%s<error text="server error"/>' % XML_HEADER).encode('utf-8'))
                request.finish()
            if not results:
                request.setResponseCode(404)
                request.write((
                    '%s<error text="unknown username"/>' % XML_HEADER).encode('utf-8'))
                request.finish()
            d = self.config.deleteUser(username)
            d.addCallback(_deleted)
            d.addErrback(_error)
            return d
        request.setHeader('Content-Type','text/xml')
        try: username = request.args[b'username'][0].decode('utf-8')
        except KeyError:
            request.setResponseCode(400)
            return ('%s<error '
                    'text="username parameter missing"/>' % XML_HEADER).encode('utf-8')
        d = self.config.userData.findByUsername(username)
        d.addCallback(_deleteUser)
        d.addErrback(self.renderError, request)
        return server.NOT_DONE_YET


class LogResource(BaseXmlResource):

    def render_GET(self, request):
        request.setHeader('Content-Type','text/plain')
        logFile = fsroot + "/" + self.adminConfig.FiveserverLogFile
        if os.path.exists(logFile):
            logFile = open(logFile)
            logLines = logFile.readlines()
            logFile.close()
            try: n = int(request.args[b'n'][0])
            except: n = 30
            n = min(len(logLines),n)
            n = max(10,min(5000,n))  # keep n sane: [10,5000]
            request.write(b'Last %d lines of the log:\r\n' % n)
            request.write(b'===========================================\r\n')
            for line in logLines[-n:]:
                request.write(line.encode('utf-8'))
            return b''
        else:
            request.setHeader('Content-Type','text/xml')
            return ('%s<error text="no log file available"/>' % XML_HEADER).encode('utf-8')


class DebugResource(BaseXmlResource):

    def render_GET(self, request):
        request.setHeader('Content-Type','text/html')
        return ('''<html><head><title>FiveServer Admin Service</title>
</head><body>
<h3>Set debug value: (currently: %s)</h3>
<form name='debugForm' action='/debug' method='POST'>
<input name='debug' value='' type='text' size='40'/>
<input name='set' value='set' type='submit'/>
</form>
</body></html>''' % self.config.serverConfig.Debug).encode('utf-8')

    def render_POST(self, request):
        try: debugStr = request.args[b'debug'][0].lower()
        except KeyError: debugStr = ''
        if debugStr in [b'0',b'false',b'no']:
            self.config.serverConfig.Debug = False
        elif debugStr in [b'1',b'true',b'yes']:
            self.config.serverConfig.Debug = True
        log.setDebug(self.config.serverConfig.Debug)
        request.setHeader('Content-Type','text/xml')
        return ('%s<debug enabled="%s" href="/home"/>' % (
                XML_HEADER, self.config.serverConfig.Debug)).encode('utf-8')


class MaxUsersResource(BaseXmlResource):

    def render_GET(self, request):
        request.setHeader('Content-Type','text/html')
        return ('''<html><head><title>FiveServer Admin Service</title>
</head><body>
<h3>Set MaxUsers value: (currently: %s)</h3>
<form name='maxUsersForm' action='/maxusers' method='POST'>
<input name='maxusers' value='' type='text' size='40'/>
<input name='set' value='set' type='submit'/>
</form>
</body></html>''' % self.config.serverConfig.MaxUsers).encode('utf-8')

    def render_POST(self, request):
        try: 
            maxusers = int(request.args[b'maxusers'][0])
        except (KeyError, ValueError): 
            maxusers = self.config.serverConfig.MaxUsers
        if maxusers not in range(1001):
            maxusers = self.config.serverConfig.MaxUsers
            
        self.config.serverConfig.MaxUsers = maxusers
        request.setHeader('Content-Type','text/xml')
        return ('%s<maxUsers value="%s" href="/home"/>' % (
                XML_HEADER, self.config.serverConfig.MaxUsers)).encode('utf-8')


class StoreSettingsResource(BaseXmlResource):

    def render_GET(self, request):
        request.setHeader('Content-Type','text/html')
        return ('''<html><head><title>FiveServer Admin Service</title>
</head><body>
<h3>Set store-settings flag value: (currently: %s)</h3>
<form name='settingsForm' action='/settings' method='POST'>
<input name='store' value='' type='text' size='40'/>
<input name='set' value='set' type='submit'/>
</form>
</body></html>''' % self.config.isStoreSettingsEnabled()).encode('utf-8')

    def render_POST(self, request):
        try: storeStr = request.args[b'store'][0].lower()
        except KeyError: storeStr = ''
        if storeStr in [b'0',b'false',b'no']:
            self.config.serverConfig.StoreSettings = False
        elif storeStr in [b'1',b'true',b'yes']:
            self.config.serverConfig.StoreSettings = True
        request.setHeader('Content-Type','text/xml')
        return ('%s<storeSettings enabled="%s" href="/home"/>' % (
                XML_HEADER, self.config.serverConfig.StoreSettings)).encode('utf-8')


class BannedResource(BaseXmlResource):

    def render_GET(self, request):
        request.setHeader('Content-Type','text/xml')
        banned = domish.Element((None,'banned'))
        banned['href'] = '/home'
        li = banned.addElement('list')
        entries = list(self.config.bannedList.Banned)
        entries.sort()
        for entry in entries:
            e = li.addElement('entry')
            e['href'] = '/ban-remove?entry=%s' % urllib.parse.quote(entry.encode('utf-8'), safe='')
            e['spec'] = entry
            #e.addContent(entry)
        banned.addElement('add')['href'] = '/ban-add'
        return ('%s%s' % (XML_HEADER, banned.toXml())).encode('utf-8')


class BanAddResource(BaseXmlResource):

    def render_GET(self, request):
        request.setHeader('Content-Type','text/html')
        try: entry = request.args[b'entry'][0]
        except KeyError: entry = ''
        return ('''<html><head><title>FiveServer Admin Service</title>
<style>span.ip {color:#800;}</style>
</head><body>
<h3>New entry to add to the banned list:</h3>
<p>
<form name='banForm' action='/ban-add' method='POST'>
<input name='entry' value='%(entry)s' type='text' size='40'/>
<input name='add' value='add' type='submit'/>
</form>
</p>
<p>
<br />
You can either use specific IP or a network, with or without mask 
(specified as bits).<br />Here are some examples:
</p>
<p>
<span class="ip">75.120.4.205</span> 
- bans just this one IP<br />
<span class="ip">75.120.4</span>
- bans all IPs in network, specified by 24-bit address: 
75.120.4.1 - 75.120.4.255<br />
<span class="ip">75.120.4/24</span>
- same as above<br />
<span class="ip">75.120.4/22</span>
- bans all IPs in network, specified by 22-bit address: 
75.120.4.1 - 75.120.7.255<br />
<span class="ip">192.168</span>
- bans all IPs in network, specified by 16-bit address: 
192.168.0.1 - 192.168.255.255<br />
<span class="ip">192.168.</span>
- same as above<br />
<span class="ip">192.168.0.0/16</span>
- same as above
</p>
</body></html>''' % {'entry':entry}).encode('utf-8')

    def render_POST(self, request):
        request.setHeader('Content-Type','text/xml')
        try: entry = request.args[b'entry'][0]
        except KeyError: entry = b''
        entry = entry.decode('utf-8')
        try:
            try: entryIndex = self.config.bannedList.Banned.index(entry)
            except ValueError:
                if entry.strip()!=b'':
                    self.config.bannedList.Banned.append(entry)
                    self.config.bannedList.save()
                    self.config.makeFastBannedList()
            return ('%s<actionAccepted href="/banned" />' % XML_HEADER).encode('utf-8')
        except Exception as info:
            request.setResponseCode(500)
            log.msg('SERVER ERROR: %s' % info)
            return ('%s<error text="server error"/>' % XML_HEADER).encode('utf-8')


class BanRemoveResource(BaseXmlResource):

    def render_GET(self, request):
        request.setHeader('Content-Type','text/html')
        try: entry = request.args[b'entry'][0]
        except KeyError: entry = b''
        entry = entry.decode('utf-8')
        return ('''<html><head><title>FiveServer Admin Service</title>
</head><body>
<h3>Remove this entry from the banned list:</h3>
<form name='banForm' action='/ban-remove' method='POST'>
<input name='entry' value='%(entry)s' type='text' size='40'/>
<input name='remove' value='remove' type='submit'/>
</form>
</body></html>''' % {'entry':entry}).encode('utf-8')

    def render_POST(self, request):
        request.setHeader('Content-Type','text/xml')
        try: entry = request.args[b'entry'][0]
        except KeyError: entry = b''
        entry = entry.decode('utf-8')
        try:
            try: entryIndex = self.config.bannedList.Banned.index(entry)
            except ValueError:
                pass
            else:
                del self.config.bannedList.Banned[entryIndex]
                self.config.bannedList.save()
                self.config.makeFastBannedList()
            return ('%s<actionAccepted href="/banned" />' % XML_HEADER).encode('utf-8')
        except Exception as info:
            request.setResponseCode(500)
            log.msg('SERVER ERROR: %s' % info)
            return ('%s<error text="server error"/>' % XML_HEADER).encode('utf-8')


class ServerIpResource(BaseXmlResource):
    
    def render_GET(self, request):
        request.setHeader('Content-Type','text/html')
        return ('''<html><head><title>FiveServer Admin Service</title>
</head><body>
<h3>Current server IP is: %(ip)s</h3>
<form name='ipRequeryForm' action='/server-ip' method='POST'>
<input name='requery' value='requery' type='submit'/>
</form>
</body></html>''' % {'ip':self.config.serverIP_wan}).encode('utf-8')

    def render_POST(self, request):
        self.config.setIP(resetTime=False)
        request.setHeader('Content-Type','text/xml')
        return ('%s<serverIP-requery started="true" href="/home"/>' % (
                XML_HEADER)).encode('utf-8')


class RosterResource(BaseXmlResource):

    def render_GET(self, request):
        request.setHeader('Content-Type','text/html')
        try: enforceHash = self.config.serverConfig.Roster['enforceHash']
        except: enforceHash = False
        try: compareHash = self.config.serverConfig.Roster['compareHash']
        except: compareHash = False
        return ('''<html><head><title>FiveServer Admin Service</title>
</head><body>
<h3>Edit roster-verification settings</h3>
<form name='rosterSettingsForm' action='/roster' method='POST'>
<table>
<tr>
<td>enforce hash:</td>
<td><input name='enforceHash' value='%(enforceHash)s' type='text' size='10'/>
</td></tr>
<tr>
<td>compare hash:</td>
<td><input name='compareHash' value='%(compareHash)s' type='text' size='10'/>
</td></tr>
</table>
<input name='submit' value='submit' type='submit'/>
</form>
</body></html>''' % {
'enforceHash':enforceHash,
'compareHash':compareHash}).encode('utf-8')

    def render_POST(self, request):
        try: 
            enforceHash = request.args[b'enforceHash'][0].lower() in [
                b'1',b'true']
            compareHash = request.args[b'compareHash'][0].lower() in [
                b'1',b'true']
            self.config.serverConfig.Roster = {
                'enforceHash':enforceHash,
                'compareHash':compareHash}
            request.setHeader('Content-Type','text/xml')
            return ('%s<result text="roster settings changed" '
                    'href="/home"/>' % XML_HEADER).encode('utf-8')
        except IndexError:
            request.setHeader('Content-Type','text/xml')
            return ('%s<error text="missing or incorrect parameters" '
                    'href="/home"/>' % XML_HEADER).encode('utf-8')


class SendMessageResource(BaseXmlResource):
    """Send an inbox message to a player by profile name. GET/POST /send-message"""

    isLeaf = True

    def render_GET(self, request):
        request.setHeader('Content-Type', 'text/html')
        return b'''<html><head><title>Send Message</title></head><body>
<h3>Send Inbox Message</h3>
<form method="POST">
To (profile name): <input name="to_name" type="text" size="32"/><br/>
Subject: <input name="subject" type="text" size="64"/><br/>
Body:<br/><textarea name="body" rows="6" cols="60"></textarea><br/>
<input type="submit" value="Send"/>
</form></body></html>'''

    def render_POST(self, request):
        def _sent(_):
            request.setHeader('Content-Type', 'text/xml')
            request.write(('%s<actionAccepted href="/home"/>' % XML_HEADER).encode('utf-8'))
            request.finish()

        def _gotProfile(profiles):
            if not profiles:
                request.setResponseCode(404)
                request.setHeader('Content-Type', 'text/xml')
                request.write(('%s<error text="profile not found"/>' % XML_HEADER).encode('utf-8'))
                request.finish()
                return
            to_profile = profiles[0]
            d = self.config.messageData.sendMessage(
                to_profile.id, None, subject, body)
            d.addCallback(_sent)
            d.addErrback(self.renderError, request)

        try:
            to_name = request.args[b'to_name'][0].decode('utf-8')
            subject = request.args.get(b'subject', [b''])[0].decode('utf-8')[:64]
            body = request.args.get(b'body', [b''])[0].decode('utf-8')[:512]
        except (KeyError, UnicodeDecodeError):
            request.setResponseCode(400)
            return ('%s<error text="to_name required"/>' % XML_HEADER).encode('utf-8')

        if not self.config.messageData:
            request.setResponseCode(503)
            return ('%s<error text="messaging not available"/>' % XML_HEADER).encode('utf-8')

        d = self.config.profileData.findByName(to_name)
        d.addCallback(_gotProfile)
        d.addErrback(self.renderError, request)
        return server.NOT_DONE_YET


class CupsResource(BaseXmlResource):
    """List cups and create new cups. GET /cups, POST /cups"""

    isLeaf = False

    def render_GET(self, request):
        def _render(rows):
            rows_html = ''
            for row in rows:
                id, name, cup_type, status, created_on, finished_on = row
                finished = str(finished_on) if finished_on else '-'
                rows_html += (
                    '<tr><td><a href="/cups/%d">%s</a></td>'
                    '<td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>'
                    % (id, escape(name), cup_type, status, str(created_on), finished))
            html = '''<!DOCTYPE html><html><head><title>Cups</title>
<style>body{font-family:Arial,sans-serif;margin:2em}
table{border-collapse:collapse;width:100%%}
th,td{border:1px solid #ccc;padding:6px 10px;text-align:left}
th{background:#f0f0f0}a{color:#080}
input,select{margin:4px;padding:4px}
h2{margin-top:1.5em}</style></head><body>
<h1>Cups</h1>
<table><tr><th>Name</th><th>Type</th><th>Status</th><th>Created</th><th>Finished</th></tr>
%s</table>
<h2>Create Cup</h2>
<form method="POST">
Name: <input name="name" type="text" size="30" required/>
Type: <select name="type">
  <option value="winnerscup">Winners Cup</option>
  <option value="competition">Competition</option>
</select>
<input type="submit" value="Create"/>
</form>
</body></html>''' % rows_html
            request.setHeader('Content-Type', 'text/html')
            request.write(html.encode('utf-8'))
            request.finish()
        d = self.config.cupData.listCups()
        d.addCallback(_render)
        d.addErrback(self.renderError, request)
        return server.NOT_DONE_YET

    def render_POST(self, request):
        def _render(cup_id):
            request.setResponseCode(302)
            request.setHeader('Location', '/cups/%d' % cup_id)
            request.finish()
        try:
            name = request.args[b'name'][0].decode('utf-8')
            cup_type = request.args.get(b'type', [b'winnerscup'])[0].decode('utf-8')
            if cup_type not in ('competition', 'winnerscup'):
                cup_type = 'winnerscup'
        except (KeyError, UnicodeDecodeError):
            request.setResponseCode(400)
            request.setHeader('Content-Type', 'text/xml')
            return ('%s<error text="name parameter required"/>' % XML_HEADER).encode('utf-8')
        d = self.config.cupData.createCup(name, cup_type)
        d.addCallback(_render)
        d.addErrback(self.renderError, request)
        return server.NOT_DONE_YET

    def getChildWithDefault(self, path, request):
        try:
            cup_id = int(path)
            return CupDetailResource(self.adminConfig, self.config, cup_id)
        except (ValueError, TypeError):
            return resource.NoResource()


class CupDetailResource(BaseXmlResource):
    """Show bracket and participants for a single cup. GET /cups/{id}"""

    isLeaf = False

    def __init__(self, adminConfig, config, cup_id):
        BaseXmlResource.__init__(self, adminConfig, config)
        self.cup_id = cup_id

    def render_GET(self, request):
        d = defer.gatherResults([
            self.config.cupData.getCupById(self.cup_id),
            self.config.cupData.getCupParticipants(self.cup_id),
            self.config.cupData.getCupMatches(self.cup_id),
        ])

        def _render(results):
            cup_row, participants, matches = results
            if cup_row is None:
                request.setResponseCode(404)
                request.setHeader('Content-Type', 'text/html')
                request.write(b'<h1>Cup not found</h1>')
                request.finish()
                return
            id, name, cup_type, status, created_on, finished_on = cup_row

            names = {pid: pname for pid, pname, _, _ in participants}

            participants_html = ''
            for profile_id, pname, points, pstatus in participants:
                participants_html += (
                    '<tr><td>%s</td><td>%d</td><td>%s</td>'
                    '<td><form method="POST" action="/cups/%d/remove" style="margin:0">'
                    '<input type="hidden" name="profile_id" value="%d"/>'
                    '<input type="submit" value="Remove"/></form></td></tr>'
                    % (escape(pname), points, pstatus, id, profile_id))

            rounds = {}
            for row in matches:
                (mid, cup_id, match_id, rnd,
                 home_id, away_id, winner_id, mstatus, played_on) = row
                rounds.setdefault(rnd, []).append(row)

            bracket_html = ''
            for rnd in sorted(rounds):
                bracket_html += '<h3>Round %d</h3><table><tr><th>Home</th><th>Away</th><th>Winner</th><th>Status</th><th>Played</th><th></th></tr>' % rnd
                for row in rounds[rnd]:
                    (mid, cup_id, match_id, rnd2,
                     home_id, away_id, winner_id, mstatus, played_on) = row
                    home_name = escape(names.get(home_id, str(home_id)))
                    away_name = escape(names.get(away_id, str(away_id)))
                    winner_name = escape(names.get(winner_id, '-')) if winner_id else '-'
                    played = str(played_on) if played_on else '-'
                    walkover_btn = ''
                    if mstatus == 'pending':
                        walkover_btn = '<a href="/cups/%d/walkover?cup_match_id=%d">Walkover</a>' % (id, mid)
                    bracket_html += (
                        '<tr><td>%s</td><td>%s</td><td>%s</td>'
                        '<td>%s</td><td>%s</td><td>%s</td></tr>'
                        % (home_name, away_name, winner_name, mstatus, played, walkover_btn))
                bracket_html += '</table>'

            activate_btn = ''
            if status == 'open':
                activate_btn = '''<form method="POST" action="/cups/%d/activate">
<input type="submit" value="Activate Cup (lock roster &amp; generate bracket)"/>
</form>''' % id

            finished_str = ('Finished: %s' % finished_on) if finished_on else ''

            html = '''<!DOCTYPE html><html><head><title>Cup: {name}</title>
<style>body{{font-family:Arial,sans-serif;margin:2em}}
table{{border-collapse:collapse;margin-bottom:1em}}
th,td{{border:1px solid #ccc;padding:6px 10px;text-align:left}}
th{{background:#f0f0f0}}a{{color:#080}}
input,select{{margin:4px;padding:4px}}
h2{{margin-top:1.5em}}</style></head><body>
<a href="/cups">&larr; All Cups</a>
<h1>{name} <small style="font-size:0.6em;color:#666">{cup_type} &mdash; {status}</small></h1>
<p>Created: {created} {finished}</p>
{activate_btn}
<h2>Participants</h2>
<table><tr><th>Name</th><th>Points</th><th>Status</th><th></th></tr>
{participants_html}</table>
<h3>Add Participant</h3>
<form method="POST" action="/cups/{id}/add">
Profile name: <input name="profile_name" type="text" size="30" required/>
<input type="submit" value="Add"/>
</form>
<h2>Bracket</h2>
{bracket_html}
</body></html>'''.format(
                name=escape(name), cup_type=cup_type, status=status,
                created=str(created_on), finished=finished_str,
                activate_btn=activate_btn, participants_html=participants_html,
                id=id, bracket_html=bracket_html or '<p>Not yet generated.</p>')

            request.setHeader('Content-Type', 'text/html')
            request.write(html.encode('utf-8'))
            request.finish()

        d.addCallback(_render)
        d.addErrback(self.renderError, request)
        return server.NOT_DONE_YET

    def getChildWithDefault(self, path, request):
        if path == b'add':
            return CupAddParticipantResource(
                self.adminConfig, self.config, self.cup_id)
        if path == b'remove':
            return CupRemoveParticipantResource(
                self.adminConfig, self.config, self.cup_id)
        if path == b'activate':
            return CupActivateResource(
                self.adminConfig, self.config, self.cup_id)
        if path == b'walkover':
            return CupWalkoverResource(
                self.adminConfig, self.config, self.cup_id)
        return resource.NoResource()


class CupAddParticipantResource(BaseXmlResource):
    """Add a player to a cup. GET shows form, POST adds. /cups/{id}/add"""

    isLeaf = True

    def __init__(self, adminConfig, config, cup_id):
        BaseXmlResource.__init__(self, adminConfig, config)
        self.cup_id = cup_id

    def render_GET(self, request):
        request.setHeader('Content-Type', 'text/html')
        return ('''<html><head><title>Add Cup Participant</title></head><body>
<h3>Add participant to cup %d</h3>
<form method="POST">
Profile name: <input name="profile_name" type="text" size="32"/>
<input type="submit" value="Add"/>
</form></body></html>''' % self.cup_id).encode('utf-8')

    def render_POST(self, request):
        def _added(_):
            request.setResponseCode(302)
            request.setHeader('Location', '/cups/%d' % self.cup_id)
            request.finish()

        def _gotProfile(profiles):
            if not profiles:
                request.setResponseCode(404)
                request.setHeader('Content-Type', 'text/xml')
                request.write(('%s<error text="profile not found"/>' % XML_HEADER).encode('utf-8'))
                request.finish()
                return
            profile = profiles[0]
            d = self.config.cupData.addParticipant(self.cup_id, profile.id)
            d.addCallback(_added)
            d.addErrback(self.renderError, request)

        try:
            profile_name = request.args[b'profile_name'][0].decode('utf-8')
        except (KeyError, UnicodeDecodeError):
            request.setResponseCode(400)
            return ('%s<error text="profile_name required"/>' % XML_HEADER).encode('utf-8')
        d = self.config.profileData.findByName(profile_name)
        d.addCallback(_gotProfile)
        d.addErrback(self.renderError, request)
        return server.NOT_DONE_YET


class CupRemoveParticipantResource(BaseXmlResource):
    """Remove a player from a cup. POST /cups/{id}/remove?profile_id=N"""

    isLeaf = True

    def __init__(self, adminConfig, config, cup_id):
        BaseXmlResource.__init__(self, adminConfig, config)
        self.cup_id = cup_id

    def render_GET(self, request):
        try:
            profile_id = int(request.args[b'profile_id'][0])
        except (KeyError, ValueError):
            return ('%s<error text="profile_id required"/>' % XML_HEADER).encode('utf-8')
        request.setHeader('Content-Type', 'text/html')
        return ('''<html><head><title>Remove Cup Participant</title></head><body>
<h3>Remove profile %d from cup %d?</h3>
<form method="POST">
<input type="hidden" name="profile_id" value="%d"/>
<input type="submit" value="Remove"/>
</form></body></html>''' % (profile_id, self.cup_id, profile_id)).encode('utf-8')

    def render_POST(self, request):
        def _done(_):
            request.setResponseCode(302)
            request.setHeader('Location', '/cups/%d' % self.cup_id)
            request.finish()
        try:
            profile_id = int(request.args[b'profile_id'][0])
        except (KeyError, ValueError):
            request.setResponseCode(400)
            return ('%s<error text="profile_id required"/>' % XML_HEADER).encode('utf-8')
        d = self.config.cupData.removeParticipant(self.cup_id, profile_id)
        d.addCallback(_done)
        d.addErrback(self.renderError, request)
        return server.NOT_DONE_YET


class CupActivateResource(BaseXmlResource):
    """Activate a cup (lock roster and generate bracket). POST /cups/{id}/activate"""

    isLeaf = True

    def __init__(self, adminConfig, config, cup_id):
        BaseXmlResource.__init__(self, adminConfig, config)
        self.cup_id = cup_id

    def render_GET(self, request):
        request.setHeader('Content-Type', 'text/html')
        return ('''<html><head><title>Activate Cup</title></head><body>
<h3>Activate cup %d? (locks roster and generates bracket)</h3>
<form method="POST">
<input type="submit" value="Activate"/>
</form></body></html>''' % self.cup_id).encode('utf-8')

    def render_POST(self, request):
        def _done(ok):
            if not ok:
                request.setResponseCode(400)
                request.setHeader('Content-Type', 'text/html')
                request.write(b'<h1>Error: need at least 2 participants</h1>')
                request.finish()
                return
            request.setResponseCode(302)
            request.setHeader('Location', '/cups/%d' % self.cup_id)
            request.finish()
        d = self.config.cupData.activateCup(self.cup_id)
        d.addCallback(_done)
        d.addErrback(self.renderError, request)
        return server.NOT_DONE_YET


class CupWalkoverResource(BaseXmlResource):
    """Grant a walkover win in a cup match. GET form, POST /cups/{id}/walkover?cup_match_id=N"""

    isLeaf = True

    def __init__(self, adminConfig, config, cup_id):
        BaseXmlResource.__init__(self, adminConfig, config)
        self.cup_id = cup_id

    def render_GET(self, request):
        try:
            cup_match_id = int(request.args[b'cup_match_id'][0])
        except (KeyError, ValueError):
            return ('%s<error text="cup_match_id required"/>' % XML_HEADER).encode('utf-8')

        d = defer.gatherResults([
            self.config.cupData.getCupParticipants(self.cup_id),
            self.config.cupData.getCupMatches(self.cup_id),
        ])

        def _render(results):
            participants, matches = results
            names = {pid: pname for pid, pname, _, _ in participants}
            match_row = next((r for r in matches if r[0] == cup_match_id), None)
            if match_row is None:
                request.setHeader('Content-Type', 'text/html')
                request.write(b'<h1>Match not found</h1>')
                request.finish()
                return
            (mid, _, _, rnd, home_id, away_id, _, _, _) = match_row
            home_name = escape(names.get(home_id, str(home_id)))
            away_name = escape(names.get(away_id, str(away_id)))
            html = ('''<!DOCTYPE html><html><head><title>Cup Walkover</title></head><body>
<a href="/cups/%d">&larr; Back to Cup</a>
<h3>Grant walkover for match: %s vs %s</h3>
<form method="POST">
<input type="hidden" name="cup_match_id" value="%d"/>
Winner: <select name="winner_profile_id">
<option value="%d">%s</option>
<option value="%d">%s</option>
</select>
<input type="submit" value="Grant Walkover"/>
</form></body></html>''' % (
                self.cup_id, home_name, away_name,
                cup_match_id,
                home_id, home_name, away_id, away_name))
            request.setHeader('Content-Type', 'text/html')
            request.write(html.encode('utf-8'))
            request.finish()

        d.addCallback(_render)
        d.addErrback(self.renderError, request)
        return server.NOT_DONE_YET

    def render_POST(self, request):
        def _done(_):
            request.setResponseCode(302)
            request.setHeader('Location', '/cups/%d' % self.cup_id)
            request.finish()
        try:
            cup_match_id = int(request.args[b'cup_match_id'][0])
            winner_profile_id = int(request.args[b'winner_profile_id'][0])
        except (KeyError, ValueError):
            request.setResponseCode(400)
            return ('%s<error text="cup_match_id and winner_profile_id required"/>' % XML_HEADER).encode('utf-8')
        d = self.config.cupData.walkover(cup_match_id, winner_profile_id)
        d.addCallback(_done)
        d.addErrback(self.renderError, request)
        return server.NOT_DONE_YET


class ProcessInfoResource(BaseXmlResource):

    def render_GET(self, request):
        def writeInfo(p, request):
            if p is None:
                class Process:
                    def __init__(self,pid):
                        self.pid = pid
                        status,output = commands.getstatusoutput(
                                'ps -o %%cpu,rss %s' % self.pid)
                        cpu, rss = output.split()[-2:]
                        self.cpu = float(cpu)
                        self.rss = int(rss)
                    def get_memory_info(self):
                        return (self.rss*1024,0)
                    def get_cpu_percent(self):
                        return self.cpu
                p = Process(os.getpid())
            request.setHeader('Content-Type','text/xml')
            procInfo = domish.Element((None,'processInfo'))
            procInfo['href'] = '/home'
            procInfo['pid'] = str(p.pid)
            uptime = procInfo.addElement('uptime')
            uptime['since'] = str(self.config.startDatetime)
            uptime['up'] = str(datetime.now() - self.config.startDatetime)
            stats = procInfo.addElement('stats')
            stats['cpu'] = '%0.1f%%' % p.get_cpu_percent()
            stats['mem'] = '%0.1fM' % (
                    p.get_memory_info()[0]/1024.0/1024)
            extra = procInfo.addElement('info')
            extra['cmdline'] = ' '.join(sys.argv)
            request.write(XML_HEADER.encode('utf-8'))
            request.write(procInfo.toXml().encode('utf-8'))
            request.finish()
        try: self.process
        except AttributeError:
            try: self.process = psutil.Process(os.getpid())
            except NameError:
                self.process = None
        d = defer.Deferred()
        d.addCallback(writeInfo, request)
        reactor.callLater(0.1, d.callback, self.process)
        return server.NOT_DONE_YET

