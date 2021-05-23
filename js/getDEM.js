function getDEM(coords, done) { 
    var url_png = "https://cyberjapandata.gsi.go.jp/xyz/dem_png/{z}/{x}/{y}.png";
    var url_png5a = "https://cyberjapandata.gsi.go.jp/xyz/dem5a_png/{z}/{x}/{y}.png";
    var threshold = 4000;
    var img = new Image();
    var dem;
    var dem5a;
    var url10,url5;
    var is5a,force10b;
    var force5a = false;
    var errpxl = [];
    var missingarea;
    
    img.crossOrigin = 'anonymous';
    img.onload = function() {
	var canvas = document.createElement('canvas'),
	    context = canvas.getContext('2d'),
	    missing = 0,
	    prevh;
	
	canvas.width = 256;
	canvas.height = 256;
	context.drawImage(this, 0, 0);
	d = context.getImageData(0,0,256,256).data;
	for (var i = 0; i<= 0xffff; i++) {
	    r = d[i*4 + 0];
	    g = d[i*4 + 1];
	    b = d[i*4 + 2];
	    x = r * Math.pow(2,16) + g * Math.pow(2,8) +  b;
	    h = ( x < Math.pow(2, 23))? x : x - Math.pow(2, 24);
	    if ( h == -Math.pow(2,23))
		h = 0;
	    
	    if (is5a && h < 100) {
		missing++;
 		if ((i && 0xff) != 0 && prevh >= 100) {
		    errpxl.push(i-1)
		}
	    } else if (is5a && prevh < 100) {
		missing++;
		if ((i && 0xff) != 0 && h >= 100) {
		    errpxl.push(i)
		}
	    }
	    prevh = h;
	    dem[i] = 0.01 * h;

	}
	if (force10b || force5a) {
	    if (done) done(dem)
	    return;
	}
	
	if (is5a) {
	    if (missing < threshold) {
		if (done) done(dem)
		return;
	    }
	    is5a = false;
	    force10b = false;
	    missingarea = 100.0 * missing / 65536
	    dem5a = dem.concat();
	    img.src = url10;
	    
	} else {
	    var pts = errpxl.length,
		sumd = 0,delta;
	    
	    while (errpxl.length > 0) {
		p = errpxl.pop();
		sumd = dem5a[p] - dem[p]
	    }
	    delta = sumd/pts;
	    //console.log("Original DEM5A:" + url5)
	    //console.log(missingarea+"% of DEM5A is missing")
	    //console.log("Interpolate by DEM10B:" + img.src)
	    //console.log("Caculate " + pts + " points")
	    //console.log("DEM5A is higher than dem by " + sumd/pts + "m")
	    for (var i = 0; i<= 0xffff; i++) {
		if (dem5a[i] < 1.0)
		    dem5a[i] = dem[i] -delta
	    }
	    if (done) done(dem5a)
	    return 
	}
    }

    img.onerror = function() {
	if (force10b) {
	    console.log("Fatal No GSI DEM:",url10)
	    return;
	} else {
//	    console.log("DEM5a not found. using DEM")
	    is5a = false;
	    force10b = true;
	    img.src = url10
	}
    }
    
    url5 = L.Util.template(url_png5a, coords);
    url10 = L.Util.template(url_png, coords);
    dem = new Array(256*256);    
    is5a = true;
    force10b = false;
    img.src = url5;
}
