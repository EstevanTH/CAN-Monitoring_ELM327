/**
* Code responsible for displaying CAN frames
* This part additionally interacts with the filter GUI parts.
**/


function onConnected(){
	document.body.className = "connected";
}
function onDisconnected(){
	document.body.className = "";
}
if( true ){
	let addByteSpace = function( asciiByte ){
		return " "+asciiByte;
	};
	let knownFrameCells = {
		false: {}, // 11-bit identifier
		true: {} // 29-bit identifier
	};
	let outputTable = document.getElementById( "outputTable" );
	let outputTbody = outputTable.getElementsByTagName( "TBODY" )[0];
	function updateData( frame ){
		if( !frame.r ){ // no RTR frames, only showing data frames
			var frameCells = knownFrameCells[frame.e][frame.i];
			var cellDLC;
			var cellData;
			var cellTimesSeen;
			var cellTime;
			if( frameCells ){
				// Load cells:
				cellDLC = frameCells.DLC;
				cellData = frameCells.data;
				cellTimesSeen = frameCells.timesSeen;
				cellTime = frameCells.time;
			}
			else{
				// Create row and cells:
				var row = document.createElement( "TR" );
					var cellIdentifier = document.createElement( "TD" );
						var formattedIdentifier = frame.i.toString( 16 );
						formattedIdentifier = ( "0".repeat( ( frame.e?8:3 )-formattedIdentifier.length ) )+formattedIdentifier;
						cellIdentifier.innerText = formattedIdentifier;
					row.appendChild( cellIdentifier );
					cellDLC = document.createElement( "TD" );
					row.appendChild( cellDLC );
					cellData = document.createElement( "TD" );
					row.appendChild( cellData );
					cellTimesSeen = document.createElement( "TD" );
						cellTimesSeen.innerText = 0;
					row.appendChild( cellTimesSeen );
					cellTime = document.createElement( "TD" );
					row.appendChild( cellTime );
					var cellActions = document.createElement( "TD" );
						var buttonToWhitelist = document.createElement( "INPUT" );
						buttonToWhitelist.type = "button";
						buttonToWhitelist.value = "To whitelist";
						buttonToWhitelist.title = "Add this identifier to the Identifier whitelist";
						buttonToWhitelist.onclick = function(){
							whitelistNewValueAdd( formattedIdentifier );
						};
						cellActions.appendChild( buttonToWhitelist );
						var buttonToBlacklist = document.createElement( "INPUT" );
							buttonToBlacklist.type = "button";
							buttonToBlacklist.value = "To blacklist";
							buttonToBlacklist.title = "Add this identifier to the Identifier blacklist";
							buttonToBlacklist.onclick = function(){
								blacklistNewValueAdd( formattedIdentifier );
							};
						cellActions.appendChild( buttonToBlacklist );
					row.appendChild( cellActions );
				outputTable.appendChild( row );
				frameCells = {
					"DLC": cellDLC,
					"data": cellData,
					"timesSeen": cellTimesSeen,
					"time": cellTime,
				}
				knownFrameCells[frame.e][frame.i] = frameCells;
			}
			// Update cells:
			var cellDLCText = frame.l;
			var cellDataText = frame.d.replace( /[0-9a-f]{2}/ig, addByteSpace ).substring( 1 );
			var cellTimesSeenText;
			frameTime = new Date( frame.t*1000 );
			frameTimeString_ms = frameTime.getMilliseconds().toString();
			var cellTimeText = frameTime.toTimeString().substr( 0, 8 )+"."+( "0".repeat( 3-frameTimeString_ms.length ) )+frameTimeString_ms;
			if( outputHeld ){
				// Cannot simply do « outputHeldValues[cellDLC] = cellDLCText » because every cell matches the same key!
				outputHeldValues[cellDLC.creationIndex] = [cellDLC, cellDLCText];
				outputHeldValues[cellData.creationIndex] = [cellData, cellDataText];
				cellTimesSeenText = outputHeldValues[cellTimesSeen.creationIndex];
				if( cellTimesSeenText===undefined ){
					cellTimesSeenText = parseInt( cellTimesSeen.innerText ); // current cell value
				}
				else{
					cellTimesSeenText = cellTimesSeenText[1]; // held value
				}
				++cellTimesSeenText;
				outputHeldValues[cellTimesSeen.creationIndex] = [cellTimesSeen, cellTimesSeenText];
				outputHeldValues[cellTime.creationIndex] = [cellTime, cellTimeText];
			}
			else{
				cellDLC.innerText = cellDLCText;
				cellData.innerText = cellDataText;
				cellTimesSeenText = parseInt( cellTimesSeen.innerText )+1;
				cellTimesSeen.innerText = cellTimesSeenText;
				cellTime.innerText = cellTimeText;
			}
		}
	}
}


if( true ){
	var obdRelayUrl = "ws://"+document.location.host+"/frames.ws";
	
	// Get a suitable WebSocket constructor:
	let _WebSocket;
	if( window.WebSocket ){
		_WebSocket = window.WebSocket;
	}
	else if( window.MozWebSocket ){
		_WebSocket = window.MozWebSocket
	}
	
	// Mechanism:
	let obdConnection = undefined;
	function connect(){
		obdConnection = new _WebSocket( obdRelayUrl );
		obdConnection.onopen = function( evt ){
			onConnected();
		};
		obdConnection.onclose = function( evt ){
			onDisconnected();
			connect();
		};
		obdConnection.onmessage = function( evt ){
			var frame = JSON.parse( evt.data );
			updateData( frame );
		};
	}
	
	// Start the magic!
	setTimeout( connect, 1 );
}
