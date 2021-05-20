/* Callsign Entry Pad for Amateur radio station in JA. 
   Author: JL1NIE
   Based on the following keypad-plugin  
   Author:Vijay krish
   URL:"https://github.com/VijayKrish93/Keypad-plugin"
   Type:Jquery plugin
   Description:Compact keypad plugin which supports text and Numeric
*/

(function($){
    $.fn.searchinput=function(options){
	var options=$.extend({width:100,height:20,candidates:20, done:null},options);
	var ele=this;
	var query=''
	var num_param=''
	var list_param=''
	var data_list= []
	var selected = 0;
	var done=null
	var target={
	    init:function(){
		wquery = 'https://www.sotalive.tk/api/sotasummits/ww?'
		jquery = 'https://www.sotalive.tk/api/sotasummits/ja?'
		num_param='flag=2&code='
		list_param='flag=0&code='
		done = options['done']
	    },
	    markup:function(){
		var input=document.createElement("INPUT");
		input.setAttribute('list',"__sota_summit_list")
		input.setAttribute('oninput',"station_input();")
		input.setAttribute('placeholder',"Summit Code")
		input.style.width=options.width+"px";
		input.style.height="20px";
		input.style.margin="0px 0px 0px 5px";
		input.style.padding="0px";
		input.style.fontSize="12px";
		ele.append(input);
		var span=document.createElement("SPAN");
		span.style.width=20+"px";
		span.style.height="10px";
		span.style.margin="0px 0px 5px 0px";
		span.style.padding="0px";
		span.style.fontSize="10px";
		ele.append(span);
		var datalist=document.createElement("DATALIST")
		datalist.id="__sota_summit_list";
		ele.append(datalist);
	    }
	};
	target.init();    
	target.markup();
	window.station_input = function station_input (){
	    text = $('input').val()
	    station_query(text)
	}
	
	function station_query(text) {
	    $(ele).find("span").each(function(index, s) { s.innerHTML = '';});
	    if (text.length > 2){
		str = text.split(' ')
		for (var s of data_list) {
		    if (str[0] != undefined ) {
			smt = str[0].toUpperCase()
			if (s['code'] == smt)
			    if (done) {
				$('input').val('')
				done(s)
			    }
		    }
		}
		if (options.candidates > 0) {
		    dl = $('datalist')
		    dl.empty()
		    data_list = []
		    $.getJSON(wquery, num_param + text,function(res) {
			number = res['summits']['totalCount']
			$(ele).find("span").each(function(index, s) { s.innerHTML = number+'mts';});
			if (number < options.candidates ) {
			    var prfx = text.substr(0,2).toUpperCase()
			    if(prfx == 'JA')
				q = jquery
			    else
				q = wquery
			    $.getJSON(q, list_param + text,function(res){
				summits = res['summits']
				if (summits) {
				    for (var s of summits) {
					code = s['code']
					lat = s['lat']
					lng = s['lon']
					if (prfx == 'JA')
					    name = s['name_j']
					else
					    name = s['name']
					data = s
					var opt = document.createElement("OPTION")
					opt.value= code + ' ' + name 
					dl.append(opt)
					data_list.push({
					    'code': code,
					    'coord':[lat ,lng],
					    'name': name,
					    'data': data})
				    }
				}
			    })
			}
		    })
		}
	    }
	}
	
    };
}(jQuery));
