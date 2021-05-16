class RegionFill {

    constructor(tilex, tiley, pxlx, pxly) {
	this.tile_size = 255;
	this.summit_tile_x = tilex;
	this.summit_pxl_x = pxlx;
	this.summit_tile_y = tiley;
	this.summit_pxl_y = pxly;
	this.current_tile_x = tilex;
	this.current_tile_y = tiley;
	this.current_context = null;
	this.current_image = null;
	this.pixel_stack = []
	this.tile_stack = []
	this.fill_done = false;
	this.tile_extension = false;
    }
    
    setImg(img, x, y, c) {
	if ( x > this.tile_size || x < 0 || y > this.tile_size || y < 0 ) {
	    return;
	}
	img.data[(x + y * (this.tile_size + 1))*4 + 0] = c[0];
	img.data[(x + y * (this.tile_size + 1))*4 + 1] = c[1];
	img.data[(x + y * (this.tile_size + 1))*4 + 2] = c[2];
	img.data[(x + y * (this.tile_size + 1))*4 + 3] = c[3];
    }

    setTile(tilex, tiley, context, image) {
	this.current_tile_x = tilex;
	this.current_tile_y = tiley;
	this.current_context = context;
	this.current_image = image;
    }

    pushTile(tilex, tiley, context, image) {
	this.tile_stack.push([tilex, tiley, context, image]);
    }
    
    pushPxl(tiledx, x, tiledy, y) {
	this.pixel_stack.push([
	    this.current_tile_x + tiledx,
	    this.current_tile_y + tiledy,
	    x, y
	])
    }

    fillAllTile(opaque, color) {
	var tile;
	var tx,ty;
	var ctx,img;
	
	while (this.tile_stack.length > 0) {
	    tile = this.tile_stack.pop();
	    tx = tile[0];
	    ty = tile[1];
	    ctx = tile[2];
	    img = tile[3];
	    this.setTile(tx, ty, ctx, img);
	    for (const elem of this.pixel_stack) {
		if (tx == elem[0] && ty == elem[1]) {
		    //console.log("tile:"+tx+","+ty + "("+elem[2],","+elem[3]+")");
		    this.fillRegion(elem[2], elem[3], opaque, color);
		}
	    }
	}
    }
    
    getImg(img, x, y) {
	if (this.tile_extension) {
	    if ( x > this.tile_size ) {
		this.pushPxl(1,0 , 0,y);
		return -1;
	    }
	    if ( x < 0 ) {
		this.pushPxl(-1,this.tile_size, 0,y);
		return -1;
	    }
	    
	    if ( y > this.tile_size ) {
		this.pushPxl(0,x , 1,0);
		return -1;
	    }
	    if ( y < 0 ) {
		this.pushPxl(0,x , -1,this.tile_size);
	    return -1;
	    }
	    
	    return img.data[(x + y * (this.tile_size+1))*4 + 3];
	} else {
	    if ( x > this.tile_size || x < 0 || y > this.tile_size || y < 0)
		return -1;
    
	    return img.data[(x + y * (this.tile_size+1))*4 + 3];
	}
    }
    
    fillRegion(x, y, opaque, color) {
	var xs = [];
	var ys = [];
	
	var ctx = this.current_context;
	var img = this.current_image;
	var c = this.getImg(img, x, y);
	
	if (c == color[3] || c != opaque)
	    return

	this.setImg(img, x ,y, color);

	xs.push(x);
	ys.push(y);

	while (xs.length > 0) {
	    x = xs.pop();
	    y = ys.pop();
	
	    if (opaque == this.getImg(img, x + 1, y)) {
		this.setImg(img, x + 1, y, color);
		xs.push(x + 1);
		ys.push(y);
	    }
	    if (opaque == this.getImg(img, x , y + 1)) {
		this.setImg(img, x, y + 1, color);
		xs.push(x);
		ys.push(y + 1);
	    }
	    if (opaque == this.getImg(img, x - 1, y)) {
		this.setImg(img, x - 1, y, color);
		xs.push(x - 1);
		ys.push(y);
	    }
	    if (opaque == this.getImg(img, x, y - 1)) {
		this.setImg(img, x, y - 1, color);
		xs.push(x);
		ys.push(y-1);
	    }
	}
	
	ctx.putImageData(img, 0, 0);
    }

    centerfillRegion(x, y, opaque, color) {
	this.tile_extension = true;
	this.fillRegion(x, y, opaque, color);
	this.tile_extension = false;
    }
    
    abs(val) {
	return val < 0 ? -val : val;
    }
    
    fillTile(context, image, tilex, tiley, opaque, color) {
	var dx = this.abs(tilex - this.summit_tile_x);
	var dy = this.abs(tiley - this.summit_tile_y);
	var x;
	var y;
	
	if (dx == 0 && dy == 0) {
	    this.setTile(tilex, tiley, context, image)
	    x = this.summit_pxl_x - tilex * (this.tile_size + 1);
	    y = this.summit_pxl_y - tiley * (this.tile_size + 1);
	    //console.log("center:"+tilex+","+tiley + "("+x+","+y+")");
	    this.centerfillRegion(x, y, opaque, color);
	    this.fill_done = true;
	}
	else if (dx <= 1 && dy <=1) {
	    //console.log("push:"+tilex+","+tiley);
	    this.pushTile(tilex, tiley, context, image);
	}
	
	if (this.fill_done)
	    this.fillAllTile(opaque, color);
    }
}
