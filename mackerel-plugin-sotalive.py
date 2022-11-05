#!/usr/bin/env python3
# coding: utf-8
from datetime import datetime
import json
import os

if os.environ.get('MACKEREL_AGENT_PLUGIN_META','') == '1':
    print("# mackerel-agent-plugin")
    meta = {
        'graphs': {
            'sotawatchlive': {
                'label': 'SOTAwatch Live Status',
                'unit' : 'float',
                'metrics': [
                    {
                        'name':'SOTAwatch3_Status',
                        'label':'SOTAwatch3_Status'
                    },
                    {
                        'name':'Alerts',
                        'label':'Alerts'
                    },
                    {
                        'name':'Spots',
                        'label':'Sposts'
                    },
                    {
                        'name':'APRS_Stations',
                        'label':'APRS_Stations'
                    },
                    {
                        'name':'APRS_packets10',
                        'label':'APRS_packets10'
                    },
                    {
                        'name':'Twitter_API',
                        'label':'twitter'
                    }
                ]
            }
        }
    }
    print(json.dumps(meta))

else:
    with open("/var/tmp/sotalive-stat.json","r") as f:
        jd = json.load(f)
        now = datetime.utcnow().strftime("%s")
        print("sotawatchlive.SOTAwatch3_Status\t{}\t{}".format(jd.get('SOTAWATCH',2),now))
        print("sotawatchlive.Alerts\t{}\t{}".format(jd.get('ALERTS',0),now))
        print("sotawatchlive.Spots\t{}\t{}".format(jd.get('SPOTS',0),now))
        print("sotawatchlive.APRS_Stations\t{}\t{}".format(jd.get('TRACKS',0),now))
        print("sotawatchlive.APRS_packets10\t{}\t{}".format(jd.get('PACKETS',0)/10,now))
        print("sotawatchlive.Twitter_API\t{}\t{}".format(jd.get('TWEET',0)/10,now))
