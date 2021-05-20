function getDEM(coords, done) { 
    var url_png = "https://cyberjapandata.gsi.go.jp/xyz/dem_png/{z}/{x}/{y}.png";
    var url_png5a = "https://cyberjapandata.gsi.go.jp/xyz/dem5a_png/{z}/{x}/{y}.png";

    var check_url = function(_url) {
	var xhr;
	xhr = new XMLHttpRequest();
	xhr.open('HEAD', _url, false);
	xhr.send(null);
	return xhr.status;
    }
    
    var img = new Image();

    img.crossOrigin = 'anonymous';
    img.onload = function() {
	var canvas = document.createElement('canvas'),
	    context = canvas.getContext('2d'),
	    dem = new Array(256*256);
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
    url = L.Util.template(url_png5a, coords);
    if(check_url(url) == 404) {
	//console.log("DEM5A not found")
	url = L.Util.template(url_png, coords);
    }
    
    img.src = url;
}
