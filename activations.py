#!/usr/bin/env python

import datetime
from HTMLParser import HTMLParser
#from icalendar import Calendar, Event
import matplotlib
matplotlib.use('Agg')
from numpy import *
import pytz
import re
import sqlite3
import sys
import telnetlib
import threading
from time import sleep
import tweepy
import urllib
import urllib2
from sotakeys import *

HOST = "arc.jg1vgx.net"
PORT = 7000
CALL = 'JL1NIE'
arc_init = ['set dx fil skimdupe\n',\
            'set dx ext skimmerquality\n',\
            'set dx fil cqzone = 25\n']

#arc_init = ['set dx fil skimdupe\n',\
#            'set dx ext skimmerquality\n']

sota_activators = []

agenda_url ='http://wwff.co/agenda/'
jaff_activators = []

debug = False
#debug = True

stop_count = 0
COUNT_MAX = 13 
HOUR = 3600
TWEET_PERIOD = 180

rbn_dict = {'':''}
jaff_rbn_dict = {'':''}
jaff_dict = {'':''}

rbn_dirty = False
jaff_rbn_dirty = False

tweet_api = None
tweet_api2 = None

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

class ActivationParser(HTMLParser):
    def __init__(self, api):
        HTMLParser.__init__(self)
        self.isStart = False
        self.isAlertDate = False
        self.isSpots = False
        self.spots = []
        self.currentSpot = ""
        self.cuurentDate = ""
        self.api = api

    def handle_starttag(self,  tagname,  attribute):
        attrs = dict(attribute)
        if 'div' == tagname and 'id' in attrs:
            if attrs['id'] == 'column1':
                self.isStart = True
        elif 'span' == tagname and 'class' in attrs:
            a = attrs['class']
            if a == 'alertDate':
                self.isAlertDate = True
            else:
                self.isAlertDate = False
        elif 'table' == tagname and 'class' in attrs:
            a = attrs['class']
            if a == 'spots':
                self.isSpots = True
            else:
                self.isSpots = False

    def handle_endtag(self,  tagname):
        if 'div' == tagname:
            if self.isStart:
                self.isStart = False

                (tzname, wakeupat) = KEYS['Alertafter']
                tzl = pytz.timezone(tzname)
                today = datetime.datetime.now(tzl)
                now = today.replace(hour=wakeupat, minute=0)
                last = today.replace(hour=23, minute=59)
                spots = []
                for (d, sp) in self.spots:
                    if re.search(KEYS['Alerts'], sp):
                        sl = sp.split()
                        start = datetime.datetime.strptime(
                            sl[0] + " " + d[1] + " " +
                            d[2] + " " + d[3], "%H:%M %d %B %Y")
                        start = start.replace(tzinfo=pytz.utc)
                        if start >= now and start <= last:
                            call = sl[1]
                            mountain = sl[3]
                            freq = []
                            for i in sl[4].split(','):
                                m = re.search('(\d+)\.*[\d|\.]*\-\w+', i)
                                if m:
                                    frq = int(m.group(1))
                                    if frq < 50:
                                        freq.append((int(m.group(1)), i))

                            freq.sort(key=lambda (f, t): f)
                            freq.reverse()
                            spots.append((d[2][0:3], d[3], start, sp,
                                          call, mountain, freq))

                tstr = now.strftime("%d %B %Y")
                if len(spots) > 0:
                    if len(spots) == 1:
                        header2 = "An SOTA activation is currently scheduled on " + tstr
                    else:
                        header2 = str(len(spots)) + " SOTA activations are currently scheduled on " + tstr

                    tweet(self.api, "SOTAwatch alerts:\n "+header2)

                    for (month, year, start, sp, call, mountain, frql) in spots:
                        tweet(self.api, sp)
                        if frql:
                            sota_activators.append((month, year, start, sp, call, mountain, frql))
                else:
                    tweet(self.api, "No activations are currently scheduled on "+tstr)
        elif 'span' == tagname:
            self.isAlertDate = False

        elif 'table' == tagname:
            self.isSpots = False
            self.spots.append((self.currentDate, self.currentSpot))
            self.currentSpot = ""

        elif 'td' == tagname:
            if self.isSpots:
                self.currentSpot = self.currentSpot + " "

    def handle_data(self,  data):
        data = data.strip("\n")
        data = data.strip("\t")
        if self.isStart:
            if self.isAlertDate:
                m = re.search("(\w+)\s*(\d+)\w+\s+(\w+)\s+(\d+)", data)
                if m:
                    self.currentDate = m.groups()
                self.isAlertDate = False
            elif self.isSpots:
                self.currentSpot = self.currentSpot + data


def draw_heatmap(api,  frq,  fdict,  prp, index):
    from matplotlib import pyplot as plt
    import numpy as np

    if KEYS['LOCALTIME']:
        columns = ['08', '09', '10', '11', '12', '13', '14', '15', '16', '17']
        (tzname, wakeupat) = KEYS['Alertafter']
        tz = pytz.timezone(tzname)
    else:
        columns = ['23', '00', '01', '02', '03', '04', '05', '06', '07', '08']
        tz = pytz.utc

    fig, ax = plt.subplots(figsize=(10, 10))
    ax.imshow(prp, aspect='0.5', interpolation='none')
    ax.set_xticks(np.arange(10), minor=False)
    ax.set_yticks(np.arange(54), minor=False)

    ax.xaxis.tick_top()
    ax.set_xticklabels(columns, minor=False)
    ax.set_yticklabels(index, minor=False)

    header = "Propagation Forecast for " + str(frq) + "MHz\n"
    ax.set_title(header, y=1.01)

    msg = ""

    for i in range(len(fdict)):
        (m, y, start, spot, call, mountain, ftxt) = fdict[i]
        t = start.replace(tzinfo=tz)
        tstr = tz.fromutc(t).strftime("%H%M %Z")
        t = tstr + "\n  " + ftxt + " " + call + " (" + mountain + ")"
        ax.text(10, 2 + i * 3, t)
        msg = msg + tstr + " " + call + "\n"

    if debug:
        plt.show()

    msg = header + msg
    plt.savefig(KEYS['VOAIMG'], dpi=64)
    tweet_with_media(api, KEYS['VOAIMG'], msg)


def forecast(api):
    frqtoint = {3: 1, 7: 2, 10: 3, 14: 4, 18: 5, 21: 6, 24: 7, 28: 8}
    db = sqlite3.connect(KEYS['VOACAP'])
    cur = db.cursor()
    fdict = {3: [], 7: [], 10: [], 14: [], 18: [], 21: [], 24: [], 28: []}
    for ((m, year, start, spot, call, mountain, frql)) in sota_activators:
        for (freq, ftxt) in frql:
            if freq in fdict:
                fdict[freq].append((m, year, start, spot, call, mountain, ftxt))

    for i in fdict.keys():
        fdict[i].sort(key=lambda (m, year, start, spot, call, mountain, ftxt): start)

    for i in [28, 24, 21, 18, 14, 10, 7, 3]:
        if fdict[i]:
            (m, year, start, spot, call, mountain, ftxt) = fdict[i][0]
            cur.execute(
                "select zone, zonename, rellist from propagation where p_year = ? AND p_month = ? AND band = ?", (year, m, frqtoint[i]))
            if cur:
                zlabel = []
                predict = []
                for (zone, zonename, prop) in cur.fetchall():
                    p = prop.split(',')
                    pl = [p[22], p[23], p[0], p[1], p[2],
                          p[3], p[4], p[5], p[6], p[7]]
                    predict.append(map(float, pl))
                    zlabel.append(zonename)

                #draw_heatmap(api, i, fdict[i], predict, index=zlabel)
    db.close()

# def jaff_activation(api):
#     global jaff_activators
#     global agenda_utl

#     if debug:
#         file = open('wwff-a0ee89abb4a.ics','rb')
#         the_page = file.read()
#     else:
#         user_agent = 'Mozilla/5.0 (Windows NT 6.1; Win64; x64)'
#         values = {
#         'ical':'1',
#         'tribe_display':'list'
#         }
#         headers = { 'User-Agent' : user_agent }
#         data = urllib.urlencode(values)
#         req = urllib2.Request(agenda_url,data,headers)
#         res = urllib2.urlopen(req)
#         the_page = res.read()

#     cal = Calendar.from_ical(the_page)
    
#     ldata = []
#     (tzname, wakeupat) = KEYS['Alertafter']
#     tzl = pytz.timezone(tzname)
#     today = datetime.datetime.now(tzl)
#     now = today.replace(hour=wakeupat, minute=0)
#     last = today.replace(hour=23, minute=59)

#     for ev in cal.walk():
#         if ev.name == 'VEVENT':
#             summary = ev['summary'].encode('utf-8')
#             m = re.search("(JAFF-\S+)\s*by\s*(\S+)",summary)
#             if m:
#                 start_t = ev.decoded("dtstart")
#                 if not isinstance(start_t,type(now)):
#                     start_t = datetime.datetime.combine(start_t,datetime.time(0,0))
#                 end_t = ev.decoded("dtend")
#                 if not isinstance(end_t,type(now)):
#                     end_t = datetime.datetime.combine(end_t,datetime.time(23,59))

#                 start_t = pytz.utc.localize(start_t)
#                 end_t = pytz.utc.localize(end_t)
#                 jaff = m.group(1)
#                 call = m.group(2)
#                 if end_t >= now and start_t <= last:
#                     desc = ev['description'].encode('utf-8')
#                     url = ev['url'].encode('utf-8')
#                     jaff_activators.append((start_t,end_t,jaff,call,desc,url))
#     tstr = now.strftime("%d %B %Y")
#     if len(jaff_activators) > 0:
#         if len(jaff_activators) == 1:
#             header2 = "A JAFF activation is currently scheduled on " + tstr
#         else:
#             header2 = str(len(jaff_activators)) + " JAFF activations are currently scheduled on " + tstr
#         tweet(api,"WWFF agenda:\n"+header2)
#         for (st,end,jaff,call,desc,url) in jaff_activators:
#             st_jst = st.astimezone(tzl)
#             end_jst = end.astimezone(tzl)
#             tm_jst = st_jst.strftime("%m/%d %H:%M")+ " JST - " + end_jst.strftime("%m/%d %H:%M") + " JST"
#             tm_utc = st.strftime("%m/%d %H:%M")+ " - " + end.strftime("%m/%d %H:%M")
#             msg = tm_jst + "(" +tm_utc + ") " + call + " in " + jaff + "\n" +url
#             tweet(api,msg)
#     else:
#         tweet(api,"No JAFF activations are currently scheduled on "+ tstr)
        
def stop_cluster():
    global stop_count
    global COUNT_MAX
    global HOUR
    stop_count = stop_count + 1
    if stop_count < COUNT_MAX:
        t = threading.Timer(HOUR,stop_cluster)
        t.start()

def tweet_rbn():
    global tweet_api
    global tweet_api2
    global rbn_dirty
    global jaff_rbn_dirty
    global rbn_dict
    global jaff_rbn_dict
    global stop_count
    global TWEET_PERIOD

    if rbn_dirty:
        for i in rbn_dict.keys():
            if len(i)>0:
                (freq,call,m) = rbn_dict[i][0]
                msg = ""
                for j in rbn_dict[i]:
                    (f1,c1,m) = j
                    msg = msg + m
                (tzname, wakeupat) = KEYS['Alertafter']
                tzl = pytz.timezone(tzname)
                now = datetime.datetime.now(tzl)
                t = now.strftime("%H:%M:%S")
                tweet(tweet_api,"{} {} on {}\n    Skimmer:{} #SOTAspotJA".format(t,call,freq,msg))
                rbn_dirty = False
        rbn_dict = {'':''}

    if jaff_rbn_dirty:
        for i in jaff_rbn_dict.keys():
            if len(i)>0:
                (freq,call,jaff,url,skimmer,db) = jaff_rbn_dict[i]
                (tzname, wakeupat) = KEYS['Alertafter']
                tzl = pytz.timezone(tzname)
                now = datetime.datetime.now(tzl)
                t = now.strftime("%H:%M")
                tweet(tweet_api2,"{} {} in {} {} at {}({}dB)\n{}".format(t,call,jaff,freq,skimmer,db,url))
                jaff_rbn_dirty = False
        jaff_rbn_dict = {'':''}

    if stop_count < COUNT_MAX:
        t = threading.Timer(TWEET_PERIOD,tweet_rbn)
        t.start()

def run_cluster(api,api2):
    global CALL
    global COUNT_MAX
    global stop_count
    global tweet_api
    global tweet_api2
    global rbn_dict
    global jaff_dict
    global jaff_rbn_dict
    global rbn_dirty
    global jaff_rbn_dirty

    tn = telnetlib.Telnet()
    tn.open(HOST,7000)
    tn.read_until("Please enter your call:")
    tn.write(CALL + "\n")
    for i in arc_init:
        tn.write(i)
        sleep(2)

    sota_activator_call_list = []
    jaff_activator_call_list = []

    for ((m, year, start, spot, call, mountain, frql)) in sota_activators:
        m = re.search("(\w+)/(\w+)", call)
        if m:
            if len(m.group(1)) > len(m.group(2)):
                sota_activator_call_list.append(m.group(1).upper())
            else:
                sota_activator_call_list.append(m.group(2).upper())
        else:
            sota_activator_call_list.append(call.upper())
            
    for ((start_t,end_t,jaff,call,desc,url)) in jaff_activators:
        m = re.search("(\w+)/(\w+)", call)
        if m:
            if len(m.group(1)) > len(m.group(2)):
                call2 = m.group(1).upper()
            else:
                call2 = m.group(2).upper()
        else:
            call2 = call.upper()
        jaff_activator_call_list.append(call2)
        jaff_dict[call2] = (call,jaff,url)

    t = threading.Timer(0,tweet_rbn)
    tweet_api = api
    tweet_api2 = api2
    t.start()
    while stop_count < COUNT_MAX:
        try:
            s = tn.read_until("\n")
        except Exception, e:
            tweet(api,"Connection reset by peer.")
            print >>sys.stderr, 'socket error: %s ' % e
            return 
        l = s.split()
        if len(l)>10 and l[0] == 'DX':
            if l[2][-2] == '#':
                (skimmer,freq,call,db) = (l[2],l[3],l[4],l[6])
                m = re.search("(\w+)/(\w+)", call)
                if m:
                    if len(m.group(1)) > len(m.group(2)):
                        call = m.group(1).upper()
                    else:
                        call = m.group(2).upper()
                else:
                    call = call.upper()

                if debug:
                    print call + " at " + skimmer
                    
                if call in sota_activator_call_list:
                    rbn_dirty = True
                    time = l[-1]
                    key = call
                    msg = " {}({}dB)".format(skimmer,db)
                    if key in rbn_dict:
                        rbn_dict[key].append((freq,call,msg))
                    else:
                        rbn_dict[key] = [(freq,call,msg)]

                if call in jaff_activator_call_list:
                    jaff_rbn_dirty = True
                    time = l[-1]
                    key = call
                    (c,jaff,url) = jaff_dict[call]
                    jaff_rbn_dict[key] = (freq,c,jaff,url,skimmer,db)
    tn.close()	
    #tweet(api,"Deactivate RBN Feed for "+",".join(activator_call_list))

def main():
    try:
        auth = tweepy.OAuthHandler(KEYS['Consumerkey'], KEYS['Consumersecret'])
        auth.set_access_token(KEYS['Accesstoken'], KEYS['Accesstokensecret'])
        api = tweepy.API(auth)
    except Exception, e:
        print >>sys.stderr, 'access error: %s' % e
        sys.exit(1)

    # try:
    #     auth = tweepy.OAuthHandler(KEYS['JAFFConsumerkey'], KEYS['JAFFConsumersecret'])
    #     auth.set_access_token(KEYS['JAFFAccesstoken'], KEYS['JAFFAccesstokensecret'])
    #     api2 = tweepy.API(auth)
    # except Exception, e:
    #     print >>sys.stderr, 'access error: %s' % e
    #     sys.exit(1)

    parser = ActivationParser(api)
    url = "http://www.sotawatch.org/alerts.php"
    htmldata = urllib2.urlopen(url)
    parser.feed(htmldata.read())
    htmldata.close()
    parser.close()

 #   forecast(api)

    #jaff_activation(api2)
    
    #if sota_activators or jaff_activators:
    #    t = threading.Timer(0,stop_cluster)
    #    t.start()
    #    run_cluster(api,api2)

if __name__ == '__main__':
    main()
