#!/usr/bin/env python
# coding: utf-8
from datetime import datetime, timedelta
import sqlite3
import sys
import re
from sotakeys import *

association_db = KEYS['ASSOC_DB']+"-new"
dxsummit_db = KEYS['DXSUMMIT_DB']+"-new"

conn_tmp = sqlite3.connect("tmpdb.db")
cur_tmp = conn_tmp.cursor()
cur2_tmp = conn_tmp.cursor()
conn_assoc = sqlite3.connect(association_db)
cur_assoc = conn_assoc.cursor()
conn_summit = sqlite3.connect(dxsummit_db)
cur_summit = conn_summit.cursor()

cur_assoc.execute("create table associations(code text,association text,continent text,primary key(code))")
cur_summit.execute("CREATE TABLE summits (code txt,lat real,lng real,point integer,alt integer,name text,desc text)")
cur_summit.execute("CREATE INDEX summit_index on summits(lat,lng)")
cur_summit.execute("CREATE INDEX summit_code_idx on summits(code)")

conn_assoc.commit()
conn_summit.commit()
i = 0
for s in cur_tmp.execute("select * from allsummits"):
    (code,assoc,region,sname,altm,altf,gr1,gr2,lng,lat,pt,bp,validfrom,validto,_,_,_)= s
    now = int(datetime.utcnow().strftime("%s"))
    valid = int(datetime.strptime(validto,'%d/%m/%Y').strftime("%s"))
    if now < valid:
        m = re.match('(\w+)/(\w+)',code)
        prefix = m.group(1)
        cur2_tmp.execute("select * from continent where prefix = '%s'" % prefix)
        c = cur2_tmp.fetchone()
        if c :
            (_,_,continent) = c
            q = "insert or replace into associations(code, association,continent) values(?, ?, ?)"
            cur_assoc.execute(q,(code,assoc,continent))
            q = "insert into summits(code,lat,lng,point,alt,name,desc) values(?, ?, ?, ?, ?, ?, ?)"
            cur_summit.execute(q,(code,lat,lng,pt,altm,sname,region))
            print "Import:" + code
            i+=1
        else:
            print "Unknown association:" + prefix + " SummitCode=" + code
            exit
    else:
        print "Obsolete summit:" + code + " skipped."

print str(i) + " summits has been imported."
conn_assoc.commit()
conn_summit.commit()
conn_assoc.close()
conn_summit.close()
