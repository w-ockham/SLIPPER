function getDEM(coords, done) { 
    var url_png = "https://cyberjapandata.gsi.go.jp/xyz/dem_png/{z}/{x}/{y}.png";
    var url_png5a = "https://cyberjapandata.gsi.go.jp/xyz/dem5a_png/{z}/{x}/{y}.png";

    var img = new Image();

    img.crossOrigin = 'anonymous';
    img.onload = function() {
	var canvas = document.createElement('canvas'),
	    context = canvas.getContext('2d'),
	    dem = new Array(256*256);
	//console.log("Loadig image"+img.src)
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
	    dem[i] = 0.01 * h;
	}
	if (done) done(dem)
    }

    img.onerror = function() {
	url = L.Util.template(url_png, coords);
	//console.log("DEM5a not found. using DEM")
	img.src = url
    }
    
    url = L.Util.template(url_png5a, coords);
    img.src = url;
}
