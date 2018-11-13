import re

def addnewstation(msg):
    global st_list
    m = re.search(r'^(\S+)\s(\S+).*\son\s\S+\s\((.+?)\)\s([\d|\.]+)',msg)
    if m :
        (call,time,freq)=(m.group(2),m.group(1),m.group(4))
        for i in range(len(st_list)):
            (c,t,f) = st_list[i]
            if c == call :
                st_list[i] = (call,time,freq)
                return
        st_list = [(call,time,freq)] + st_list
        if len(st_list) > 3:
            st_list = st_list[0:3]

def readlast3(fname):
    global st_list
    global st_msg
    try:
        f = open(fname,'r')
    except Exception, e:
        st_list = []
        st_msg = "None"
        return st_msg
    ln = f.readlines()
    st_list = []
    st_msg = ""
    for l in ln:
        x = l.split()
        (call,time,freq) = (x[0],x[1],x[2])
        st_list = st_list + [(call,time,freq)]
        st_msg = st_msg + " " + time + "-" + call + "-" + freq 
    f.close()
    return st_msg

def writelast3(fname):
    global st_list
    global st_msg

    f = open(fname,'w+')
    for l in st_list:
        (call,time,freq) = l
        f.write(call+" "+time+" "+freq+"\n")
    f.close()
    st_list = []

