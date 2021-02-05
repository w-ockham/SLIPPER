#!/usr/bin/env python
# coding: utf-8
import aprslib
import bz2
from datetime import datetime, timedelta
from dateutil.parser import parse
import gc
import shelve
import logging
import objgraph
import pickle
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

import sys, codecs
sys.stderr = codecs.getwriter("utf-8")(sys.stderr)
sys.stdout = codecs.getwriter("utf-8")(sys.stdout)

debug = False
#debug = True

sotawatch_url = KEYS['SOTA_URL']
sotalive_url = KEYS['SOTALIVE_URL']
sotawatch_json_url = KEYS['SOTAWATCH_JSON_URL']
output_json_file = KEYS['OUTPUT_JSON_FILE']
output_json_jafile = KEYS['OUTPUT_JSON_JAFILE']
summit_db = KEYS['SUMMIT_DB']
dxsummit_db = KEYS['DXSUMMIT_DB']
association_db = KEYS['ASSOC_DB']
alert_db = KEYS['ALERT_DB']
aprslog_db = KEYS['APRSLOG_DB']
user_db = KEYS['USER_DB']
params_db  = KEYS['PARAMS_DB']
aprs_user = KEYS['APRS_USER']
aprs_password = KEYS['APRS_PASSWD']
aprs_host = KEYS['APRS_HOST']
aprs_port = KEYS['APRS_PORT']
tweet_at = KEYS['TWEET_AT']
update_alerts_every = KEYS['UPDATE_ALERTS_EVERY']
update_spots_every = KEYS['UPDATE_SPOTS_EVERY']
latestSpot = {}
tweet_api = None
tweet_api_debug = None
target_ssids = ['7','9','5','6','8']
aprs_filter = ""
aprs_beacon = None

localtz = pytz.timezone('Asia/Tokyo')
grs80 = pyproj.Geod(ellps='GRS80')
# 3000m x 3000m
deltalat, deltalng = 0.002704*10, 0.003311*10

# Activator's state
STATES = (
    NOTRCVD,
    RCVD,
    NEAR,
    APRCH,
    APRCH_SENT,
    ONSUMMIT,
    ONSUMMIT_SENT,
    DESC
    ) = range(-1,7)

ERRLEVEL = (
    E_NONE,
    E_INFO,
    E_WARN,
    E_FATAL
    ) = range(0,4)

_sys_stat = {
    }

def sys_clearstat():
    global _sys_stat
    _sys_stat['ALERTS'] = 0
    _sys_stat['SPOTS'] = 0
    _sys_stat['TRACKS'] = 0
    _sys_stat['PACKETS'] = 0
    _sys_stat['TWEET'] = 0
    
def sys_updatestat(facility, val):
    _sys_stat[facility] = val
    with open("/var/tmp/sotalive-stat.json","w") as f:
        json.dump(_sys_stat,f)

def sys_updatestatall(alerts,spots,aprs,packets):
    _sys_stat['ALERTS'] = alerts
    _sys_stat['SPOTS'] = spots
    _sys_stat['TRACKS'] = aprs
    _sys_stat['PACKETS'] = packets
    with open("/var/tmp/sotalive-stat.json","w") as f:
        json.dump(_sys_stat,f)
    
def tweet(api, txt):
    if debug:
        print(txt)
    else:
        if len(txt) > 255:
            txt = txt[0:255]
        try:
            api.update_status(status=txt)
        except tweepy.TweepError as e:
            print >>sys.stderr, 'tweet error: %s ' % e
            print >>sys.stderr, 'txt = %s ' % txt
            if e.message[0]['code'] != 187:
                sys_updatestat('TWEET',E_FATAL)
            else:
                sys_updatestat('TWEET',E_INFO)
            return

def tweet_with_media(api, fname, txt):
    if debug:
        print(txt)
    else:
        if len(txt) > 110:
            txt = txt[0:110]
        try:
            api.update_with_media(fname, status=txt)
        except tweepy.TweepError as e:
            print >>sys.stderr, 'tweet error %s ' % e
            print >>sys.stderr, 'txt = %s ' % txt
            if e.message[0]['code'] != 187:
                sys_updatestat('TWEET',E_FATAL)
            else:
                sys_updatestat('TWEET',E_INFO)
	    return

def parse_callsign(call):
    call = call.upper().replace(" ","")
    r = call.rfind('-')
    if r > 0:
        op = call[0:r]
        ssidtype = call[r+1:] 
    else:
        op = call
        ssidtype = '7'
        
    return (op,ssidtype,call)

def lookup_from_op(call):
    conn_alert = sqlite3.connect(alert_db)
    cur_alert = conn_alert.cursor()
    cur_beacon = conn_alert.cursor()

    (op,_,_) = parse_callsign(call)
    
    q = 'select * from beacons where operator = ?'
    cur_beacon.execute(q, (op, ))
    r = cur_beacon.fetchall()
    if r:
        for (start, end, op, _, _, _, _, _ , _, _, state,
             name, m, m2, tlon, lasttweet, mode) in r:
            if state == -1:
                tm = datetime.fromtimestamp(int(start)).strftime("%H:%M")
                mesg = "No beacons received. Upcoming Activation: " + tm + " " + name
                break
            else:
                mesg = m2
    else:
        q = 'select * from alerts where operator = ?'
        cur_alert.execute(q, (op, ))
        r = cur_alert.fetchall()
        if r:
            mesg = "Out of notification time window. Upcoming Activation: "
            for (time, _, _, _, _, summit, _, _, _, _, _, _) in r:
                tm = datetime.fromtimestamp(int(time)).strftime("%m/%d %H:%M")
                mesg = mesg + tm + " " + summit + " "
                break
        else:
            mesg = "No Upcoming Activation."

    conn_alert.close()
    return mesg


def search_summit(code_dest,lat,lng):
    conn_summit = sqlite3.connect(summit_db)
    cur_summit = conn_summit.cursor()
    conn_dxsummit = sqlite3.connect(dxsummit_db)
    cur_dxsummit = conn_dxsummit.cursor()
    
    mag = KEYS['MAGNIFY']
    latu,latl = lat + deltalat*mag, lat - deltalat*mag
    lngu,lngl = lng + deltalng*mag, lng - deltalng*mag

    result = []
    target = None
    
    if re.search(KEYS['JASummits'],code_dest):
        foreign = False
        continent = 'JA'
        for s in cur_summit.execute('''select * from summits where (? > lat) and (? < lat) and (? > lng) and (? < lng)''',(latu,latl,lngu,lngl,)):
            (code,lat1,lng1,pt,alt,name,desc,_,_)= s
            try:
                az,bkw_az,dist = grs80.inv(lng,lat,lng1,lat1)
            except Exception as e:
                az,bkw_az,dist = (0, 0, 99999)
            o = (code,int(dist),int(az),pt,alt,name,desc)
            result.append(o)
            if code == code_dest:
                target = o 
    else:
        foreign = True
        continent = 'WW'
        for s in cur_dxsummit.execute("select * from summits where (? > lat) and (? < lat) and (? > lng) and (? < lng)",(latu,latl,lngu,lngl,)):
            (code,lat1,lng1,pt,alt,name,desc)= s
            try:
                az,bkw_az,dist = grs80.inv(lng,lat,lng1,lat1)
            except Exception as e:
                az,bkw_az,dist = (0, 0, 99999)
            o = (code,int(dist),int(az),pt,alt,name,desc)
            result.append(o)
            if code == code_dest:
                target = o

    if not target:
        if re.search(KEYS['JASummits'],code_dest):
            for s in cur_summit.execute("select * from summits where code = ?",(code_dest,)):
                (code,lat1,lng1,pt,alt,name,desc,_,_)= s
                try:
                    az,bkw_az,dist = grs80.inv(lng,lat,lng1,lat1)
                except Exception as e:
                    az,bkw_az,dist = (0, 0, 99999)
                target = (code,int(dist),int(az),pt,alt,name,desc)
        else:
            for s in cur_dxsummit.execute("select * from summits where code = ?",(code_dest,)):
                (code,lat1,lng1,pt,alt,name,desc)= s
                try:
                    az,bkw_az,dist = grs80.inv(lng,lat,lng1,lat1)
                except Exception as e:
                    az,bkw_az,dist = (0, 0, 99999)
                target = (code,int(dist),int(az),pt,alt,name,desc)

    if not target:
        target = (code,999999,0,0,0,"Summit not recognized","")
    
    result.sort(key=lambda x:x[1])
    if result:
        if foreign:
            conn_assoc = sqlite3.connect(association_db)
            cur_assoc = conn_assoc.cursor()
            (code,_,_,_,_,_,_) = result[0]
            for (c,)  in cur_assoc.execute("select continent from associations where code = ?",(code,)):
                continent = c
                break
            conn_assoc.close()
            
    conn_summit.close()
    conn_dxsummit.close()
    
    return (foreign,continent,target,result[0:3])

def get_activator_status(cur,op,ssid,summit):
    q = 'select * from message_history where operator = ? and ssid =? and summit = ?'
    cur.execute(q,(op,ssid,summit,))
    r = cur.fetchone()
    if r:
        (_,_,_,_,state,_) = r
        return state
    else:
        return None
    
def set_activator_status(cur,now,op,ssid,summit,state,dist):    
    q = 'insert or replace into message_history(time,operator,ssid,summit,state,distance) values (? ,?, ?, ?, ?, ?)'
    cur.execute(q,(now,op,ssid,summit,state,dist,))
    return state

def lookup_summit(call,lat,lng):
    (op,ssidtype,_) = parse_callsign(call)
    
    if op in KEYS['EXCLUDE_USER']:
        return (True,'',-1, 0, "Oops!")

    conn_beacon = sqlite3.connect(alert_db)
    cur_beacon = conn_beacon.cursor()
    cur_message = conn_beacon.cursor()
    conn_aprslog = sqlite3.connect(aprslog_db)
    cur_aprslog = conn_aprslog.cursor()

    now = int(datetime.utcnow().strftime("%s"))
    q = 'select summit,operator,lat_dest,lng_dest,state from beacons where operator = ? and start < ? and end > ?'
    cur_beacon.execute(q,(op,now,now))
    nowstr = datetime.fromtimestamp(now).strftime("%H:%M")

    for (code_dest,_,lat_dest,lng_dest,state) in cur_beacon.fetchall():
        (foreign,continent,target,result) = search_summit(code_dest,lat,lng)

        if state < 0:
            state = RCVD
        else:
            state = state % 10

        prev_state = state
    
        if len(result) > 0:
            (code,dist,_,_,_,_,_) = result[0]

            prev_state = get_activator_status(cur_message,op,ssidtype,code)
                
            if dist <=100.0:
                if prev_state == ONSUMMIT:
                    state = ONSUMMIT_SENT
                elif prev_state == ONSUMMIT_SENT:
                    state = ONSUMMIT_SENT
                else:
                    state = ONSUMMIT
            elif dist <=300.0:
                if prev_state == APRCH or prev_state == APRCH_SENT:
                    state = APRCH_SENT
                elif prev_state == ONSUMMIT or prev_state == ONSUMMIT_SENT: 
                    state = ONSUMMIT_SENT
                else:
                    state = APRCH
            elif dist <= 600.0:
                if prev_state == ONSUMMIT or prev_state == ONSUMMIT_SENT:
                    state = DESC
                elif prev_state == APRCH or prev_state == APRCH_SENT: 
                    state = APRCH_SENT
                else:
                    state = NEAR
            else:
                if prev_state == ONSUMMIT or prev_state == ONSUMMIT_SENT or prev_state == APRCH or prev_state == APRCH_SENT:
                    state = DESC
                else:
                    state = RCVD

            set_activator_status(cur_message,now,op,ssidtype,code,state,dist)
            
            if state == ONSUMMIT or state == ONSUMMIT_SENT:
                (code,dist,az,pt,alt,name,desc) = result[0]
                if state == ONSUMMIT:
                    nowstr2 = datetime.fromtimestamp(now).strftime("%m/%d %H:%M")
                    update_user_params(op,[('LastActOn',code),('LastActAt',nowstr2)])
                if foreign:
                    mesg = "Welcome to " + code +". "+ name +","+ desc + " " + str(alt) + "m "+ str(pt) + "pt."
                else:
                    mesg = "Welcome to " + code +". "+ name +" " + str(alt) + "m "+ str(pt) + "pt.\n"+desc
                mesg2 = code + " - " + name + " " + str(alt) + "m " + str(pt) + "pt. " + str(dist) +"m("+str(az)+"deg)."

            elif state == APRCH or state == APRCH_SENT:
                (code,dist,az,pt,alt,name,desc) = result[0]
                mesg = "Approaching " + code + ", " + str(dist) +"m("+str(az)+"deg) to go."
                mesg2 = code + ":" + str(dist) +"m("+str(az)+"deg)." 

            elif state == DESC:
                (code,dist,az,pt,alt,name,desc) = result[0]
                mesg = "Descending " + code + ", " + str(dist) +"m("+str(az)+"deg) from summit."
                mesg2 = code + ":" + str(dist) +"m("+str(az)+"deg)." 

            elif state == RCVD or state == NEAR:
                mesg = nowstr + " "
                for (code,dist,az,_,_,_,_) in result:
                    mesg = mesg + code.split('/')[1] + ":"+ str(dist) + "m(" + str(az) + ") "
                (code,dist,az,pt,alt,name,desc) = result[0]
                mesg2 = nowstr + " "+ code + ":" + str(dist) + "m(" + str(az) + "deg)." 
        else:
            (code,dist,az,pt,alt,name,desc) = target
            mesg = nowstr + " "+ code + ":" + str(dist) +"m("+str(az)+"deg)."
            mesg2 = mesg
            state = 0
            az = 0

        if ssidtype in target_ssids:
            state = 10 * target_ssids.index(ssidtype) + state
        else:
            state = 10 * 0 + state

        q = 'update beacons set lastseen = ?, lat = ?, lng = ?,dist = ?, az = ?,state = ?,message = ?,message2 =?, type = ? where operator = ? and start < ? and end > ?'
        
        if (state % 10) != prev_state:
            errlog = op +'-'+ ssidtype + ':' + code + ':'+ continent + ':(' + str(prev_state) +'->'+ str(state) + '):' + str(dist) + 'm:' 
            print >> sys.stderr, 'UPDATE:' + errlog

        try:
            cur_beacon.execute(q,(now,lat,lng,dist,az,state,mesg,mesg2,'APRS',op,now,now))
            conn_beacon.commit()
        except Exception as err:
            print >> sys.stderr, 'update beacon.db %s' % err
            print >> sys.stderr, 'oprator='+op+' summit='+code
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
        return (foreign, continent, state % 10, 0, mesg)
    
    conn_beacon.close()
    conn_aprslog.close()
    return (True,'', -1, 0, "Oops!")

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
        res =(lat,lng)
    conn_dxsummit.close()
    return res
    
def parse_alerts(url):
    try:
        response = requests.get(url)
    except Exception as e:
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
        
def parse_json_alerts(url,time_to):
    try:
        param = urllib.urlencode(
        {
        'client': 'sotawatch',
        'user': 'anon'
        })
        readObj= urllib.urlopen(url+'/api/alerts?'+param)
        res = readObj.read()
        alerts = json.loads(res)
    except Exception as e:
        print >>sys.stderr, 'JSON GET ALERTS %s' % e
        sys_updatestat('SOTAWATCH',E_FATAL)
        return []

    sys_updatestat('SOTAWATCH',E_NONE)
    result = []
    
    for item in alerts:
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
        if alert_time < time_to:
            result.append({'time':alert_time,
                           'start':alert_start,
                           'end': alert_end,
                           'poster': item['posterCallsign'],
                           'callsign': item['activatingCallsign'].upper().replace(" ",""),
                           'summit': item['associationCode'].upper()+"/"+item['summitCode'].upper(),
                           'summit_info': item['summitDetails'],
                           'freq': item['frequency'],
                           'comment': item['comments'],
                           'poster': "(Posted by " + item['posterCallsign'] + ")"})

    return result

def calc_distance(p1,p2):
    return (float(p1[0])-float(p2[0]))**2 + (float(p1[1])-float(p2[1]))**2

def smooth_route(route):
    if len(route)<10:
        return route
    res = []
    r_pos = 0
    for d in route:
        if len(res)>4:
            d1 = calc_distance(res[r_pos-1]['latlng'],d['latlng'])
            insertp = False
            T1 = d['i_time']
            for i in range(2,len(res)):
                d2 = calc_distance(res[r_pos-i]['latlng'],d['latlng'])
                T2 = res[r_pos-i]['i_time']
                if d1 > d2 and (T1-T2)<300:
                    d1 = d2
                    ip = i-1
                    insertp = True
            if insertp:
                res.insert(r_pos-ip,d)
            else:
                res.append(d)
        else:
            res.append(d)
        r_pos+=1
    return res

def readlast3(c):
    global latestSpot
    if c == 'JA':
        slist = latestSpot['JA']
    elif c == 'AS':
        slist = latestSpot['AS/OC']
    elif c == 'OC':
        slist = latestSpot['AS/OC']
    elif c == 'EU':
        slist = latestSpot['EU/AF']
    elif c == 'AF':
        slist = latestSpot['EU/AF']
    elif c == 'NA':
        slist = latestSpot['NA/SA']
    elif c == 'SA':
        slist = latestSpot['NA/SA']
    else:
        slist = latestSpot['WW']
        
    if len(slist)>0:
        msg = ""
        slist.reverse()
        for o in slist[0:3]:
            msg = msg +' '+ o['spot_time'][6:] +'-'+o['op']+'-'+o['spot_freq']
        msg = msg.strip(' ')
    else:
        msg ="No spots."
        
    return msg

def update_json_data():
    global latestSpot

    sys_clearstat()

    conn_aprslog = sqlite3.connect(aprslog_db)
    cur_aprslog = conn_aprslog.cursor()
    conn = sqlite3.connect(alert_db)
    cur = conn.cursor()

    q = "attach database '" + association_db + "' as assoc"
    cur.execute(q);

    q = 'select distinct O.operator,O.callsign,O.summit,C.association,C.continent,A.time,A.summit_info,A.lat_dest,A.lng_dest,A.alert_freq,A.alert_comment,B.lat,B.lng,B.dist,S.time,S.summit,S.summit_info,S.lat,S.lng,S.spot_freq,S.spot_mode,S.spot_comment,S.spot_color,S.poster from oprts as O  left outer join assoc.associations as C on (O.summit=C.code) left outer join alerts as A on (O.operator=A.operator and O.summit=A.summit) left outer join spots as S on (O.operator=S.operator and O.summit = S.summit) left outer join beacons AS B on (O.operator=B.operator and O.summit = B.summit)'
    cur.execute(q);
    rows = cur.fetchall()

    now = int(datetime.utcnow().strftime("%s"))
    alert_start = now + 3600 * KEYS['ALERT_FROM']
    alert_end= now  + 3600 * KEYS['ALERT_TO']
    mid_hist = now - 3600 * KEYS['MID_HIST']

    alert_count = 0
    spot_count = 0
    aprs_count = 0
    beacon_count = 0
    entry_db = {}

    for (op,call,summit,assoc,conti,atime,ainfo,alatdest,alngdest,afreq,acomment,blat,blng,bdist,stime,ssummit,sinfo,slat,slng,sfreq,smode,scomment,scolor,sposter) in rows:

        if atime:
            at = datetime.fromtimestamp(int(atime)).strftime("%m/%d %H:%M")
        else:
            at =""
            afreq = ""
            acomment = ""
            
        if stime:
            st = datetime.fromtimestamp(int(stime)).strftime("%m/%d %H:%M")
            delta = now - stime
            if delta <= 180:
                scolor = 'red-blink'
                spot_count += 1
            elif delta <= 1800:
                scolor = 'red'
                spot_count += 1
            elif delta <= 3600:
                scolor = 'orange'
            elif delta <= 7200:
                scolor = 'normal'
            else:
                scolor = 'obsolete'
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
            aprs_start = atime + 3600 * KEYS['WINDOW_FROM']
            aprs_end = atime + 3600 * KEYS['WINDOW_TO']
            if stime:
                time = stime
        else:
            time = stime
            aprs_start = stime + 3600 * KEYS['WINDOW_FROM']
            aprs_end = stime + 3600 * KEYS['WINDOW_TO']
            
        if time > (now-60*30):
            spot_type = "after"
        else:
            spot_type = "before"
        
        q = 'select time,lat,lng,dist,state,summit from aprslog where operator = ? and time > ? and time < ?'
        cur_aprslog.execute(q,(op,aprs_start,aprs_end,))
        route = {}
        smoothed = {}
        for s in target_ssids:
            route['id'+s] = []
            smoothed['id'+s] = []

        for (t,lat,lng,dist,state,aprs_summit) in cur_aprslog.fetchall():
            ssid = target_ssids[int(state)/10]
            tm = datetime.fromtimestamp(int(t)).strftime("%H:%M")
            o = {'i_time':int(t),'time':tm,
                 'latlng':[float(lat),float(lng)],
                 'dist':dist,'summit':aprs_summit}
            route['id'+ssid].append(o)

        #smoothed[0] = smooth_route(route[0])
        #smoothed[1] = smooth_route(route[1])

        entry_db[op+summit] = (time,{'op':call,
                              'opid':op,
                              'summit':summit,'summit_info':ainfo,
                              'association':assoc,'continent':conti,
                              'summit_latlng':[float(alatdest),float(alngdest)],
                              'alert_time':at,
                              'alert_freq':afreq,
                              'alert_comment':acomment,
                              'spot_time':st,
                              'spot_freq':sfreq.strip(' '),
                              'spot_mode':smode,
                              'spot_comment':scomment,
                              'spot_color':scolor,
                              'aprs_message':"",
                              'route':route,
                              #'smoothed':smoothed,
                              'spot_type':spot_type})

    js = sorted(entry_db.values(),key=lambda x: x[0])

    dxl = []
    jal = []
    dxml= []
    dxll= []

    latestSpot = { 'WW':[],'JA':[],'AS/OC':[],'EU/AF':[], 'NA/SA':[] }

    for (t,d) in js:
        if t < now:
            dxll.append(d)
            if (t > mid_hist):
                dxml.append(d)

        if t > alert_start:

            alert_count += 1
            l_1 =len(d['route']['id5']) + len(d['route']['id7'])
            if l_1 > 0:
                beacon_count += l_1
                aprs_count += 1

            if re.search(KEYS['JASummits'],d['summit']):
                jal.append(d)
                dxl.append(d)
                read_user_params(d['opid'],[('Active',True),('Retry',3)])
                if t < now and d['spot_time'] != "" and d['continent']:
                    update_user_params(d['opid'],[('LastSpotOn',d['summit']),('LastSpotAt',d['spot_time'])])
                    latestSpot['JA'].append(d)
                    latestSpot['AS/OC'].append(d)
                    latestSpot['WW'].append(d)
            else:
                dxl.append(d)
                read_user_params(d['opid'],[('Active',False),('Retry',3)])
                if t < now and d['spot_time'] != "" and d['continent']:
                    update_user_params(d['opid'],[('LastSpotOn',d['summit']),('LastSpotAt',d['spot_time'])])
                    latestSpot['WW'].append(d)
                    if d['continent'] in ['AS','OC']:
                        latestSpot['AS/OC'].append(d)
                    elif d['continent'] in ['EU','AF']:
                        latestSpot['EU/AF'].append(d)
                    elif d['continent'] in ['NA','SA']:
                        latestSpot['NA/SA'].append(d)
                        
    sys_updatestatall(alert_count, spot_count, aprs_count, beacon_count)        

    with open(output_json_file+'.json',"w") as f:
        json.dump(dxl,f)
        
    with open(output_json_jafile+'.json',"w") as f:
        json.dump(jal,f)

    with open(output_json_file+'-mid-hist.json',"w") as f:
        json.dump(dxml,f)

    with open(output_json_file+'-hist.json',"w") as f:
        json.dump(dxll,f)
        
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
    except Exception as e:
        print >>sys.stderr, 'JSON GET SPOTS %s' % e
        sys_updatestat('SOTAWATCH',E_FATAL)
        return []

    try:
        r = json.loads(res)
    except Exception as e:
        print >>sys.stderr, 'JSON SPOTS LOAD %s' % e
        sys_updatestat('SOTAWATCH',E_WARN)
        return []
    
    sys_updatestat('SOTAWATCH',E_NONE)
    
    conn2 = sqlite3.connect(alert_db)
    cur2 = conn2.cursor()
    r.reverse()
    for item in r:
        if item['comments'] is None:
            item['comments'] = ""
        ts = item['timeStamp']
        ts = ts[:ts.find('.')]
        spot_time = int(datetime.strptime(ts,'%Y-%m-%dT%H:%M:%S').strftime("%s"))
        spot_end= spot_time  + 3600 * KEYS['WINDOW_TO']
        activator = item['activatorCallsign'].upper().replace(" ","")
        m = re.match('(\w+)/(\w+)/(\w+)',activator)
        if m:
            op = m.group(2)
        else:
            m = re.match('(\w+)/(\w+)',activator)
            if m:
                op = m.group(1)
            else:
                op = activator.strip()

        summit = item['associationCode']+"/"+item['summitCode']
        summit = summit.upper()
        (lat,lng) = parse_summit(summit)

        q ='insert or replace into spots (time,end,operator,callsign,summit,summit_info,lat,lng,spot_freq,spot_mode,spot_comment,spot_color,poster) values (?,?,?,?,?,?,?,?,?,?,?,?,?)'
        cur2.execute(q,(spot_time,spot_end,op,activator,summit,item['summitDetails'],lat,lng,item['frequency'],item['mode'],item['comments'],item['highlightColor'],item['callsign']))
        last_tweetat = read_params('last_tweetat')
        if spot_time >= last_tweetat:
            st = datetime.fromtimestamp(int(spot_time)).strftime("%H:%M")
            mesg = st +' ' + activator + ' on ' + summit + ' (' + item['summitDetails'] +') '+ item['frequency'] + ' ' + item['mode'] +' '+item['comments'] + '[' + item['callsign'] + ']'
            mesg = mesg + ' ' + sotalive_url + '/#' + urllib.quote(op.encode('utf8') + '+' + summit.encode('utf8') , '')
            if re.search(KEYS['JASummits'],summit):
                tweet(tweet_api,mesg)
            #tweet(tweet_api_debug,mesg)

    update_params('last_tweetat',int(datetime.utcnow().strftime("%s")))
    conn2.commit()
    conn2.close()
    update_json_data()
    
def update_alerts():
    global aprs_filter
    
    try:
        conn = sqlite3.connect(alert_db)
    except Exception as err:
        print >> sys.stderr, alert_db
        print >> sys.stderr, '%s' % err
        return
    
    try:
        aprs = sqlite3.connect(aprslog_db)
    except Exception as err:
        print >> sys.stderr, aprslog_db
        print >> sys.stderr, '%s' % err
        return
    
    cur = conn.cursor()
    cur2 = conn.cursor()
    aprs_cur = aprs.cursor()
    
    now = int(datetime.utcnow().strftime("%s"))
    keep_in_db = now - 3600 * KEYS['KEEP_IN_DB']
    keepin_aprs = now - 2 * 3600 * KEYS['KEEP_IN_DB']
    keep_in_db_hist = now - 3600 * KEYS['WINDOW_TO'] + 3600 * KEYS['WINDOW_FROM']
    
    aprs_cur.execute("delete from aprslog where time < %s" % str(keepin_aprs))
    aprs.commit()
    aprs.close()

    q = 'drop table if exists current'
    cur.execute(q)
    q = 'create table current(operator text,summit text)'
    cur.execute(q);
    
    q = 'create table if not exists alerts (time int,start int,end int,operator text,callsign text,summit text,summit_info text,lat_dest text,lng_dest text,alert_freq text,alert_comment text,poster text,primary key(callsign,summit))'
    cur.execute(q)
    q = 'delete from alerts where end < ?'
    cur.execute(q,(keep_in_db,))
    conn.commit()

    q ='create table if not exists beacons (start int,end int,operator text,lastseen int,lat text,lng text,lat_dest text,lng_dest text,dist int,az int,state int,summit text,message text,message2 text,tlon int,lasttweet text,type text,primary key(operator,summit))'
    cur2.execute(q)
    q = 'delete from beacons where end < ?'
    cur2.execute(q,(keep_in_db,))

    q ='create table if not exists spots (time int,end int,operator text,callsign text,summit text,summit_info text,lat text,lng text,spot_freq text,spot_mode text,spot_comment text,spot_color text,poster text,primary key(operator))'  
    cur2.execute(q)
    q = 'delete from spots where end < ?'
    cur2.execute(q,(keep_in_db,))

    q = 'create view if not exists oprts as select distinct operator,callsign, summit from alerts union select operator,callsign,summit from spots;'
    cur2.execute(q)

    q = 'create table if not exists message_history(time int,operator text,ssid text, summit text,state int,distance int,primary key(operator,ssid,summit))'
    cur2.execute(q)
    q = 'delete from message_history where time < ?'
    cur2.execute(q,(keep_in_db_hist,))
    
    conn.commit()

    res = parse_json_alerts(sotawatch_json_url,now+3600 * KEYS['ALERT_TO'])

    operators = []

    for user in KEYS['TEST_USER']:
        d = {'time':now,'start':now-100,'end':now+10800,
             'operator':user,'callsign':user,'summit':'JA/KN-006',
             'summit_info':'Test','freq':'433-fm',
             'comment':'Alert Test','poster':'(Posted By JL1NIE)'}
        res.append(d)
    
    for d in res:
        (lat_dest,lng_dest) = parse_summit(d['summit'])

        m = re.match('(\w+)/(\w+)/(\w+)',d['callsign'])
        if m:
            op = m.group(2)
        else:
            m = re.match('(\w+)/(\w+)',d['callsign'])
            if m:
                op = m.group(1)
            else:
                op = d['callsign']

        q = 'insert into current(operator,summit) values (?,?)'
        cur.execute(q,(op,d['summit']))
        
        q = 'insert or replace into alerts(time,start,end,operator,callsign,summit,summit_info,lat_dest,lng_dest,alert_freq,alert_comment,poster) values (?,?,?,?,?,?,?,?,?,?,?,?)'
        cur.execute(q,(d['time'],d['start'],d['end'],
                       op,d['callsign'],
                       d['summit'],d['summit_info'],
                       str(lat_dest),str(lng_dest),
                       d['freq'],
                       d['comment'],d['poster']))
        if now >= d['start'] and now <= d['end']:
            if not op in operators:
                operators.append(op)
                q = 'select * from beacons where operator = ? and summit = ?'
                cur2.execute(q,(op,d['summit']))
                r = cur2.fetchall()
                if len(r)>0:
                    q = 'update beacons set start = ? ,end = ? where operator = ? and summit = ?'
                    cur2.execute(q,(d['start'],d['end'],op,d['summit']))
                else:
                    q = 'insert into beacons (start,end,operator,lastseen,lat,lng,lat_dest,lng_dest,dist,az,state,summit,message,message2,tlon,lasttweet,type) values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'
                    cur2.execute(q,(d['start'],d['end'],op,
                                    0, #lastseen
                                    '', # lat
                                    '', # lng
                                    str(lat_dest), # lat_dest
                                    str(lng_dest), # lng_dest
                                    -1,0,
                                    NOTRCVD,
                                    d['summit'],
                                    d['summit_info'],
                                    d['summit_info'],
                                    0,'',
                                    'SW2'))
        conn.commit()
        
    q = 'delete from alerts where (operator,summit) not in (select * from current) and alerts.time > ?'
    cur.execute(q,(now,))

    q = 'delete from beacons where (operator,summit) not in (select * from current) and beacons.start > ?'
    cur2.execute(q,(now,))

    q = 'select distinct operator from beacons where start < ? and end > ?'
    cur.execute(q,(now,now))
    operators = []
    for ((r,)) in cur.fetchall():
        operators.append(r.strip())
    aprs_filter =  "b/"+ "-*/".join(operators) +"-*"
    if aprs_beacon:
        aprs_beacon.set_filter(aprs_filter)
    #print >>sys.stderr, 'APRS Filter:' + aprs_filter
    conn.commit()
    conn.close()
        
def tweet_alerts():
    today = datetime.now(localtz).strftime("%d %B %Y")
    conn = sqlite3.connect(alert_db)
    cur = conn.cursor()
    start = int(datetime.utcnow().strftime("%s")) + 3600 * KEYS['ALERT_FROM']
    end = int(datetime.utcnow().strftime("%s")) + 3600 * KEYS['TWEET_ALERT_TO']
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
    mesg = mesg + today + "."
    tweet(tweet_api,mesg)
    
    for (tm,_,_,op,call,summit,info,lat,lng,freq,comment,poster) in rows:
        tm = datetime.fromtimestamp(int(tm)).strftime("%H:%M")
        mesg = tm + " " + call + " on\n" + summit + " " + freq + "\n" + info + "\n" + comment + " " + poster
        mesg = mesg + ' ' + sotalive_url + '/#' + urllib.quote(op.encode('utf8') + '+' + summit.encode('utf8'), '')
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
    for i in range(2):
        msgno = get_new_msgno()
        mlist.append(msgno)
        m = message + '{' + str(msgno)
        if debug:
            print "Sending("+ str(i) + "):" + m
        else:
            aprs.sendall(m)
        sleep(60+int(i/2)*30)
        if ack_received(mlist):
            break
    discard_ack(mlist)
    if len(mlist) == 2:
        print >>sys.stderr, "APRS: Can't send message:" + callfrom + ' ' + message + '\n'

        
def send_message_with_ack(aprs, callfrom, message):
    header = aprs_user+">APRS,TCPIP*::"+callfrom+":"
    if len(message)>67:
        message = message[0:67]
    if debug:
        print "Sending:" + header + message
    else:
        th = Thread(name="MessageWorker",target=send_message_worker,args=(aprs, callfrom, header+message))
        th.start()

def send_long_message_with_ack2(aprs, callfrom, message):
    for m in message.splitlines():
        send_message_with_ack(aprs, callfrom, m)

def send_message_worker2(aprs, callfrom, header, messages,retry):
    retry += 1
    for message in messages.splitlines():
        mlist = []
        wait_timer = 7
        for i in range(retry):
            msgno = get_new_msgno()
            mlist.append(msgno)
            if len(message)>67:
                message = message[0:67]
            m = header + message + '{' + str(msgno)
            print >>sys.stderr, 'APRS raw message(' + str(wait_timer) + ',' + str(i) + '):' + m
            aprs.sendall(m.encode('utf-8'))
            sleep(wait_timer)
            if ack_received(mlist):
                print >>sys.stderr, 'APRS recv_ack(' +str(wait_timer) +','+  str(msgno)+ ')'
                break
            else:
                wait_timer *= 2

        discard_ack(mlist)
        if len(mlist) == retry:
            print >>sys.stderr, "APRS: Can't send message:" + callfrom + ' ' + message + '\n'

def send_long_message_with_ack(aprs, callfrom, messages,retry = 3):
    header = aprs_user+">APRS,TCPIP*::"+callfrom+":"
    th = Thread(name="MessageWorker",target=send_message_worker2,args=(aprs, callfrom, header, messages,retry))
    th.start()
 
def send_summit_message(callfrom, lat ,lng):
    foreign,continent,state,tlon,mesg = lookup_summit(callfrom,lat,lng)
    if state == ONSUMMIT: # On Summit
        mesg = mesg + "\n" + readlast3(continent)
        print >>sys.stderr, 'APRS: Message ' + callfrom + ':On Summit'
        if read_user_param(callfrom,'Active'):
            send_long_message_with_ack(aprs_beacon,callfrom,mesg,read_user_param(callfrom,'Retry'))
    elif state == APRCH:# Approaching Summit
        print >>sys.stderr, 'APRS: Message ' + callfrom + ':Approaching'
        if read_user_param(callfrom,'Active'):
            send_long_message_with_ack(aprs_beacon,callfrom,mesg,read_user_param(callfrom,'Retry'))
    del mesg

def on_service(callfrom):
    (op,_,_) = parse_callsign(callfrom)
    conn_beacon = sqlite3.connect(alert_db)
    cur_beacon = conn_beacon.cursor()
    q = 'select * from beacons where operator = ?'
    cur_beacon.execute(q,(op,))
    result = False
    for (_,_,_,_,_,_,lat_dest,lng_dest,_,_,state,code,mesg,mesg2,tlon,lasttweet,mode) in cur_beacon.fetchall():
        result = True
    conn_beacon.close()
    return result

def set_tweet_location(callfrom,tlon):
    (op,_,_) = parse_callsign(callfrom)
    conn_beacon = sqlite3.connect(alert_db)
    cur_beacon = conn_beacon.cursor()
    q = 'update beacons set tlon = ? where operator = ?'
    try:
        cur_beacon.execute(q,(tlon,op,))
        conn_beacon.commit()
    except Exception as err:
        print >> sys.stderr, 'update beacon.db %s' % e
    conn_beacon.close()

def check_dupe_mesg(callfrom,tw):
    (op,_,_) = parse_callsign(callfrom)
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

def check_beacon_status():
    conn_beacon = sqlite3.connect(alert_db)
    cur_beacon = conn_beacon.cursor()
    now = int(datetime.utcnow().strftime("%s")) - 3600 * 2
    q = 'select * from beacons where state >=0 and lastseen > ?'
    cur_beacon.execute(q,(now,))
    approach = []
    descend = []
    on_summit =[]
    recv = []
    for (_,_,op,last,_,_,_,_,_,_,state,_,_,_,_,_,_) in cur_beacon.fetchall():
        state = state % 10

        if state == APRCH or state == APRCH_SENT or state == NEAR:
            approach.append(op)
        elif state == ONSUMMIT or state == ONSUMMIT_SENT:
            tm = datetime.fromtimestamp(last).strftime("%H:%M")
            on_summit.append(op+"("+tm+")")
        elif state == DESC:
            descend.append(op)
        elif state == RCVD:
            recv.append(op)
            
    conn_beacon.close()

    on_summit = list(set(on_summit))
    approach = list(set(approach))
    descend = list(set(descend))
    recv = list(set(recv))
    
    if on_summit:
        result = "On:"+','.join(on_summit)
    else:
        result = "On:None"
    if approach:
        result = result + " APR:"+','.join(approach)
    if descend:
        result = result + " DESC:"+','.join(descend)
    if recv:
        result = result + " RECV:"+','.join(recv)

    return result

def check_user_status(callfrom):
    r = read_user_params(callfrom,[('Active',None),('Retry',None),
                                   ('LastActOn',None),('LastActAt',None),
                                   ('LastSpotOn',None),('LastSpotAt',None)],False)
    (op,_,_) = parse_callsign(callfrom)
    mesg = op + ": "
    if r['Active']:
        mesg = mesg +"Message=Active: "
    else:
        mesg = mesg +"Message=Inactive: "
    if r['Retry']:
        mesg = mesg + "Max.Retry=" + str(r['Retry']) + ": "
    if r['LastActOn']:
        mesg = mesg +"LatestActivation: " + str(r['LastActAt']) + " " +  str(r['LastActOn']) + ": "  
    if r['LastSpotOn']:
        mesg = mesg + "LatestSpot: " + str(r['LastSpotAt']) + " " +  str(r['LastSpotOn']) + ": "  
    try:
	res = unicode(mesg,'utf-8')
    except Exception as e:
        return mesg
    return res

def do_command(callfrom,mesg):
    print >>sys.stderr, 'SLIPPER Command: ' + callfrom + ':' + mesg 
    for com in mesg.split(","):
        com = com.upper().strip()
        if com in ['HELP','?']:
            res = 'ACT,DEACT,DX,JA,AS,OC,EU,AF,NA,SA,BC,ST,LOC,RET=<num>,HELP,?'
            send_long_message_with_ack(aprs_beacon,callfrom,res)
            break
        if com in ['ACT']:
            update_user_param(callfrom,'Active',True)
            send_long_message_with_ack(aprs_beacon,callfrom,"Activate summit message.")
        elif com in ['DEACT']:
                update_user_param(callfrom,'Active',False)
                send_long_message_with_ack(aprs_beacon,callfrom,"Deactivate summit message.")
        elif com in ['DX']:
            res = readlast3('WW')
            send_long_message_with_ack(aprs_beacon,callfrom,res)
        elif com in ['JA']:
            res = readlast3('JA')
            send_long_message_with_ack(aprs_beacon,callfrom,res)
        elif com in ['AS']:
            res = readlast3('AS')
            send_long_message_with_ack(aprs_beacon,callfrom,res)
        elif com in ['OC']:
            res = readlast3('OC')
            send_long_message_with_ack(aprs_beacon,callfrom,res)
        elif com in ['EU']:
            res = readlast3('EU')
            send_long_message_with_ack(aprs_beacon,callfrom,res)
        elif com in ['AF']:
            res = readlast3('AF')
            send_long_message_with_ack(aprs_beacon,callfrom,res)
        elif com in ['NA']:
            res = readlast3('NA')
            send_long_message_with_ack(aprs_beacon,callfrom,res)
        elif com in ['SA']:
            res = readlast3('SA')
            send_long_message_with_ack(aprs_beacon,callfrom,res)
        elif com in ['BC']:
            res = check_beacon_status()
            send_long_message_with_ack(aprs_beacon,callfrom,res)
        elif com in ['ST']:
            res = check_user_status(callfrom)
            send_long_message_with_ack(aprs_beacon,callfrom,res)
        elif com in ['LOC']:
            res = lookup_from_op(callfrom)
            send_long_message_with_ack(aprs_beacon,callfrom,res)
        else:
            m = re.search('RET=(.+)',mesg,re.IGNORECASE)
            if m:
                cs = m.group(1)
                try:
                    rc = int(cs.strip())
                except Exception as e:
                    rc = 3
                if rc > 18:
                    rc = 17
                update_user_param(callfrom,'Retry',rc)
                send_long_message_with_ack(aprs_beacon,callfrom,'Set max. messsage retry = '+str(rc))
            else:
                (admin,_,_) = parse_callsign(aprs_user)
                (u,_,_) =  parse_callsign(callfrom)
                if u == admin:
                    m1 = re.search('DCALL=(.+)',mesg,re.IGNORECASE)
                    m2 = re.search('ACALL=(.+)',mesg,re.IGNORECASE)
                    if m1:
                        (call,_,_) =parse_callsign(m1.group(1))
                        update_user_param(call,'Active',False)
                        send_long_message_with_ack(aprs_beacon,callfrom,'Deactivate = '+call)
                    elif m2:
                        (call,_,_) =parse_callsign(m2.group(1))
                        update_user_param(call,'Active',True)
                        send_long_message_with_ack(aprs_beacon,callfrom,'Activate = '+call)
                    elif com in ['DUMP']:
                        dump_userdb()
                        send_long_message_with_ack(aprs_beacon,callfrom,"dump user_db done.")
                    else:
                        res = readlast3('JA')
                        send_long_message_with_ack(aprs_beacon,callfrom,'? ' + res)
                else:
                    res = readlast3('JA')
                    send_long_message_with_ack(aprs_beacon,callfrom,'? ' + res)
            break
    del mesg
        
def callback(packet):
    msg = aprslib.parse(packet)
    callfrom = msg['from'] + "      "
    callfrom = callfrom[0:9]
    ssidtype = callfrom[callfrom.rfind('-')+1:].strip()
    
    if debug:
        print "Receive:"+callfrom+ ":"+msg['format']+"-"+msg['raw']
    if msg['format'] in  ['uncompressed','compressed','mic-e']:
        if ssidtype in target_ssids:
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

def update_params(key, value):
    db = shelve.open(params_db,'c')
    db[key] = value
    db.close()
    return value

def read_params(key):
    db = shelve.open(params_db,'c')
    try:
        value = db[key]
    except  Exception as e:
        value = 0
        db[key] = 0
    db.close()
    return value

def setup_userdb():
    global user_db
    conn_user = sqlite3.connect(user_db)
    conn_user.execute("create table if not exists user_db(operator text primary key,obj blob)")
    conn_user.commit()
    conn_user.close()

def p2o(param):
    return bz2.compress(pickle.dumps(param), 3)

def o2p(obj):
    return pickle.loads(bz2.decompress(obj))

def update_user_param(callfrom, key, value):
    global user_db
    
    (op,_,_) = parse_callsign(callfrom)
    conn = sqlite3.connect(user_db)
    conn.text_factory = str
    for u in conn.execute('select * from user_db where operator = ?',(op,)):
        (o,obj) = u
        param = o2p(obj)
        param[key] = value
        conn.execute('update user_db set obj = ? where operator = ?',(p2o(param),op))
        conn.commit()
        conn.close()
        return value
    param = {}
    param[key] = value
    conn.execute('insert into user_db(operator, obj) values(?, ?)',(op,p2o(param)))
    conn.commit()
    conn.close()
    return value

def read_user_param(callfrom, key, init = None):
    global user_db
    
    (op,_,_) = parse_callsign(callfrom)
    conn = sqlite3.connect(user_db)
    conn.text_factory = str
    
    value = init
    for u in conn.execute('select * from user_db where operator = ?',(op,)):
        (o,obj) = u
        param = o2p(obj)
        try:
            value = param[key]
        except Exception as e:
            param[key] = value
            conn.execute('update user_db set obj = ? where operator = ?' ,(p2o(param),op))
            conn.commit()
        conn.close()
        return value
    param = {}
    param[key] = value
    conn.execute('insert into user_db (operator, obj) values (?, ?)', (op,p2o(param)))
    conn.commit()
    conn.close()
    return value

def read_user_params(callfrom, vals,update = True):
    global user_db

    (op,_,_) = parse_callsign(callfrom)
    conn = sqlite3.connect(user_db)
    conn.text_factory = str
    rslt = {}
    for (key,init) in vals:
        value = init
        r = conn.execute('select * from user_db where operator = ?',(op,)).fetchone()
        if r:
            (o,obj) = r
            param = o2p(obj)
            try:
                value = param[key]
                rslt[key] = value
            except Exception as e:
                if update:
                    param[key] = value
                    conn.execute('update user_db set obj = ? where operator = ?' ,(p2o(param),op))
                    conn.commit()
                    rslt[key] = value
                else:
                    rslt[key] = None
        else:
            if update:
                param = {}
                param[key] = value
                conn.execute('insert into user_db (operator, obj) values (?, ?)', (op,p2o(param)))
                conn.commit()
                rslt[key] = value
            else:
                rslt[key] = None
    conn.close()
    return rslt

def update_user_params(callfrom, vals):
    global user_db

    (op,_,_) = parse_callsign(callfrom)
    conn = sqlite3.connect(user_db)
    conn.text_factory = str
    rslt = []
    for (key,value) in vals:
        r = conn.execute('select * from user_db where operator = ?',(op,)).fetchone()
        if r:
            (o,obj) = r
            param = o2p(obj)
            param[key] = value
            conn.execute('update user_db set obj = ? where operator = ?' ,(p2o(param),op))
        else:
            param = {}
            param[key] = value
            conn.execute('insert into user_db (operator, obj) values (?, ?)', (op,p2o(param)))
    conn.commit()            
    conn.close()

def dump_userdb():
    conn = sqlite3.connect(user_db)
    conn.text_factory = str
    for u in conn.execute('select * from user_db'):
        (op,obj) = u
        print >> sys.stderr, check_user_status(op)
    conn.close()
    print >> sys.stderr, "APRS Filter:" + aprs_filter
    
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

    setup_userdb()
    
    update_alerts()
    update_spots()
    
def main():
    global tweet_api
    global tweet_api_debug

    try:
        auth = tweepy.OAuthHandler(KEYS['ConsumerkeySOTAwatch'], KEYS['ConsumersecretSOTAwatch'])
        auth.set_access_token(KEYS['AccesstokenSOTAwatch'], KEYS['AccesstokensecretSOTAwatch'])
        tweet_api = tweepy.API(auth)
    except Exception as e:
        print >>sys.stderr, 'access error: %s' % e
        sys.exit(1)

    try:
        auth = tweepy.OAuthHandler(KEYS['ConsumerkeySOTAwatch2'], KEYS['ConsumersecretSOTAwatch2'])
        auth.set_access_token(KEYS['AccesstokenSOTAwatch2'], KEYS['AccesstokensecretSOTAwatch2'])
        tweet_api_debug = tweepy.API(auth)
    except Exception as e:
        print >>sys.stderr, 'access error: %s' % e
        sys.exit(1)
        
    setup_db()

    logging.basicConfig()
    
    aprs = Thread(target=aprs_worker, args=())
    aprs.start()
    schedule.every(update_alerts_every).minutes.do(update_alerts)
    schedule.every(update_spots_every).minutes.do(update_spots)
    schedule.every().day.at(tweet_at).do(tweet_alerts)

    while True:
        schedule.run_pending()
        gc.collect()
        #objgraph.show_growth()
        sleep(30)

def test_db():
    setup_db()
    op = 'JL1NIE-5'
    tracks =[(35.679488, 139.754062),#54k
             (35.440663, 139.236127),#447m
             (35.440698, 139.234196),#300m
             (35.440494, 139.232486),#121m
             (35.440849, 139.231449),#23m
             (35.440849, 139.231449),#23m
             (35.440494, 139.232486),#121m
             (35.440698, 139.234196),#300m
             (35.440663, 139.236127),#447
             (35.679488, 139.754062)]
    tracks = [(41.409,-122.194901)]
    for (lat, lng) in tracks:
        print search_summit('JA-KN/006',lat,lng)
    update_json_data()
    
if __name__ == '__main__':
    main()

