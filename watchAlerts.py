#!/usr/bin/env python
import aprslib
from datetime import  datetime, timedelta
from dateutil.parser import parse
import gc
import objgraph
import pyproj
import pytz
import re
import requests
import sqlite3
import schedule
import sys
import telnetlib
from threading import Thread, Lock
from time import sleep
import tweepy

import urllib
import json
import pprint

from sotakeys import *
from last3 import *

debug = False
#debug = True

sotawatch_url = KEYS['SOTA_URL']
sotawatch_json_url = KEYS['SOTAWATCH_JSON_URL']
output_json_file = KEYS['OUTPUT_JSON_FILE']
output_json_jafile = KEYS['OUTPUT_JSON_JAFILE']
summit_db = KEYS['SUMMIT_DB']
dxsummit_db = KEYS['DXSUMMIT_DB']
alert_db = KEYS['ALERT_DB']
aprslog_db = KEYS['APRSLOG_DB']
last3 = KEYS['LAST3']
last3dx = KEYS['LAST3DX']
aprs_user = KEYS['APRS_USER']
aprs_password = KEYS['APRS_PASSWD']
aprs_host = KEYS['APRS_HOST']
aprs_port = KEYS['APRS_PORT']
tweet_at = KEYS['TWEET_AT']
update_alerts_every = KEYS['UPDATE_ALERTS_EVERY']
update_spots_every = KEYS['UPDATE_SPOTS_EVERY']

tweet_api = None

aprs_filter = ""
aprs_beacon = None

localtz = pytz.timezone('Asia/Tokyo')
grs80 = pyproj.Geod(ellps='GRS80')
#3000m x 3000m
deltalat,deltalng = 0.002704*10,0.003311*10

def tweet(api, txt):
    if debug:
        print txt
    else:
        if len(txt) > 140:
            txt = txt[0:140]
	try:
            api.update_status(status=txt)
	except Exception, e:
            print >>sys.stderr, 'tweet error: %s ' % e
            print >>sys.stderr, 'txt = %s ' % txt 
            return

def tweet_with_media(api, fname, txt):
    if debug:
        print txt
    else:
        if len(txt) > 110:
            txt = txt[0:110]
        try:
            api.update_with_media(fname, status=txt)
        except Exception, e:
            print >>sys.stderr, 'tweet error %s ' % e
            print >>sys.stderr, 'txt = %s ' % txt 
	    return

def lookup_from_op(op):
    conn_alert = sqlite3.connect(alert_db)
    cur_alert = conn_alert.cursor()
    cur_beacon = conn_alert.cursor()
    
    op = op[0:op.rfind('-')].strip()
    q = 'select * from beacons where operator = ?'
    cur_beacon.execute(q,(op,))
    r = cur_beacon.fetchall()
    if r:
        for (start,end,op,_,_,_,_,_,_,_,state,name,m,m2,tlon,lasttweet,mode) in r:
            if state == -2:
                tm = datetime.fromtimestamp(int(start)).strftime("%H:%M")
                mesg = "No beacons received. Upcoming Activation: " + tm + " " + name
                break
            else:
                mesg = m2
    else:
        q = 'select * from alerts where operator = ?'
        cur_alert.execute(q,(op,))
        r = cur_alert.fetchall()
        if r:
            mesg = "Out of notification time window. Upcoming Activations: "
            for (time,_,_,_,_,summit,_,_,_,_) in r:
                tm = datetime.fromtimestamp(int(time)).strftime("%m/%d %H:%M")
                mesg = mesg + tm + " " + summit + " "
                break
        else:
            mesg = "No Upcoming Activations."

    conn_alert.close()
    return mesg

def lookup_summit(op,lat,lng):
    op = op[0:op.rfind('-')].strip()
    if op in KEYS['EXCLUDE_USER']:
        return (True,-1, 0, "Oops!")

    mag = KEYS['MAGNIFY']
    conn_summit = sqlite3.connect(summit_db)
    cur_summit = conn_summit.cursor()
    conn_dxsummit = sqlite3.connect(dxsummit_db)
    cur_dxsummit = conn_dxsummit.cursor()
    conn_beacon = sqlite3.connect(alert_db)
    cur_beacon = conn_beacon.cursor()
    conn_aprslog = sqlite3.connect(aprslog_db)
    cur_aprslog = conn_aprslog.cursor()

    q = 'select * from beacons where operator = ?'
    cur_beacon.execute(q,(op,))
    state = -1
    now = int(datetime.utcnow().strftime("%s"))
    nowstr = datetime.fromtimestamp(now).strftime("%H:%M")

    for (_,_,_,_,_,_,lat_dest,lng_dest,_,_,state,code,mesg,mesg2,tlon,lasttweet,mode) in cur_beacon.fetchall():
        latu,latl = lat + deltalat*mag, lat - deltalat*mag
        lngu,lngl = lng + deltalng*mag, lng - deltalng*mag
        result = []

        if re.search(KEYS['JASummits'],code):
            foreign = False
            for s in cur_summit.execute("select * from summits where (? > lat) and (? < lat) and (? > lng) and (? < lng)",(latu,latl,lngu,lngl,)):
                (code,lat1,lng1,pt,alt,name,desc,_,_)= s
                az,bkw_az,dist = grs80.inv(lng,lat,lng1,lat1)
                result.append((code,int(dist),int(az),pt,alt,name,desc))
        else:
            foreign = True
            for s in cur_dxsummit.execute("select * from summits where (? > lat) and (? < lat) and (? > lng) and (? < lng)",(latu,latl,lngu,lngl,)):
                (code,lat1,lng1,pt,alt,name,desc)= s
                az,bkw_az,dist = grs80.inv(lng,lat,lng1,lat1)
                result.append((code,int(dist),int(az),pt,alt,name,desc))
            
        result.sort(key=lambda x:x[1])
        result = result[0:3]
        if len(result) > 0:
            (_,dist,_,_,_,_,_) = result[0]
            if dist <=100.0:
                if state < 3:
                    state = 3
                else:
                    state = 4
            elif dist <=300.0:
                if state < 1:
                    state = 1
                elif state ==1:
                    state = 2
                elif state == 4:
                    state = 5
            else:
                if state >= 3:
                    state = 6
                else:
                    state = 0

            if state == 3 or state == 4:
                (code,dist,az,pt,alt,name,desc) = result[0]
                mesg = "Welcome to " + code +". "+ name + " " + str(alt) + "m "+ str(pt) + "pt.\n"+desc+"."
                mesg2 = code + " - " + name + " " + str(alt) + "m "+ str(pt) + "pt. " + str(dist) +"m("+str(az)+"deg)." 
            elif state == 1 or state == 2:
                (code,dist,az,pt,alt,name,desc) = result[0]
                mesg = "Approaching " + code + ", " + str(dist) +"m("+str(az)+"deg) to go."
                mesg2 = mesg
            elif state == 5:
                (code,dist,az,pt,alt,name,desc) = result[0]
                mesg = "Departing " + code + ", " + str(dist) +"m("+str(az)+"deg) from summit."
                mesg2 = mesg
            elif state == 0 or state == 6:
                mesg = nowstr + " "
                for (code,dist,az,_,_,_,_) in result:
                    mesg = mesg + code.split('/')[1] + ":"+ str(dist) + "m("+str(az)+") "
                (code,dist,az,pt,alt,name,desc) = result[0]
                mesg2 = mesg
        else:
            mesg = nowstr + " No Summits within 30km square from {0:.6f},{1:.6f}.".format(lat,lng)
            mesg2 = mesg
            state = -1
            dist = 0
            az = 0
            
        q = 'update beacons set lastseen = ?, lat = ?, lng = ?, lat_dest = ?, lng_dest = ?,dist = ?, az = ?,state = ?,summit = ?,message = ?,message2 =?, type = ? where operator = ?'
        try:
            cur_beacon.execute(q,(now,lat,lng,lat_dest,lng_dest,dist,az,state,code,mesg,mesg2,'APRS',op,))
            conn_beacon.commit()
        except Exception as err:
            print >> sys.stderr, 'update beacon.db %s' % err
            pass
        
        q = 'insert into aprslog (time,operator,lat,lng,lat_dest,lng_dest,dist,az,state,summit) values(?,?,?,?,?,?,?,?,?,?)'
        try:
            cur_aprslog.execute(q,(now,op,lat,lng,lat_dest,lng_dest,dist,az,state,code))
            conn_aprslog.commit()
        except Exception as err:
            print >> sys.stderr, 'update aprslog.db %s' % err
            pass

        conn_beacon.close()
        conn_aprslog.close()
        conn_summit.close()
        conn_dxsummit.close()
        return (foreign, state, tlon, mesg)
    
    conn_beacon.close()
    conn_aprslog.close()
    conn_summit.close()
    conn_dxsummit.close()
    return (True,-1, 0, "Oops!")

def parse_summit(code):
    conn_dxsummit = sqlite3.connect(dxsummit_db)
    cur_dxsummit = conn_dxsummit.cursor()

    lat,lng = 0.0,0.0
    name,alt,pts = '',0,0

    q = "select * from summits where code = ?"
    cur_dxsummit.execute(q,(code,))
    rows = cur_dxsummit.fetchall()
    if rows:
        for (code,lat,lng,pts,alt,name,_) in rows:
            res = (lat,lng)
    else:
        url = "https://www.sota.org.uk/Summit/" + code
        try:
            response = requests.get(url)
        except Exception, e:
            print >> sys.stderr, 'HTTP GET %s' % e
            return (lat,lng)
        else:    
            for line in response.text.splitlines():
                if code in line:
                    m = re.search(',\s*(.+)-\s*(\d+)m,\s*(\d+).*',line)
                    if m:
                        name = m.group(1)
                        alt = int(m.group(2))
                        pts = int(m.group(3))
                elif "data-content=" in line:
                    m = re.search('Lat:\s*(-*\d+\.\d+),\s*Long:\s*(-*\d+\.\d+)',line)
                    if m:
                        lat = float(m.group(1))
                        lng = float(m.group(2))
            q = 'insert into summits (code, lat ,lng, point, alt, name, desc) values(?,?,?,?,?,?,?)'
            cur_dxsummit.execute(q,(code,lat,lng,pts,alt,name,""))
            conn_dxsummit.commit()
            res = (lat,lng)
    conn_dxsummit.close()
    return res
    
def parse_alerts(url):
    try:
        response = requests.get(url)
    except Exception, e:
        print >>sys.stderr, 'HTTP GET %s' % e
        return []
    
    result = []
    state = 'new'
    parse_error = False
    for line in response.text.splitlines():
        if state == 'new' and "class=\"alertDate\">" in line:
            m = re.search('class=\"alertDate\">(.+)</span>',line)
            if m:
                ald = m.group(1)
            else:
                parse_error = True
        elif state == 'new' and "<strong>Summit:</strong>" in line:
            m = re.search('Summit:</strong>(.+)\'',line)
            if m:
                alert_sinfo = m.group(1).strip()
            else:
                parse_error = True
        elif state == 'new' and "\"70px\">&nbsp" in line:
            m = re.search('&nbsp;([\d:]+)</td>$',line)
            if m:
                alert_time = int(parse(ald + " " +m.group(1)).strftime("%s"))
            else:
                parse_error = True
                alert_time = 0
            alert_start = alert_time + 3600 * KEYS['WINDOW_FROM']
            alert_end= alert_time  + 3600 * KEYS['WINDOW_TO']
            state = 'operator'
        elif state == 'operator' and "<strong>" in line:
            m = re.search('<strong>(.+)</strong>',line)
            if m:
                alert_callsign = m.group(1)
            else:
                alert_callsign = ""
                parse_error = True
            m = re.match('(\w+)/(\w+)',alert_callsign)
            if m:
                if len(m.group(1)) > len(m.group(2)):
                    alert_operator = m.group(1)
                else:
                    alert_operator = m.group(2)
            else:
                alert_operator = alert_callsign
            state = 'summit'
        elif state == 'summit' and "<strong>" in line:
            m = re.search('<strong>(.+)</strong>',line)
            if m:
                alert_summit = m.group(1)
            else:
                parse_error = True
            state = 'freq'
        elif state == 'freq' and "<strong>" in line:
            m = re.search('<strong>(.+)</strong>',line)
            if m:
                alert_freq = m.group(1)
            else:
                parse_error = True
            state = 'comment'
        elif state == 'comment' and "class=\"comment\">" in line:
            m = re.search('class=\"comment\">(.*)</span>',line)
            if m:
                alert_comment = m.group(1)
            else:
                parse_error = True
            state = 'poster'
        elif state == 'poster' and "class=\"poster\">" in line:
            m = re.search('class=\"poster\">(.*)</span>',line)
            if m:
                alert_poster = m.group(1)
            else:
                parse_error = True
            if not parse_error:
                patplus = re.compile('S\+(\d+)',re.IGNORECASE)
                patminus = re.compile('S-(\d+)',re.IGNORECASE)
                for p in  patplus.findall(alert_comment):
                    alert_end = alert_time + int(p)*3600
                for p in patminus.findall(alert_comment):
                    alert_start = alert_time - int(p)*3600
                result.append({'time':alert_time,
                               'start':alert_start,
                               'end':alert_end,
                               'operator':alert_operator,
                               'callsign':alert_callsign,
                               'summit':alert_summit,
                               'summit_info':alert_sinfo,
                               'freq':alert_freq,
                               'comment':alert_comment,
                               'poster':alert_poster})
            parse_error = False    
            state = 'new'
    return result

def parse_json_alerts(url):
    try:
        param = urllib.urlencode(
        {
        'client': 'sotawatch',
        'user': 'anon'
        })
        readObj= urllib.urlopen(url+'/api/alerts?'+param)
        res = readObj.read()
    except Exception, e:
        print >>sys.stderr, 'JSON GET ALERTS %s' % e
        return []

    result = []
    
    for item in json.loads(res):
        if item['comments'] is None:
            item['comments'] = ""
        alert_time = int(datetime.strptime(item['dateActivated'],'%Y-%m-%dT%H:%M:%S').strftime("%s"))
        alert_start = alert_time + 3600 * KEYS['WINDOW_FROM']
        alert_end= alert_time  + 3600 * KEYS['WINDOW_TO']
        patplus = re.compile('S\+(\d+)',re.IGNORECASE)
        patminus = re.compile('S-(\d+)',re.IGNORECASE)
        for p in  patplus.findall(item['comments']):
            alert_end = alert_time + int(p)*3600
        for p in patminus.findall(item['comments']):
            alert_start = alert_time - int(p)*3600
            
        result.append({'time':alert_time,
                       'start':alert_start,
                       'end': alert_end,
                       'poster': item['posterCallsign'],
                       'callsign': item['activatingCallsign'],
                       'summit': item['associationCode']+"/"+item['summitCode'],
                       'summit_info': item['summitDetails'],
                       'freq': item['frequency'],
                       'comment': item['comments'],
                       'poster': "(Posted by " + item['posterCallsign'] + ")"})
        
    return result

def update_json_data():
    conn_aprslog = sqlite3.connect(aprslog_db)
    cur_aprslog = conn_aprslog.cursor()
    conn = sqlite3.connect(alert_db)
    cur = conn.cursor()
    q = 'select O.callsign,O.summit,A.operator,A.time,A.summit_info,A.lat_dest,A.lng_dest,A.alert_freq,A.alert_comment,B.lat,B.lng,B.dist,S.time,S.callsign,S.summit,S.summit_info,S.lat,S.lng,S.spot_freq,S.spot_mode,S.spot_comment,S.spot_color,S.poster from oprts as O  left outer join alerts as A on (O.callsign=A.callsign and O.summit=A.summit) left outer join spots as S on (O.callsign=S.callsign and O.summit = S.summit) left outer join beacons AS B on (O.operator=B.operator and O.summit = B.summit)'
#    cur.execute(q,(alert_start,alert_end));
    cur.execute(q);
    rows = cur.fetchall()
    j = []

    now = int(datetime.utcnow().strftime("%s"))
    alert_start = now + 3600 * -2
    alert_end= now  + 3600 * KEYS['WINDOW_TO']

    for (call,summit,aop,atime,ainfo,alatdest,alngdest,afreq,acomment,blat,blng,bdist,stime,scall,ssummit,sinfo,slat,slng,sfreq,smode,scomment,scolor,sposter) in rows:
        if atime:
            at = datetime.fromtimestamp(int(atime)).strftime("%m/%d %H:%M")
        else:
            at =""
            afreq = ""
            acomment = ""
            
        if stime:
            st = datetime.fromtimestamp(int(stime)).strftime("%H:%M")
            ainfo = sinfo
        else:
            st = ""
            sfreq = ""
            smode = ""
            scolor= ""
            scomment = ""
            
        if not alatdest:
            alatdest = slat
            alngdest = slng
            
        if atime:
            time = atime
            if stime:
                time = stime
        else:
            time = stime
        q = 'select time,lat,lng,dist from aprslog where operator = ? and time > ? and time < ?'
        cur_aprslog.execute(q,(aop,alert_start,alert_end))
        route = []
        for (t,lat,lng,dist) in cur_aprslog.fetchall():
            tm = datetime.fromtimestamp(int(time)).strftime("%H:%M")
            route.append({'time':tm,'latlng':[float(lat),float(lng)],'dist':dist})

        e = (time,{'op':call,'summit':summit,'summit_info':ainfo,
             'summit_latlng':[float(alatdest),float(alngdest)],
             'alert_time':at,
             'alert_freq':afreq,
             'alert_comment':acomment,
             'spot_time':st,
             'spot_freq':sfreq + ' ' +smode,
             'spot_comment':scomment,
             'spot_color':scolor,
             'aprs_message':"",
             'route':route
        })
        j.append(e)

    js = sorted(j,key=lambda x: x[0])

    dxl = []
    jal = []
    for (t,d) in js:
        if t > alert_start and t < alert_end :
            if re.search(KEYS['JASummits'],d['summit']):
                jal.append(d)
            else: 
                dxl.append(d)
                
    with open(output_json_file,"w") as f:
        json.dump(dxl,f)
        
    with open(output_json_jafile,"w") as f:
        json.dump(jal,f)

    conn.close()
    conn_aprslog.close()
    
def update_spots():
    try:
        param = urllib.urlencode(
        {
        'client': 'sotawatch',
        'user': 'anon'
        })
        readObj= urllib.urlopen(sotawatch_json_url+'/api/spots/20?'+param)
        res = readObj.read()
    except Exception, e:
        print >>sys.stderr, 'JSON GET SPOTS %s' % e
        return []

    conn2 = sqlite3.connect(alert_db)
    cur2 = conn2.cursor()
    r = json.loads(res);
    r.reverse()
    for item in r:
        if item['comments'] is None:
            item['comments'] = ""
        ts = item['timeStamp']
        ts = ts[:ts.find('.')]
        spot_time = int(datetime.strptime(ts,'%Y-%m-%dT%H:%M:%S').strftime("%s"))
        spot_end= spot_time  + 3600 * KEYS['WINDOW_TO']
        m = re.match('(\w+)/(\w+)/(\w+)',item['activatorCallsign'])
        if m:
            op = m.group(1)
        else:
            m = re.match('(\w+)/(\w+)',item['activatorCallsign'])
            if m:
                op = m.group(1)
            else:
                op = item['activatorCallsign']
        summit = item['associationCode']+"/"+item['summitCode']
        (lat,lng) = parse_summit(summit)
        q ='insert or replace into spots (time,end,operator,callsign,summit,summit_info,lat,lng,spot_freq,spot_mode,spot_comment,spot_color,poster) values (?,?,?,?,?,?,?,?,?,?,?,?,?)'
        cur2.execute(q,(spot_time,spot_end,op.upper(),item['activatorCallsign'],summit,item['summitDetails'],lat,lng,item['frequency'],item['mode'],item['comments'],item['highlightColor'],item['callsign']))
    conn2.commit()
    conn2.close()
    update_json_data()
    
def update_alerts():
    global aprs_filter
    conn = sqlite3.connect(alert_db)
    cur = conn.cursor()
    cur2 = conn.cursor()

    now = int(datetime.utcnow().strftime("%s"))
    
    q = 'create table if not exists alerts (time int,start int,end int,operator text,callsign text,summit text,summit_info text,lat_dest text,lng_dest text,alert_freq text,alert_comment text,poster text,primary key(time,callsign,summit))'
    cur.execute(q)
    q = 'delete from alerts where end < ?'
    cur.execute(q,(now,))
    conn.commit()

    q ='create table if not exists beacons (start int,end int,operator text,lastseen int,lat text,lng text,lat_dest text,lng_dest text,dist int,az int,state int,summit text,message text,message2 text,tlon int,lasttweet text,type text,primary key(start,operator,summit))'
    cur2.execute(q)
    q = 'delete from beacons where end < ?'
    cur2.execute(q,(now,))

    q ='create table if not exists spots (time int,end int,operator text,callsign text,summit text,summit_info text,lat text,lng text,spot_freq text,spot_mode text,spot_comment text,spot_color text,poster text,primary key(operator))'  
    cur2.execute(q)
    q = 'delete from spots where end < ?'
    cur2.execute(q,(now,))

    q = 'create view if not exists oprts as select distinct operator,callsign, summit from alerts union select operator,callsign,summit from spots;'
    cur2.execute(q)
    conn.commit()

    res = parse_json_alerts(sotawatch_json_url)

    operators = []

    for user in KEYS['TEST_USER']:
        d = {'time':now,'start':now-100,'end':now+10800,
             'operator':user,'callsign':user,'summit':'JA/KN-006',
             'summit_info':'Test Summit','freq':'433-fm',
             'comment':'Alert Test','poster':'(Posted By JL1NIE)'}
        res.append(d)
    
    for d in res:
        (lat_dest,lng_dest) = parse_summit(d['summit'])

        m = re.match('(\w+)/(\w+)/(\w+)',d['callsign'])
        if m:
            op = m.group(1)
        else:
            m = re.match('(\w+)/(\w+)',d['callsign'])
            if m:
                op = m.group(1)
            else:
                op = d['callsign']

        q = 'insert or replace into alerts(time,start,end,operator,callsign,summit,summit_info,lat_dest,lng_dest,alert_freq,alert_comment,poster) values (?,?,?,?,?,?,?,?,?,?,?,?)'
        cur.execute(q,(d['time'],d['start'],d['end'],
                       op,d['callsign'],
                       d['summit'],d['summit_info'],
                       str(lat_dest),str(lng_dest),
                       d['freq'],
                       d['comment'],d['poster']))
#        if re.match(KEYS['Watchfor'],d['summit']) and now >= d['start'] and now <= d['end']:
        if now >= d['start'] and now <= d['end']:
            if not op in operators:
                operators.append(op)
                q = 'insert or replace into beacons (start,end,operator,lastseen,lat,lng,lat_dest,lng_dest,dist,az,state,summit,message,message2,tlon,lasttweet,type) values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'
                cur2.execute(q,(d['start'],d['end'],op,
                                0, #lastseen
                                '', # lat
                                '', # lng
                                str(lat_dest), # lat_dest
                                str(lng_dest), # lng_dest
                                -1,0,-2,
                                d['summit'],
                                d['summit_info'],
                                d['summit_info'],
                                0,'',
                                'SW2'))
    conn.commit()
    conn.close()

    aprs_filter =  "b/"+ "-*/".join(operators) +"-*"
    if aprs_beacon:
        aprs_beacon.set_filter(aprs_filter)
        
def tweet_alerts():
    today = datetime.now(localtz).strftime("%d %B %Y")
    conn = sqlite3.connect(alert_db)
    cur = conn.cursor()
    start = int(datetime.utcnow().strftime("%s")) + 3600 * KEYS['ALERT_FROM']
    end = int(datetime.utcnow().strftime("%s")) + 3600 * KEYS['ALERT_TO']
    q = 'select * from alerts where time >= ? and time <= ? and summit like ?'
    cur.execute(q,(start,end,'JA%',))
    rows = cur.fetchall()

    num = len(rows) - len(KEYS['TEST_USER'])
    mesg = "SOTAwatch alerts:\n"
    if num == 0:
        mesg = mesg + "No activations are currently scheduled on "
    elif num == 1:
        mesg = mesg + "An activation is currently scheduled on "
    else:
        mesg = str(num)+" activations are currently scheduled on "
    mesg = mesg + today + " (Posted by SLIPPER1.1)."
    tweet(tweet_api,mesg)
    
    for (tm,_,_,_,call,summit,info,lat,lng,freq,comment,poster) in rows:
        tm = datetime.fromtimestamp(int(tm)).strftime("%H:%M")
        mesg = tm + " " + call + " on\n" + summit + " " + freq + "\n" + info + "\n" + comment + " " + poster
        if summit != 'JA/TT-TEST':
            tweet(tweet_api,mesg)
    conn.close()

def get_new_msgno():
    global _thlock
    global _ackpool
    global _senderpool
    global _count

    _thlock.acquire()
    _count = _count + 1
    if _count == 1000:
        _count = 1
    _senderpool.add(_count)
    _thlock.release()
    return _count

def ack_received(mlist):
    global _thlock
    global _ackpool
    global _senderpool
    global _count

    if debug:
        print _senderpool
        print _ackpool

    for msgno in mlist:
        if msgno in _ackpool:
            _thlock.acquire()
            _ackpool.discard(msgno)
            _thlock.release()
            return True
    return False

def push_msgno(msgno):
    global _thlock
    global _ackpool
    global _senderpool
    global _count

    if msgno in _senderpool:
        _thlock.acquire()
        _ackpool.add(msgno)
        _thlock.release()
        return True
    return False

def discard_ack(mlist):
    global _thlock
    global _ackpool
    global _senderpool
    global _count
    
    _thlock.acquire()    
    for msgno in mlist:
        _ackpool.discard(msgno)
        _senderpool.discard(msgno)
    _thlock.release()
    
def aprs_worker():
    global aprs_beacon
    global _thlock
    global _ackpool
    global _senderpool
    global _count
    
    _thlock = Lock()
    _ackpool = {-1}
    _senderpool = {-1}
    _count = 0
    aprs_beacon = aprslib.IS(aprs_user, host=aprs_host,
                             passwd=aprs_password, port=aprs_port)
    aprs_beacon.connect(blocking=True)
    aprs_beacon.consumer(callback, immortal=True, raw=True)

def send_ack_worker(aprs, msgno):
    sleep(2)
    for i in range(3):
        if debug:
            print "SendingAck("+ str(i) + "):" + msgno
        else:
            aprs.sendall(msgno)
            sleep(30)
    
def send_ack(aprs, callfrom, msgno):
    ack = aprs_user+">APRS,TCPIP*::"+callfrom+":ack"+str(msgno)
    th = Thread(name="AckWoker",target=send_ack_worker,args =(aprs,ack))
    th.start()
    
def send_message(aprs, callfrom, message):
    header = aprs_user+">APRS,TCPIP*::"+callfrom+":"
    if len(message)>67:
        message = message[0:67]
    if debug:
        print "Sending: "+ header + message
    else:
        aprs.sendall(header+message)

def send_message_worker(aprs, callfrom, message):
    mlist = []
    for i in range(4):
        msgno = get_new_msgno()
        mlist.append(msgno)
        m = message + '{' + str(msgno)
        if debug:
            print "Sending("+ str(i) + "):" + m
        else:
            aprs.sendall(m)
        sleep(30)
        if ack_received(mlist):
            break
    discard_ack(mlist)
        
def send_message_with_ack(aprs, callfrom, message):
    header = aprs_user+">APRS,TCPIP*::"+callfrom+":"
    if len(message)>67:
        message = message[0:67]
    if debug:
        print "Sending:" + header + message
    else:
        th = Thread(name="MessageWorker",target=send_message_worker,args=(aprs, callfrom, header+message))
        th.start()

def send_long_message_with_ack(aprs, callfrom, message):
    for m in message.splitlines():
        send_message_with_ack(aprs, callfrom, m)

def send_summit_message(callfrom, lat ,lng):
    foreign,state,tlon,mesg = lookup_summit(callfrom,lat,lng)
    if not foreign:
        if state == 3: # On Summit
            if tlon == 1:
                tweet(tweet_api,callfrom + " " + mesg.split('\n')[0])
            mesg = mesg + "\n" + readlast3(last3)
            send_long_message_with_ack(aprs_beacon,callfrom,mesg)
        elif state == 1:# Approaching Summit
            if tlon == 1:
                tweet(tweet_api,callfrom + " " + mesg)
            send_long_message_with_ack(aprs_beacon,callfrom,mesg)
    del mesg

def on_service(op):
    op = op[0:op.rfind('-')].strip()
    conn_beacon = sqlite3.connect(alert_db)
    cur_beacon = conn_beacon.cursor()
    q = 'select * from beacons where operator = ?'
    cur_beacon.execute(q,(op,))
    result = False
    for (_,_,_,_,_,_,lat_dest,lng_dest,_,_,state,code,mesg,mesg2,tlon,lasttweet,mode) in cur_beacon.fetchall():
        result = True
    conn_beacon.close()
    return result

def set_tweet_location(op,tlon):
    op = op[0:op.rfind('-')].strip()
    conn_beacon = sqlite3.connect(alert_db)
    cur_beacon = conn_beacon.cursor()
    q = 'update beacons set tlon = ? where operator = ?'
    try:
        cur_beacon.execute(q,(tlon,op,))
        conn_beacon.commit()
    except Exception as err:
        print >> sys.stderr, 'update beacon.db %s' % e
    conn_beacon.close()

def check_dupe_mesg(op,tw):
    op = op[0:op.rfind('-')].strip()
    conn_beacon = sqlite3.connect(alert_db)
    cur_beacon = conn_beacon.cursor()
    q = 'select * from beacons where operator = ?'
    cur_beacon.execute(q,(op,))
    result = False
    for (_,_,_,_,_,_,lat_dest,lng_dest,_,_,state,code,mesg,mesg2,tlon,lasttweet,mode) in cur_beacon.fetchall():
        if lasttweet == tw:
         result = True
    if not result:
        q = 'update beacons set lasttweet = ? where operator = ?'
        try:
            cur_beacon.execute(q,(tw,op,))
            conn_beacon.commit()
        except Exception as err:
            print >> sys.stderr, 'update beacon.db %s' % e
            
    conn_beacon.close()
    return result

def check_status():
    conn_beacon = sqlite3.connect(alert_db)
    cur_beacon = conn_beacon.cursor()
    now = int(datetime.utcnow().strftime("%s")) - 3600 * 2
    q = 'select * from beacons where state >=0 and state <=5 and lastseen > ?'
    cur_beacon.execute(q,(now,))
    received = []
    near_summit = []
    on_summit =[]

    for (_,_,op,last,_,_,_,_,_,_,state,_,_,_,_,_,_) in cur_beacon.fetchall():
        if state == 0:
            received.append(op)
        elif state == 1 or state == 2 or state == 5:
            near_summit.append(op)
        elif state == 3 or state == 4:
            tm = datetime.fromtimestamp(last).strftime("%H:%M")
            on_summit.append(op+"("+tm+")")
    conn_beacon.close()
    if on_summit:
        result = "On:"+','.join(on_summit)
    else:
        result = "On:None"
    if near_summit:
        result = result + " Near:"+','.join(near_summit)
    else:
        result = result + " Near:None"
    if received:
        result = result + " Recv:"+','.join(received)
    else:
        result = result + " Recv:None"
    return result
    
def do_command(callfrom,mesg):
    for com in mesg.split(","):
        com.strip()
        if com in 'HELP' or com in 'help' or com in '?':
            res = 'DX,JA,ST,LOC,LTON,LTOFF,M=<message>,HELP,?'
            send_long_message_with_ack(aprs_beacon,callfrom,res)
            break
        if com in 'DX' or com in 'dx':
            res = readlast3(last3dx)
            send_long_message_with_ack(aprs_beacon,callfrom,res)
        elif com in 'JA' or com in 'ja':
            res = readlast3(last3)
            send_long_message_with_ack(aprs_beacon,callfrom,res)
        elif com in 'ST' or com in 'st':
            res = check_status()
            send_long_message_with_ack(aprs_beacon,callfrom,res)
        elif com in 'LOC' or com in 'loc':
            res = lookup_from_op(callfrom)
            send_long_message_with_ack(aprs_beacon,callfrom,res)
        elif com in 'LTON' or com in 'lton':
            if not on_service(callfrom):
                send_long_message_with_ack(aprs_beacon,callfrom,'Out of service: '+com)
                break
            set_tweet_location(callfrom,1)
            send_long_message_with_ack(aprs_beacon,callfrom,'Set location tweet ON')
        elif com in 'LTOFF' or com in 'ltoff':
            if not on_service(callfrom):
                send_long_message_with_ack(aprs_beacon,callfrom,'Out of service: '+com)
                break
            set_tweet_location(callfrom,0)
            send_long_message_with_ack(aprs_beacon,callfrom,'Set location tweet OFF')
        else:
            m = re.search('M=(.+)',mesg,re.IGNORECASE)
            if m:
                if not on_service(callfrom):
                    send_long_message_with_ack(aprs_beacon,callfrom,'Out of service: '+com)
                    break
                tm = m.group(1)
                tm.strip()
                if check_dupe_mesg(callfrom,tm):
                    send_long_message_with_ack(aprs_beacon,callfrom,'Dupe: '+tm)
                else:
                    tweet(tweet_api,callfrom + " " + tm)
                    send_long_message_with_ack(aprs_beacon,callfrom,'Posted: '+tm)
            else:
                res = 'Command Error,DX,JA,ST,LOC,LTON,LTOFF,M=<message>,HELP,?'
                send_long_message_with_ack(aprs_beacon,callfrom,'Unknown command: '+mesg)
                break
    del mesg
        
def callback(packet):
    msg = aprslib.parse(packet)
    callfrom = msg['from'] + "      "
    callfrom = callfrom[0:9]

    if debug:
        print "Receive:"+callfrom+ ":"+msg['format']+"-"+msg['raw']
    if msg['format'] in  ['uncompressed','compressed','mic-e']:
        lat = msg['latitude']
        lng = msg['longitude']
        send_summit_message(callfrom, lat, lng)
    elif msg['format'] in ['message']:
        callto = msg['addresse'].strip()
        if callto != KEYS['APRS_USER']:
            del msg
            return
        m = re.search('ack(\d+)',msg['raw'])
        if m:
            push_msgno(int(m.group(1)))
        else:
            m = re.search('{(\d+)',msg['raw'])
            if m:
                send_ack(aprs_beacon,callfrom,int(m.group(1)))

            if 'message_text' in msg:
                do_command(callfrom,msg['message_text'])
    del msg

def setup_db():
    conn_dxsummit = sqlite3.connect(dxsummit_db)
    cur_dxsummit = conn_dxsummit.cursor()
    conn_aprslog = sqlite3.connect(aprslog_db)
    cur_aprslog = conn_aprslog.cursor()
    
    q ='create table if not exists summits (code txt,lat real,lng real,point integer,alt integer,name text,desc text)'
    cur_dxsummit.execute(q)
    q = 'create index if not exists summit_index on summits(lat,lng)'
    cur_dxsummit.execute(q)
    conn_dxsummit.commit()
    conn_dxsummit.close()

    q ='create table if not exists aprslog (time int,operator text,lat text,lng text,lat_dest text,lng_dest text,dist int,az int,state int,summit text)'
    cur_aprslog.execute(q)
    conn_aprslog.commit()
    conn_aprslog.close()
    
    update_alerts()
    update_spots()
    
def main():
    global tweet_api

    aprs = Thread(target=aprs_worker, args=())
    aprs.start()

    setup_db()
        
    try:
        auth = tweepy.OAuthHandler(KEYS['ConsumerkeySOTAwatch'], KEYS['ConsumersecretSOTAwatch'])
        auth.set_access_token(KEYS['AccesstokenSOTAwatch'], KEYS['AccesstokensecretSOTAwatch'])
        tweet_api = tweepy.API(auth)
    except Exception, e:
        print >>sys.stderr, 'access error: %s' % e
        sys.exit(1)

    schedule.every(update_alerts_every).minutes.do(update_alerts)
    schedule.every(update_spots_every).minutes.do(update_spots)
    schedule.every().day.at(tweet_at).do(tweet_alerts)

    while True:
        schedule.run_pending()
        gc.collect()
        #objgraph.show_growth()
        sleep(30)
        
if __name__ == '__main__':
    main()
