class RegionFill {

    constructor(tilex, tiley, pxlx, pxly, dist) {
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
	this.all_done = false;
	this.tile_extension = false;
	this.dist = dist;
    }

    abs(val) {
	return val < 0 ? -val : val;
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

    getImg(img, x, y) {
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
    }

    fillAllTile(opaque, color) {
	var tile;
	var tx,ty,x,y;
	var ctx,img;
	var pxl,painted;
	var newstack = []
	
	while (this.pixel_stack.length > 0) {
	    pxl = this.pixel_stack.pop();
	    tx = pxl[0];
	    ty = pxl[1];
	    x = pxl[2];
	    y = pxl[3];
	    //console.log("Try new pxl:",tx,ty,x,y);
	    painted = false;
	    for (const elem of this.tile_stack) {
		if (tx == elem[0] && ty == elem[1]) {
		    ctx = elem[2];
		    img = elem[3];
		    this.setTile(tx, ty, ctx, img);
		    this.fillRegion(x, y, opaque, color);
		    painted = true;
		    break;
		}
	    }
	    if (!painted) 
		newstack.push([tx, ty, x, y])
	}
	this.pixel_stack = newstack;
	
	for (const elem of this.tile_stack) {
	    ctx = elem[2];
	    img = elem[3];
	    ctx.putImageData(img, 0, 0);
	}
    }
    
    isCenter() {
	if ((this.summit_tile_x == this.current_tile_x)&&
	    (this.summit_tile_y == this.current_tile_y))
	    return true;
	else
	    return false;
    }
	    
    fillRegion(x, y, opaque, color) {
	var xs = [];
	var ys = [];
	
	var ctx = this.current_context;
	var img = this.current_image;
	var c = this.getImg(img, x, y);
	//console.log("Tile: ",this.current_tile_x,",",this.current_tile_y)
	if (c == color[3] || c != opaque) {
	    if (!this.isCenter()) {
		//console.log("Not set: ",x,",",y," is ",c)
		return
	    }
	}
	this.setImg(img, x ,y, color);
	//console.log("Set: ",x,",",y," to ",c)
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
    }

    setSummitPxl(tx, ty, x, y) {
	this.summit_pxl_x = x
	this.summit_pxl_y = y
	this.summit_tile_x = tx
	this.summit_tile_y = ty
	console.log(tx,ty,x,y)
    }
    
    fillTile(context, image, tilex, tiley, opaque, color) {
	var dx = this.abs(tilex - this.summit_tile_x);
	var dy = this.abs(tiley - this.summit_tile_y);
	var x,y;

	if (dx == 0 && dy == 0) {
	    this.setTile(tilex, tiley, context, image)
	    x = this.summit_pxl_x - tilex * (this.tile_size + 1);
	    y = this.summit_pxl_y - tiley * (this.tile_size + 1);
	    //console.log("center: "+tilex+","+tiley + "("+x+","+y+")");
	    this.fillRegion(x, y, opaque, color);
	    this.pushTile(tilex, tiley, context, image);
	}
	else if (dx <= this.dist && dy <= this.dist) {
	    //console.log("push: "+tilex+","+tiley);
	    this.pushTile(tilex, tiley, context, image);
	}
	this.fillAllTile(opaque, color);
    }
}

class RegionFill2 {

    constructor(tilex, tiley, pxlx, pxly, cmap, dist) {
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
	this.all_done = false;
	this.tile_extension = false;
	this.opaque1 = cmap[0].opaque;
	this.opaque2 = cmap[1].opaque;
	this.color1 = cmap[0].color;
	this.color2 = cmap[1].color;
	this.dist = dist;
    }

    abs(val) {
	return val < 0 ? -val : val;
    }
    
    setImg(img, x, y, c) {
	if ( x > this.tile_size || x < 0 || y > this.tile_size || y < 0 ) {
	    return;
	}
	if (c) {
	    img.data[(x + y * (this.tile_size + 1))*4 + 0] = this.color1[0];
	    img.data[(x + y * (this.tile_size + 1))*4 + 1] = this.color1[1];
	    img.data[(x + y * (this.tile_size + 1))*4 + 2] = this.color1[2];
	    img.data[(x + y * (this.tile_size + 1))*4 + 3] = this.color1[3];
	} else {
	    img.data[(x + y * (this.tile_size + 1))*4 + 0] = this.color2[0];
	    img.data[(x + y * (this.tile_size + 1))*4 + 1] = this.color2[1];
	    img.data[(x + y * (this.tile_size + 1))*4 + 2] = this.color2[2];
	    img.data[(x + y * (this.tile_size + 1))*4 + 3] = this.color2[3];
	}
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

    getImg(img, x, y) {
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
    }

    fillAllTile() {
	var tile;
	var tx,ty,x,y;
	var ctx,img;
	var pxl,painted;
	var newstack = []
	
	while (this.pixel_stack.length > 0) {
	    pxl = this.pixel_stack.pop();
	    tx = pxl[0];
	    ty = pxl[1];
	    x = pxl[2];
	    y = pxl[3];
	    //console.log("Try new pxl:",tx,ty,x,y);
	    painted = false;
	    for (const elem of this.tile_stack) {
		if (tx == elem[0] && ty == elem[1]) {
		    ctx = elem[2];
		    img = elem[3];
		    this.setTile(tx, ty, ctx, img);
		    this.fillRegion(x, y);
		    painted = true;
		    break;
		}
	    }
	    if (!painted) 
		newstack.push([tx, ty, x, y])
	}
	this.pixel_stack = newstack;
	
	for (const elem of this.tile_stack) {
	    ctx = elem[2];
	    img = elem[3];
	    ctx.putImageData(img, 0, 0);
	}
    }
    
    isCenter() {
	if ((this.summit_tile_x == this.current_tile_x)&&
	    (this.summit_tile_y == this.current_tile_y))
	    return true;
	else
	    return false;
    }
	    
    fillRegion(x, y) {
	var xs = [];
	var ys = [];

	var opaque1 = this.opaque1,
	    opaque2 = this.opaque2,
	    color = this.color1;
	var ctx = this.current_context;
	var img = this.current_image;
	var c = this.getImg(img, x, y);
	
	//console.log("Tile: ",this.current_tile_x,",",this.current_tile_y)
	if (c == color[3] || (c != opaque1 && c != opaque2)) {
	    /*
	    if (!this.isCenter()) {
		console.log("Not set: ",x,",",y," is ",c)
		return
	    }
	    */
	    return;
	}
	this.setImg(img, x ,y, opaque1 == c);
	//console.log("Set: ",x,",",y," to ",c)
	xs.push(x);
	ys.push(y);

	while (xs.length > 0) {
	    x = xs.pop();
	    y = ys.pop();
	    c = this.getImg(img, x + 1, y)
	    if (opaque1 == c || opaque2 == c) { 
		this.setImg(img, x + 1, y, opaque1 == c);
		xs.push(x + 1);
		ys.push(y);
	    }
	    c = this.getImg(img, x , y + 1)
	    if (opaque1 == c || opaque2 == c ) {
		this.setImg(img, x, y + 1, opaque1 == c);
		xs.push(x);
		ys.push(y + 1);
	    }
	    c = this.getImg(img, x - 1, y)
	    if (opaque1 == c || opaque2 == c ) {
		this.setImg(img, x - 1, y, opaque1 == c);
		xs.push(x - 1);
		ys.push(y);
	    }
	    c = this.getImg(img, x, y - 1)
	    if (opaque1 == c || opaque2 == c ) {
		this.setImg(img, x, y - 1, opaque1 == c);
		xs.push(x);
		ys.push(y-1);
	    }
	}
    }

    fillTile(context, image, tilex, tiley) {
	var dx = this.abs(tilex - this.summit_tile_x);
	var dy = this.abs(tiley - this.summit_tile_y);
	var x,y;

	if (dx == 0 && dy == 0) {
	    this.setTile(tilex, tiley, context, image)
	    x = this.summit_pxl_x - tilex * (this.tile_size + 1);
	    y = this.summit_pxl_y - tiley * (this.tile_size + 1);
	    //console.log("center: "+tilex+","+tiley + "("+x+","+y+")");
	    this.fillRegion(x, y);
	    this.pushTile(tilex, tiley, context, image);
	}
	else if (dx <= this.dist && dy <= this.dist) {
	    //console.log("push: "+tilex+","+tiley);
	    this.pushTile(tilex, tiley, context, image);
	}
	this.fillAllTile();
    }
}
