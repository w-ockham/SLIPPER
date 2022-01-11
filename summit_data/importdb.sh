#!/bin/bash
PATH=/usr/local/sbin:/usr/bin:/bin
TARGET=/home/ubuntu/sotaapp/backend/database
cd $TARGET
rm -f summitslist.csv tmp.csv tmpdb.db
wget --quiet https://www.sotadata.org.uk/summitslist.csv
sed -e '1,1d' summitslist.csv > tmp.csv
sqlite3 tmpdb.db -separator , ".import tmp.csv allsummits"
sed -e '1i code,lat,lng,point,alt,name,region,name_k,region_k' ja_summits.csv > tmp.csv
sqlite3 tmpdb.db -separator , ".import tmp.csv ja_summits" 
date > import.log
./make-summitlist.py tmpdb.db continent.csv association-new.db summits-new.db &>> import.log
mv association-new.db association.db
mv summits-new.db summits.db