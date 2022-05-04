#!/bin/bash
PATH=/usr/local/sbin:/usr/bin:/bin
TARGET=/home/ubuntu/sotaapp/backend/database
cd $TARGET
date > import.log
rm -f summitslist.csv tmp.csv tmpdb.db
wget --quiet https://www.sotadata.org.uk/summitslist.csv &>> import.log
sed -e '1,1d' summitslist.csv > tmp.csv
sqlite3 tmpdb.db -separator , ".import tmp.csv allsummits" &>> import.log

cat ja_summits.csv | sed -e 's/^[^[:alnum:]]*//' -e 's/\r//g' -e '1i code,lat,lng,point,alt,name,region,name_k,region_k' > tmp.csv
sqlite3 tmpdb.db -separator , ".import tmp.csv ja_summits"  &>> import.log

cat jaarm.csv ja5arm.csv ja6arm.csv ja8arm.csv| sed -e 's/^[^[:alnum:]]*//' -e 's/\r//g' -e '1i code,name,alt1,alt2,lon,lat,validfrom,validto,score,prom,clon,clat,name_k' > tmp.csv
sqlite3 tmpdb.db -separator ',' ".import tmp.csv jaarm_summits"  &>> import.log

./make-summitlist.py tmpdb.db continent.csv association-new.db summits-new.db &>> import.log

mv association-new.db association.db
mv summits-new.db summits.db
touch $TARGET/../uwsgi.touch
