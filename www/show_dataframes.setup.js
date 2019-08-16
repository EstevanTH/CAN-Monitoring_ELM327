/**
* Code responsible for capture configuration
* Code designed to work with old browsers (to be reviewed & tested)
**/


/// TODO : ne jamais vider les champs "Add:" après les clics respectifs sur "To whitelist" et "To blacklist".


if( true ){
	// Workaround to allow created Elements to have distinct Object keys (using their creationIndex).
	document.createElementWithoutIndex = document.createElement;
	( function(){
		var lastCreationIndex = 0;
		document.createElement = function( nodename ){
			var obj = this.createElementWithoutIndex( nodename );
			if( obj ){
				obj.creationIndex = ++lastCreationIndex;
			}
			return obj;
		}
	} )();
}


if( true ){
	var newXHR;
	if( window.XMLHttpRequest ){
		newXHR = function(){
			return new XMLHttpRequest();
		};
	}
	else if( window.ActiveXObject ){
		newXHR = function(){
			return new ActiveXObject( "Microsoft.XMLHTTP" );
		};
	}
	
	var locationOrigin = document.location.protocol+"//"+document.location.host;
	
	var JSON_parse;
	if( window.JSON && JSON.parse ){
		JSON_parse = JSON.parse;
	}
	else{
		JSON_parse = function( code ){
			return eval( "("+code+")" );
		};
	}
	
	function requestXHRGetJson( callback, uri ){
		var request = newXHR();
		request.open( "GET", locationOrigin+uri, true );
		request.onreadystatechange = function(){
			if( request.readyState===4 ){
				var success = false;
				if( request.status===200 ){
					var data;
					try{
						data = JSON_parse( request.responseText );
						success = true;
					}catch( e ){}
				}
				callback( success, data );
			}
		};
		request.send();
		return request;
	}
	
	function requestXHRPostUrlencoded( callback, uri, data ){
		var request = newXHR();
		request.open( "POST", locationOrigin+uri, true );
		request.setRequestHeader( "Content-Type", "application/x-www-form-urlencoded" );
		request.onreadystatechange = function(){
			if( request.readyState===4 ){
				var success = false;
				if( request.status===200 ){
					success = true;
				}
				if( callback ) callback( success );
			}
		};
		request.send( data );
		return request;
	}
	
	function arrayToUrlencoded( array, fieldName ){
		// Unescaped syntax!
		// The last '&' must be removed.
		var i;
		var len = array.length;
		var postData = "";
		for( i = 0; i<len; ++i ){
			postData += fieldName+"[]="+array[i]+"&";
		}
		return postData;
	}
	
	var validCanIdentifier = /^([0-7][0-9a-f]{2}|[0-1][0-9a-f]{7})$/i;
	var validCanIdentifierOrEmpty = /^(|[0-7][0-9a-f]{2}|[0-1][0-9a-f]{7})$/i;
	
	function isCanIdentifierInHtmlTable( rowContainer, canIdentifier ){
		var inTable = false;
		var rows = rowContainer.childNodes;
		var i;
		var len = rows.length;
		for( i = 0; i<len; ++i ){
			var row = rows[i];
			if( row instanceof Element ){
				// nodes of row all created by JS: only Elements
				if( row.childNodes[1].innerHTML===canIdentifier ){
					inTable = true;
					break;
				}
			}
		}
		return inTable;
	}
	function getCanIdentifiersFromHtmlTable( rowContainer ){
		var canIdentifiers = [];
		var rows = rowContainer.childNodes;
		var i;
		var len = rows.length;
		for( i = 0; i<len; ++i ){
			var row = rows[i];
			if( row instanceof Element ){
				// nodes of row all created by JS: only Elements
				canIdentifiers.push( row.childNodes[1].innerHTML );
			}
		}
		return canIdentifiers;
	}
	function pushCanIdentifierToHtmlTable( rowContainer, canIdentifier, buttonSet ){
		var row = document.createElement( "TR" );
			var cell = document.createElement( "TD" );
				var removeLink = document.createElement( "A" );
					removeLink.href = "#";
					removeLink.innerHTML = "Remove";
					removeLink.onclick = function(){
						row.parentNode.removeChild( row );
						if( buttonSet ){
							buttonSet.className = "actionNeeded";
						}
					};
				cell.appendChild( removeLink );
			row.appendChild( cell );
			var cell = document.createElement( "TD" );
				cell.innerHTML = canIdentifier;
			row.appendChild( cell );
		rowContainer.appendChild( row );
		return row;
	}
	function clearCanIdentifiersFromHtmlTable( rowContainer ){
		var rows = rowContainer.childNodes;
		var i;
		var len = rows.length;
		for( i = len-1; i>=0; --i ){
			var row = rows[i];
			if( row instanceof Element ){
				row.parentNode.removeChild( row );
			}
		}
	}
	
	function canIdentifierIntegerToString( identifier, always8 ){
		// 29-bit CAN identifiers below from 00000000 to 000007ff are returned with 3 digits.
		var targetDigits = ( always8 || identifier>0x7ff )? 8 : 3;
		identifier = identifier.toString( 16 );
		var i;
		for( i = identifier.length; i<targetDigits; ++i ){
			identifier = "0"+identifier;
		}
		return identifier;
	}
}


if( true ){
	// All CAN identifiers are considered being hex strings, except received ones.
	function loadWhitelistAndMask( callback ){
		return requestXHRGetJson( callback, "/api/filter1/getInstalled" );
	}
	function resetWhitelist( callback ){
		return requestXHRPostUrlencoded( callback, "/api/filter1/installByIds", "whitelist=" );
	}
	function setWhitelist( identifiers, callback ){
		if( identifiers.length ){
			postData = arrayToUrlencoded( identifiers, "whitelist" );
			postData = postData.substr( 0, postData.length-1 );
			return requestXHRPostUrlencoded( callback, "/api/filter1/installByIds", postData );
		}
		else{
			return resetWhitelist( callback );
		}
	}
	function loadBlacklist( callback ){
		return requestXHRGetJson( callback, "/api/filter2/getExcluded" );
	}
	function resetBlacklist( callback ){
		return requestXHRPostUrlencoded( callback, "/api/filter2/setExcluded", "blacklist=" );
	}
	function setBlacklist( identifiers, callback ){
		if( identifiers.length ){
			postData = arrayToUrlencoded( identifiers, "blacklist" );
			postData = postData.substr( 0, postData.length-1 );
			return requestXHRPostUrlencoded( callback, "/api/filter2/setExcluded", postData );
		}
		else{
			return resetBlacklist( callback );
		}
	}
	function resetMask( callback ){
		return requestXHRPostUrlencoded( callback, "/api/filter1/installByMask", "mask=&maskingResult=" );
	}
	function setMask( mask, maskingResult, callback ){
		return requestXHRPostUrlencoded( callback, "/api/filter1/installByMask", "mask="+mask+"&maskingResult="+maskingResult );
	}
	function loadInactivityTimeout( callback ){
		return requestXHRGetJson( callback, "/api/getInactivityTimeout" );
	}
	function setInactivityTimeout( timeout, callback ){
		return requestXHRPostUrlencoded( callback, "/api/setInactivityTimeout", "timeout="+timeout );
	}
	
	var whitelistNewValue = document.getElementById( "whitelistNewValue" );
	var blacklistNewValue = document.getElementById( "blacklistNewValue" );
	var maskMask = document.getElementById( "maskMask" );
	var maskMaskingResult = document.getElementById( "maskMaskingResult" );
	var inactivityTimeoutValue = document.getElementById( "inactivityTimeoutValue" );
	var whitelistSet = document.getElementById( "whitelistSet" );
	var blacklistSet = document.getElementById( "blacklistSet" );
	var maskSet = document.getElementById( "maskSet" );
	var inactivityTimeoutSet = document.getElementById( "inactivityTimeoutSet" );
	var whitelistReset = document.getElementById( "whitelistReset" );
	var blacklistReset = document.getElementById( "blacklistReset" );
	var maskReset = document.getElementById( "maskReset" );
	var whitelistReload = document.getElementById( "whitelistReload" );
	var blacklistReload = document.getElementById( "blacklistReload" );
	var maskReload = document.getElementById( "maskReload" );
	var inactivityTimeoutReload = document.getElementById( "inactivityTimeoutReload" );
	var whitelistContent = document.getElementById( "whitelistContent" );
	var blacklistContent = document.getElementById( "blacklistContent" );
	
	var tooltipCanIdentifierSimple = "Values from 000 to 7ff or 00000000 to 1fffffff";
	var tooltipCanIdentifierAdd = tooltipCanIdentifierSimple+"\nPress Enter to add.";
	whitelistNewValue.title = tooltipCanIdentifierAdd;
	blacklistNewValue.title = tooltipCanIdentifierAdd;
	maskMask.title = tooltipCanIdentifierSimple;
	maskMaskingResult.title = tooltipCanIdentifierSimple;
	whitelistSet.title = "Automatically sets Identifier mask as well";
	
	var messageInvalidCanIdentifier = "Invalid CAN identifier!";
	var messageDuplicatedCanIdentifier = "This CAN identifier is already in the list!";
	
	var whitelistNewValueAdd = function( canIdentifier ){
		if( validCanIdentifier.test( canIdentifier ) ){
			if( !isCanIdentifierInHtmlTable( whitelistContent, canIdentifier ) ){
				pushCanIdentifierToHtmlTable( whitelistContent, canIdentifier, whitelistSet );
				whitelistSet.className = "actionNeeded";
			}
			else{
				alert( messageDuplicatedCanIdentifier );
			}
		}
		else{
			alert( messageInvalidCanIdentifier );
		}
	};
	whitelistNewValue.onkeydown = function( ev ){
		try{
			var key = ev.keyCode;
			if( key===13 || key===10 ){
				whitelistNewValueAdd( whitelistNewValue.value );
			}
		}
		catch( e ){
			alert( e );
		}
	};
	var blacklistNewValueAdd = function( canIdentifier ){
		if( validCanIdentifier.test( canIdentifier ) ){
			if( !isCanIdentifierInHtmlTable( blacklistContent, canIdentifier ) ){
				pushCanIdentifierToHtmlTable( blacklistContent, canIdentifier, blacklistSet );
				blacklistSet.className = "actionNeeded";
			}
			else{
				alert( messageDuplicatedCanIdentifier );
			}
		}
		else{
			alert( messageInvalidCanIdentifier );
		}
	};
	blacklistNewValue.onkeydown = function( ev ){
		try{
			var key = ev.keyCode;
			if( key===13 || key===10 ){
				blacklistNewValueAdd( blacklistNewValue.value );
			}
		}
		catch( e ){
			alert( e );
		}
	};
	
	var whitelistSetCallback = function( success ){
		whitelistSet.disabled = false;
		whitelistReset.disabled = false;
		if( success ){
			whitelistSet.className = "";
			whitelistReset.className = "";
			whitelistReload.className = "";
			maskReload.className = "actionNeeded";
		}
		else{
			alert( "Could not apply the identifier whitelist!" );
		}
	};
	var whitelistSetClick = function(){
		setWhitelist( getCanIdentifiersFromHtmlTable( whitelistContent ), whitelistSetCallback );
		whitelistSet.disabled = true;
		whitelistReset.disabled = true;
	};
	whitelistSet.onclick = whitelistSetClick;
	var blacklistSetCallback = function( success ){
		blacklistSet.disabled = false;
		blacklistReset.disabled = false;
		if( success ){
			blacklistSet.className = "";
			blacklistReset.className = "";
			blacklistReload.className = "";
		}
		else{
			alert( "Could not apply the identifier blacklist!" );
		}
	};
	var blacklistSetClick = function(){
		setBlacklist( getCanIdentifiersFromHtmlTable( blacklistContent ), blacklistSetCallback );
		blacklistSet.disabled = true;
		blacklistReset.disabled = true;
	};
	blacklistSet.onclick = blacklistSetClick;
	var maskSetCallback = function( success ){
		maskSet.disabled = false;
		maskReset.disabled = false;
		if( success ){
			maskSet.className = "";
			maskReset.className = "";
			maskReload.className = "";
		}
		else{
			alert( "Could not apply the identifier mask!" );
		}
	};
	var maskSetClick = function(){
		var mask = maskMask.value;
		var maskingResult = maskMaskingResult.value;
		setMask( mask, maskingResult, maskSetCallback );
		maskSet.disabled = true;
		maskReset.disabled = true;
	};
	maskSet.onclick = maskSetClick;
	var inactivityTimeoutSetCallback = function( success ){
		inactivityTimeoutSet.disabled = false;
		if( success ){
			inactivityTimeoutSet.className = "";
			inactivityTimeoutReload.className = "";
		}
		else{
			alert( "Could not apply the CAN inactivity timeout!" );
		}
	};
	var inactivityTimeoutSetClick = function(){
		var timeout = inactivityTimeoutValue.value;
		setInactivityTimeout( timeout, inactivityTimeoutSetCallback );
		inactivityTimeoutSet.disabled = true;
	};
	inactivityTimeoutSet.onclick = inactivityTimeoutSetClick;
	var whitelistResetCallback = function( success ){
		whitelistSet.disabled = false;
		whitelistReset.disabled = false;
		if( success ){
			clearCanIdentifiersFromHtmlTable( whitelistContent );
			whitelistSet.className = "";
			whitelistReset.className = "";
			whitelistReload.className = "";
		}
		else{
			alert( "Could not reset the identifier whitelist!" );
		}
	};
	var whitelistResetClick = function(){
		resetWhitelist( whitelistResetCallback );
		whitelistSet.disabled = true;
		whitelistReset.disabled = true;
	};
	whitelistReset.onclick = whitelistResetClick;
	var blacklistResetCallback = function( success ){
		blacklistSet.disabled = false;
		blacklistReset.disabled = false;
		if( success ){
			clearCanIdentifiersFromHtmlTable( blacklistContent );
			blacklistSet.className = "";
			blacklistReset.className = "";
			blacklistReload.className = "";
		}
		else{
			alert( "Could not reset the identifier blacklist!" );
		}
	};
	var blacklistResetClick = function(){
		resetBlacklist( blacklistResetCallback );
		blacklistSet.disabled = true;
		blacklistReset.disabled = true;
	};
	blacklistReset.onclick = blacklistResetClick;
	var maskResetCallback = function( success ){
		maskSet.disabled = false;
		maskReset.disabled = false;
		if( success ){
			maskMask.value = "";
			maskMaskingResult.value = "";
			maskSet.className = "";
			maskReset.className = "";
			maskReload.className = "";
		}
		else{
			alert( "Could not reset the identifier mask!" );
		}
	};
	var maskResetClick = function(){
		resetMask( maskResetCallback );
		maskSet.disabled = true;
		maskReset.disabled = true;
	};
	maskReset.onclick = maskResetClick;
	var whitelistReloadCallback = function( success, data ){
		whitelistReload.disabled = false;
		if( success ){
			clearCanIdentifiersFromHtmlTable( whitelistContent );
			var whitelist = data["whitelist"];
			if( whitelist ){
				var i;
				var len = whitelist.length;
				for( i = 0; i<len; ++i ){
					var identifier = canIdentifierIntegerToString( whitelist[i] );
					whitelistNewValueAdd( identifier );
				}
			}
			whitelistSet.className = "";
			whitelistReset.className = "";
			whitelistReload.className = "";
		}
		else{
			alert( "Could not reload the identifier whitelist!" );
		}
	};
	var whitelistReloadClick = function( ev, data ){
		if( data===undefined ){
			whitelistReload.disabled = true;
			loadWhitelistAndMask( whitelistReloadCallback );
		}
		else{
			whitelistReloadCallback( true, data );
		}
	};
	whitelistReload.onclick = whitelistReloadClick;
	var blacklistReloadCallback = function( success, data ){
		blacklistReload.disabled = false;
		if( success ){
			clearCanIdentifiersFromHtmlTable( blacklistContent );
			var blacklist = data["blacklist"];
			if( blacklist ){
				var i;
				var len = blacklist.length;
				for( i = 0; i<len; ++i ){
					var identifier = canIdentifierIntegerToString( blacklist[i] );
					blacklistNewValueAdd( identifier );
				}
			}
			blacklistSet.className = "";
			blacklistReset.className = "";
			blacklistReload.className = "";
		}
		else{
			alert( "Could not reload the identifier blacklist!" );
		}
	};
	var blacklistReloadClick = function( ev, data ){
		if( data===undefined ){
			blacklistReload.disabled = true;
			loadBlacklist( blacklistReloadCallback );
		}
		else{
			blacklistReloadCallback( true, data );
		}
	};
	blacklistReload.onclick = blacklistReloadClick;
	var maskReloadCallback = function( success, data ){
		maskReload.disabled = false;
		if( success ){
			var mask = data["mask"];
			var maskingResult = data["maskingResult"];
			if( mask===0 && maskingResult===0 ){
				maskMask.value = "";
				maskMaskingResult.value = "";
			}
			else{
				maskMask.value = canIdentifierIntegerToString( mask, true );
				maskMaskingResult.value = canIdentifierIntegerToString( maskingResult, true );
			}
			maskSet.className = "";
			maskReset.className = "";
			maskReload.className = "";
		}
		else{
			alert( "Could not reload the identifier mask!" );
		}
	};
	var maskReloadClick = function( ev, data ){
		if( data===undefined ){
			maskReload.disabled = true;
			loadWhitelistAndMask( maskReloadCallback );
		}
		else{
			maskReloadCallback( true, data );
		}
	};
	maskReload.onclick = maskReloadClick;
	var maskMaskChange = function(){
		maskSet.className = "actionNeeded";
	};
	maskMask.onchange = maskMaskChange;
	maskMaskingResult.onchange = maskMaskChange;
	var inactivityTimeoutReloadCallback = function( success, data ){
		inactivityTimeoutReload.disabled = false;
		if( success ){
			inactivityTimeoutValue.value = data["timeout"];
			inactivityTimeoutSet.className = "";
			inactivityTimeoutReload.className = "";
		}
		else{
			alert( "Could not reload the CAN inactivity timeout!" );
		}
	};
	var inactivityTimeoutReloadClick = function( ev, data ){
		if( data===undefined ){
			inactivityTimeoutReload.disabled = true;
			loadInactivityTimeout( inactivityTimeoutReloadCallback );
		}
		else{
			inactivityTimeoutReloadCallback( true, data );
		}
	};
	inactivityTimeoutReload.onclick = inactivityTimeoutReloadClick;
	var inactivityTimeoutValueChange = function(){
		inactivityTimeoutSet.className = "actionNeeded";
	};
	inactivityTimeoutValue.onchange = inactivityTimeoutValueChange;
	
	// Load current values on page load (without error messages):
	loadWhitelistAndMask( function( success, data ){
		if( success ){
			whitelistReloadClick( undefined, data );
			maskReloadClick( undefined, data );
		}
	} );
	loadBlacklist( function( success, data ){
		if( success ){
			blacklistReloadClick( undefined, data );
		}
	} );
	loadInactivityTimeout( function( success, data ){
		if( success ){
			inactivityTimeoutReloadClick( undefined, data );
		}
	} );
}


if( true ){
	var outputHeld = false;
	var outputHeldValues = undefined;
	var outputHold = document.getElementById( "outputHold" );
	outputHold.value = "Hold";
	outputHold.onclick = function(){
		if( outputHeld ){ // resume
			outputHeld = false;
			try{
				var creationIndex;
				for( creationIndex in outputHeldValues ){
					var cell = outputHeldValues[creationIndex][0];
					if( cell instanceof Element ){
						cell.innerText = outputHeldValues[creationIndex][1];
					}
				}
			}
			catch( e ){
				alert( e );
			}
			outputHeldValues = undefined;
			outputHold.value = "Hold";
		}
		else{ // start holding
			outputHeld = true;
			outputHeldValues = {};
			outputHold.value = "Resume";
		}
	}
}
